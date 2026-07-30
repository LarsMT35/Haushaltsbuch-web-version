#!/usr/bin/env bash
# ============================================================================
#  Haushaltsbuch LXC – Installer im Stil der Proxmox-Community-Skripte
# ----------------------------------------------------------------------------
#  Auf dem Proxmox-HOST (als root) ausführen:
#
#    bash -c "$(wget -qLO - https://raw.githubusercontent.com/LarsMT35/Haushaltsbuch-web-version/main/proxmox/haushaltsbuch-lxc.sh)"
#
#  Erstellt einen unprivilegierten Debian-12-LXC (Nesting für Docker),
#  installiert Docker + die App und gibt am Ende URL & Zugangsdaten aus.
#
#  Standardwerte per Umgebungsvariable überschreibbar, z.B.:
#    CT_ID=120 DISK_SIZE=10 BRIDGE=vmbr1 bash haushaltsbuch-lxc.sh
# ============================================================================
set -euo pipefail

# ------------------------------------------------------------------ Optik
YW=$'\033[33m'; GN=$'\033[1;92m'; RD=$'\033[01;31m'; BL=$'\033[36m'; CL=$'\033[m'
CM="${GN}✔${CL}"; CROSS="${RD}✖${CL}"; INFO="${BL}ℹ${CL}"

msg_info()  { echo -e " ${YW}➤${CL}  $1"; }
msg_ok()    { echo -e " ${CM}  $1"; }
msg_error() { echo -e " ${CROSS}  $1"; }

header() {
cat <<'EOF'
    __  __                __          ____  __       __            __
   / / / /___ ___  _______/ /_  ____ _/ / /_/ /______/ /_  __  ______/ /_
  / /_/ / __ `/ / / / ___/ __ \/ __ `/ / __/ ___/ __ \/ / / / / ___/ __ \
 / __  / /_/ / /_/ (__  ) / / / /_/ / / /_(__  ) /_/ / /_/ / / /__/ / / /
/_/ /_/\__,_/\__,_/____/_/ /_/\__,_/_/\__/____/_.___/\__,_/_/\___/_/ /_/

          Haushaltsbuch Web  ·  LXC-Installer (Debian 12 + Docker)
EOF
}

# ------------------------------------------------------------- Vorprüfung
if ! command -v pveversion >/dev/null 2>&1; then
  msg_error "Dieses Skript muss auf einem Proxmox-VE-Host laufen."
  exit 1
fi
if [ "$(id -u)" -ne 0 ]; then
  msg_error "Bitte als root ausführen."
  exit 1
fi

header
echo

# ------------------------------------------------------- Konfiguration
CT_ID="${CT_ID:-$(pvesh get /cluster/nextid)}"
HOSTNAME="${HOSTNAME_CT:-haushaltsbuch}"
DISK_SIZE="${DISK_SIZE:-8}"          # GB
CORES="${CORES:-2}"
RAM="${RAM:-2048}"                   # MB
BRIDGE="${BRIDGE:-vmbr0}"
NET="${NET:-dhcp}"                   # dhcp oder z.B. 192.168.1.50/24,gw=192.168.1.1
STORAGE="${STORAGE:-local-lvm}"      # Storage für die Container-Disk
TMPL_STORAGE="${TMPL_STORAGE:-local}"
REPO_URL="${REPO_URL:-https://github.com/LarsMT35/Haushaltsbuch-web-version.git}"
REPO_FALLBACK="https://github.com/LarsMT35/Test.git"
APP_DIR="/opt/haushaltsbuch"
APP_PORT="${APP_PORT:-8080}"

echo -e " ${INFO}  Container-ID: ${BL}${CT_ID}${CL}   Hostname: ${BL}${HOSTNAME}${CL}"
echo -e " ${INFO}  Ressourcen:   ${BL}${CORES} Kerne, ${RAM} MB RAM, ${DISK_SIZE} GB Disk auf ${STORAGE}${CL}"
echo -e " ${INFO}  Netzwerk:     ${BL}${BRIDGE} (${NET})${CL}"
echo
read -r -p " Weiter mit diesen Einstellungen? [J/n] " ANSWER
case "${ANSWER:-J}" in [JjYy]*|"") ;; *) echo " Abgebrochen."; exit 0 ;; esac

# ------------------------------------------------------- Template holen
msg_info "Suche Debian-12-Template"
pveam update >/dev/null
TEMPLATE=$(pveam available --section system | awk '/debian-12-standard/{print $2}' | sort -V | tail -1)
if [ -z "$TEMPLATE" ]; then
  msg_error "Kein debian-12-standard-Template gefunden."
  exit 1
