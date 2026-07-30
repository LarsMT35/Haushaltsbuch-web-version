# Installation & Betrieb

Diese Anleitung deckt beide Wege ab: den **Proxmox-Einzeiler** (im Stil der
Proxmox-Community-Skripte) und die **manuelle Installation** per Docker Compose
auf einem beliebigen Linux-Host. Danach: erste Schritte, Updates, Backup, HTTPS.

---

## 1. Voraussetzungen

| Variante | Voraussetzung |
|---|---|
| Proxmox-Einzeiler | Proxmox VE 7/8, Internetzugang, ~8 GB freier Storage |
| Manuell | Beliebiger Linux-Host mit Docker + Docker-Compose-Plugin |

Die App braucht im Betrieb wenig Ressourcen: **2 CPU-Kerne, 2 GB RAM, 8 GB Disk**
reichen für den Heimgebrauch komfortabel.

---

## 2. Variante A – Proxmox-Einzeiler (empfohlen)

Auf dem **Proxmox-Host** als root in der Shell ausführen:

```bash
bash -c "$(wget -qLO - https://raw.githubusercontent.com/LarsMT35/Haushaltsbuch-web-version/main/proxmox/haushaltsbuch-lxc.sh)"
```

Das Skript arbeitet wie die bekannten Community-Skripte:

1. zeigt die geplanten Einstellungen an und fragt einmal nach Bestätigung
2. lädt (falls nötig) das Debian-12-LXC-Template
3. erstellt einen **unprivilegierten LXC** mit `nesting=1` (für Docker),
   Autostart bei Host-Boot und Tag `haushaltsbuch`
4. installiert im Container Docker, klont dieses Repository nach
   `/opt/haushaltsbuch` und erzeugt eine `.env` mit **zufälligen Passwörtern**
5. baut und startet den Stack (PostgreSQL + Backend + Frontend)
6. gibt am Ende **URL, Benutzername und Admin-Passwort** aus → notieren!

### Standardwerte anpassen

Alle Werte lassen sich per Umgebungsvariable überschreiben:

```bash
CT_ID=120 DISK_SIZE=10 RAM=3072 BRIDGE=vmbr1 NET="192.168.1.50/24,gw=192.168.1.1" \
bash -c "$(wget -qLO - https://raw.githubusercontent.com/LarsMT35/Haushaltsbuch-web-version/main/proxmox/haushaltsbuch-lxc.sh)"
```

| Variable | Standard | Bedeutung |
|---|---|---|
| `CT_ID` | nächste freie ID | Container-ID |
| `HOSTNAME_CT` | `haushaltsbuch` | Hostname des LXC |
| `DISK_SIZE` | `8` | Disk in GB |
| `CORES` / `RAM` | `2` / `2048` | CPU-Kerne / RAM in MB |
| `BRIDGE` | `vmbr0` | Netzwerk-Bridge |
| `NET` | `dhcp` | oder statisch: `IP/CIDR,gw=GATEWAY` |
| `STORAGE` | `local-lvm` | Storage für die Container-Disk |
| `APP_PORT` | `8080` | HTTP-Port der App |

---

## 3. Variante B – Manuell per Docker Compose

Auf einem Host mit Docker (VM, LXC mit Nesting, NUC, …):

```bash
git clone https://github.com/LarsMT35/Haushaltsbuch-web-version.git /opt/haushaltsbuch
cd /opt/haushaltsbuch

cp .env.example .env
nano .env        # DB_PASSWORD, SECRET_KEY, ADMIN_PASSWORD setzen!
# SECRET_KEY erzeugen z.B. mit:  openssl rand -hex 32

docker compose up -d --build
```

Danach läuft die App auf `http://<host>:8080` (Port über `APP_PORT` in der
`.env` änderbar). Die Datenbank liegt im Docker-Volume `db_data`,
Schema-Migrationen laufen bei jedem Start automatisch (`alembic upgrade head`).

---

## 4. Erste Schritte in der App

1. **Anmelden** mit `admin` und dem Passwort aus der Installation, dann unter
   *Einstellungen → Passwort ändern* ein eigenes setzen.
2. **Zweiten Nutzer anlegen** (*Einstellungen → Benutzerverwaltung*) – es gibt
   bewusst keine Selbstregistrierung.
