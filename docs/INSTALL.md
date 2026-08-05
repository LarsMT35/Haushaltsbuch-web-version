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
| `OS_VERSION` | `13` (Trixie) | Debian-Version; fällt automatisch auf `12` (Bookworm) zurück, falls kein Trixie-Template verfügbar ist |
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
8. **Wiederkehrende Kostenpositionen** (*Wiederkehrend*): ADAC, Rundfunkbeitrag,
   Abos usw. anlegen (Erkennungstext für die Abbuchung genügt meist) und über
   „Erkennung ausführen" mit bestehenden Buchungen verknüpfen lassen. Wird ein
   Teil monatlich über ein anderes Konto vorfinanziert (z.B. gemeinsames
   Konto), zusätzlich das Vorfinanzierungskonto samt Erkennungstext für die
   Erstattungsbuchungen eintragen – die Ampel-Übersicht zeigt dann Soll gegen
   Ist und schlägt bei Abweichung eine neue Monatsrate vor.
9. **Saldo-Abgleich** (*Einstellungen*): für Konten, deren Bank einen
   laufenden Saldo mitliefert (z.B. ING), lässt sich der berechnete gegen den
   gemeldeten Kontostand prüfen – deckt fehlende Importe oder Lücken auf.
10. **Altbestand einspielen**: alte Jahres-CSV-Exporte der Banken über denselben
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

## 8. Optional: lokale KI (Ollama) anbinden

Rein optional. Ohne Konfiguration erscheint die Funktion gar nicht erst, die
App bleibt vollständig nutzbar. Die KI schlägt Kategorien für Buchungen vor,
bei denen keine Regel greift – **zugeordnet wird erst nach Bestätigung**.

Läuft Ollama auf einem **anderen Rechner** als der Container (der Normalfall,
z.B. auf dem PC mit der Grafikkarte), sind drei Dinge nötig:

### a) Ollama nach außen hörbar machen

Ollama lauscht standardmäßig **nur auf `127.0.0.1`** und ist damit vom
Container aus nicht erreichbar. Das ist die mit Abstand häufigste
Fehlerquelle.

| System | Vorgehen |
|---|---|
| **Windows** | Einstellungen → *Umgebungsvariablen für dieses Konto* → neu: `OLLAMA_HOST` = `0.0.0.0` → Ollama über das Tray-Icon beenden und neu starten |
| **Linux (systemd)** | `sudo systemctl edit ollama` → `[Service]` / `Environment="OLLAMA_HOST=0.0.0.0"` → `sudo systemctl daemon-reload && sudo systemctl restart ollama` |
| **macOS** | `launchctl setenv OLLAMA_HOST 0.0.0.0`, danach Ollama neu starten |

Prüfen – vom PC aus, aber mit der eigenen LAN-IP statt `localhost`:

```bash
curl http://192.168.1.50:11434/api/tags
```

Kommt hier nichts, blockiert meist noch die **Firewall**: Port `11434/TCP`
für das lokale Netz freigeben (Windows-Firewall: eingehende Regel).

### b) Modell bereitstellen

```bash
ollama pull qwen2.5:14b
```

### c) App konfigurieren

In der `.env` neben der `docker-compose.yml` (auf dem Docker-Host, z.B. im LXC):

```bash
OLLAMA_URL=http://192.168.1.50:11434   # LAN-IP des PCs, NICHT localhost
OLLAMA_MODEL=qwen2.5:14b
OLLAMA_TIMEOUT=300                     # ohne GPU großzügig bemessen
```

`localhost` wäre hier der Container selbst – es muss die IP des PCs sein.
Danach übernehmen:

```bash
docker compose up -d
```

### Kontrolle

*Buchungen* öffnen: erscheint der Knopf **🤖 KI-Vorschläge**, steht die
Verbindung. Ist er ausgegraut, nennt der Tooltip den Grund. Ausführlicher
über den Statusendpunkt:

| Antwort | Bedeutung |
|---|---|
| `enabled: false` | `OLLAMA_URL` nicht gesetzt oder Stack nicht neu gestartet |
| `reachable: false` | `OLLAMA_HOST=0.0.0.0` fehlt, Firewall blockt, PC aus, oder falsche IP |
| `detail: "Modell … nicht installiert"` | `ollama pull <modell>` auf dem PC nachholen |

Ist der PC ausgeschaltet, bleibt der Knopf inaktiv – alles andere in der App
funktioniert unverändert weiter.

**Was übertragen wird:** ausschließlich Gegenpartei, Verwendungszweck und
Betrag der noch nicht zugeordneten Buchungen, dazu die Namen der eigenen
Kategorien. Keine IBANs, keine Kontonamen, keine Salden. Ziel ist
ausschließlich die selbst konfigurierte Instanz im eigenen Netz.

---

## 9. Fehlerbehebung

| Symptom | Prüfen |
|---|---|
| Seite lädt nicht | `docker compose ps` – laufen `db`, `backend`, `frontend`? |
| Fehler beim Start | `docker compose logs backend` (Migrationen/DB-Verbindung) |
| Login geht nicht | `ADMIN_PASSWORD` in `.env` gilt nur für die **Erstanlage**; danach Passwort in der App ändern bzw. per Admin zurücksetzen |
| Import-Fehler | Encoding/Format prüfen → Mapping-Assistent verwenden |
| Docker im LXC startet nicht | LXC braucht `features: nesting=1` (im Installer gesetzt) |
| Version prüfen | `curl -s http://localhost:8080/api/health` |
| Update erfolgreich, aber Änderungen fehlen im Browser | Browser-Cache auf `index.html` – einmal **Strg+Shift+R** (Hard-Refresh) oder Inkognito-Fenster. Seit dieser Version setzt nginx `no-cache` auf `index.html`, daher tritt es künftig nicht mehr auf. |
| KI-Knopf fehlt oder ist ausgegraut | siehe [Abschnitt 8](#8-optional-lokale-ki-ollama-anbinden) – meist fehlt `OLLAMA_HOST=0.0.0.0` auf dem KI-Rechner |
| Depot-Saldo zu hoch nach einem Import-Rollback | Altbestand vor v1.5.1: einmal *Buchungen → Umbuchungen erkennen* klicken, das räumt verwaiste Gegenbuchungen weg |