fi
if ! pveam list "$TMPL_STORAGE" | grep -q "$TEMPLATE"; then
  msg_info "Lade Template $TEMPLATE"
  pveam download "$TMPL_STORAGE" "$TEMPLATE" >/dev/null
fi
msg_ok "Template bereit: $TEMPLATE"

# ------------------------------------------------------- LXC erstellen
if [ "$NET" = "dhcp" ]; then
  NETCFG="name=eth0,bridge=${BRIDGE},ip=dhcp"
else
  NETCFG="name=eth0,bridge=${BRIDGE},ip=${NET}"
fi

msg_info "Erstelle LXC ${CT_ID} (unprivilegiert, Nesting für Docker)"
pct create "$CT_ID" "${TMPL_STORAGE}:vztmpl/${TEMPLATE}" \
  --hostname "$HOSTNAME" \
  --cores "$CORES" --memory "$RAM" --swap 512 \
  --rootfs "${STORAGE}:${DISK_SIZE}" \
  --net0 "$NETCFG" \
  --features nesting=1,keyctl=1 \
  --unprivileged 1 \
  --onboot 1 \
  --tags haushaltsbuch >/dev/null
msg_ok "LXC ${CT_ID} erstellt"

msg_info "Starte Container"
pct start "$CT_ID" >/dev/null
sleep 5
for i in $(seq 1 30); do
  if pct exec "$CT_ID" -- ping -c1 -W1 deb.debian.org >/dev/null 2>&1; then break; fi
  sleep 2
done
msg_ok "Container läuft, Netzwerk verfügbar"

in_ct() { pct exec "$CT_ID" -- bash -c "$1"; }

# ------------------------------------------------------- Software im CT
msg_info "Installiere Grundpakete (apt)"
in_ct "export DEBIAN_FRONTEND=noninteractive
       apt-get update -qq
       apt-get install -y -qq curl git ca-certificates openssl >/dev/null"
msg_ok "Grundpakete installiert"

msg_info "Installiere Docker (get.docker.com)"
in_ct "curl -fsSL https://get.docker.com | sh >/dev/null 2>&1 && systemctl enable --now docker >/dev/null 2>&1"
msg_ok "Docker installiert"

msg_info "Klone Haushaltsbuch-Repository"
in_ct "git clone -q '$REPO_URL' '$APP_DIR' 2>/dev/null || git clone -q '$REPO_FALLBACK' '$APP_DIR'"
msg_ok "Repository unter $APP_DIR"

msg_info "Erzeuge Zugangsdaten (.env)"
ADMIN_PW=$(in_ct "openssl rand -base64 12 | tr -d '/+=' | cut -c1-12")
in_ct "cd '$APP_DIR' && cat > .env <<ENV
DB_PASSWORD=\$(openssl rand -hex 16)
SECRET_KEY=\$(openssl rand -hex 32)
ADMIN_USERNAME=admin
ADMIN_PASSWORD=${ADMIN_PW}
APP_PORT=${APP_PORT}
ENV
chmod 600 .env"
msg_ok "Zufalls-Passwörter erzeugt"

msg_info "Baue und starte den Docker-Stack (dauert beim ersten Mal einige Minuten)"
in_ct "cd '$APP_DIR' && docker compose up -d --build --quiet-pull >/dev/null 2>&1"
msg_ok "Stack läuft"

CT_IP=$(pct exec "$CT_ID" -- hostname -I | awk '{print $1}')

echo
echo -e " ${GN}Fertig!${CL}"
echo -e " ────────────────────────────────────────────────────────────"
echo -e "  URL:          ${BL}http://${CT_IP}:${APP_PORT}${CL}"
echo -e "  Benutzer:     ${BL}admin${CL}"
echo -e "  Passwort:     ${BL}${ADMIN_PW}${CL}   ${YW}(nach dem ersten Login ändern!)${CL}"
echo -e "  App-Ordner:   ${APP_DIR} (im Container ${CT_ID})"
echo -e "  Update:       pct exec ${CT_ID} -- ${APP_DIR}/scripts/update.sh"
echo -e "  Backup:       pct exec ${CT_ID} -- ${APP_DIR}/scripts/backup.sh <ziel>"
echo -e " ────────────────────────────────────────────────────────────"
echo -e "  Anleitung:    docs/INSTALL.md im Repository"
echo