3. **Konten anlegen** (*Einstellungen → Neues Konto*): Name, Typ, **IBAN**
   (wichtig für Zielkonto-Erkennung und Umbuchungserkennung) und den
   **Anfangssaldo mit Stichtag** – ohne ihn stimmt kein berechneter Kontostand.
   Tipp: Bargeld als eigenes Konto vom Typ „Bargeld" führen.
4. **Rechte vergeben** (*Einstellungen → Kontorechte*): z.B. gemeinsames Konto →
   eine Person Eigentümer/Bearbeiter, die andere Leser.
5. **CSV importieren** (*Import*): Datei hineinziehen, Profil wählen
   (Sparkasse und ING sind vorkonfiguriert), Vorschau prüfen, übernehmen.
   Unbekanntes Bankformat → **Mapping-Assistent** nutzen und als neues Profil
   speichern. Jeder Import ist unter *Bisherige Importe* komplett rückrollbar.
6. **Kategorien & Regeln**: Nicht zugeordnete Buchungen unter *Buchungen*
   zuordnen und per „↻ Regel" dauerhaft automatisieren; unter *Regeln* lassen
   sich Regeln rückwirkend auf den Bestand anwenden.
7. **Budgets** (*Budgets*): monatliches Budget je Kategorie anlegen – die
   Ampel (grün/gelb/rot) zeigt die Ausschöpfung, Schwellwerte sind als Admin
   konfigurierbar.
8. **Altbestand einspielen**: alte Jahres-CSV-Exporte der Banken über denselben
   Import-Weg laden (Banken halten Umsätze oft nur begrenzt vor – früh sichern!).

---

## 5. Updates

Im App-Ordner (`/opt/haushaltsbuch`):

```bash
./scripts/update.sh
```

Das Skript zieht **vor** dem Update einen Datenbank-Dump, holt den neuen Stand
(`git pull`) und baut den Stack neu; Migrationen laufen automatisch. Bei
Problemen: Dump mit `scripts/restore.sh` zurückspielen und den vorherigen
Stand mit `git checkout <commit>` + `docker compose up -d --build` starten.

Im Proxmox-LXC vom Host aus: `pct exec <CTID> -- /opt/haushaltsbuch/scripts/update.sh`

---

## 6. Backup aufs NAS

Täglicher Dump per Cron (im Container/Host, `crontab -e`):

```cron
15 2 * * * /opt/haushaltsbuch/scripts/backup.sh /mnt/nas/haushaltsbuch
```

- `backup.sh` behält automatisch die letzten 14 Generationen.
- NAS-Mount z.B. per NFS/CIFS nach `/mnt/nas` einhängen (im LXC: Mountpoint
  über den Proxmox-Host durchreichen).
- **Rücksicherung mindestens einmal testen**: 
  `./scripts/restore.sh /mnt/nas/haushaltsbuch/haushaltsbuch_<datum>.sql.gz` –
  ein Backup, das nie zurückgespielt wurde, ist kein Backup.

---

## 7. HTTPS im LAN & Zugriff von unterwegs

Die App selbst spricht HTTP; für **HTTPS im Heimnetz** einen Reverse-Proxy
davorschalten (z.B. Caddy, Traefik oder Nginx Proxy Manager – viele nutzen
dafür einen eigenen LXC). Beispiel Caddy:

```
haushaltsbuch.lan {
    tls internal
    reverse_proxy 192.168.1.50:8080
}
```

**Von unterwegs**: keine Portfreigabe nötig – VPN (WireGuard) oder Tailscale
auf dem Proxmox-Host/im LXC genügt; die App bleibt unverändert.

---

## 8. Fehlerbehebung

| Symptom | Prüfen |
|---|---|
| Seite lädt nicht | `docker compose ps` – laufen `db`, `backend`, `frontend`? |
| Fehler beim Start | `docker compose logs backend` (Migrationen/DB-Verbindung) |
| Login geht nicht | `ADMIN_PASSWORD` in `.env` gilt nur für die **Erstanlage**; danach Passwort in der App ändern bzw. per Admin zurücksetzen |
| Import-Fehler | Encoding/Format prüfen → Mapping-Assistent verwenden |
| Docker im LXC startet nicht | LXC braucht `features: nesting=1` (im Installer gesetzt) |
| Version prüfen | `curl -s http://localhost:8080/api/health` |
