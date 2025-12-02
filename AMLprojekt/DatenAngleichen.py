import os
import cv2
import pandas as pd

from Feature_Extraction import VideoCleaner


# ==========================================
# Ordnerdefinitionen
# ==========================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATEN_ORDNER = os.path.join(BASE_DIR, "Datensatz")
AUSGABE_ORDNER = os.path.join(BASE_DIR, "Bereinigt")
os.makedirs(AUSGABE_ORDNER, exist_ok=True)

# Logliste
error_log = []


# ==========================================
# 1. VIDEODATEN SAMMELN
# ==========================================
print("🔍 Sammle Videoinformationen...")

video_infos = []

for root, dirs, files in os.walk(DATEN_ORDNER):
    for file in files:
        if file.lower().endswith((".mp4", ".avi", ".mov", ".mkv")):
            video_path = os.path.join(root, file)
            rel_path = os.path.relpath(root, DATEN_ORDNER)
            label = rel_path.split(os.sep)[0] if rel_path != "." else "Unbekannt"

            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                error_log.append(f"Fehler: Datei konnte nicht geöffnet werden → {video_path}")
                continue

            fps = cap.get(cv2.CAP_PROP_FPS)
            total_frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)
            width = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
            height = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
            duration = total_frames / fps if fps > 0 else 0

            cap.release()

            video_infos.append({
                "Übung": label,
                "Datei": file,
                "FPS": fps,
                "Frames": total_frames,
                "Breite": width,
                "Höhe": height,
                "Dauer_s": duration,
                "Pfad": video_path
            })

# In DataFrame packen
gesammelteDaten = pd.DataFrame(video_infos)

print(f"📦 Gefundene Videos: {len(gesammelteDaten)}")

if len(gesammelteDaten) == 0:
    print("Keine Videos im Ordner 'Datensatz' gefunden! Skript wird beendet.")
    exit()


# ==========================================
# 2. VIDEOS BEREINIGEN MIT VideoCleaner
# ==========================================
print("🧹 Starte Bereinigung...")

bereiniger = VideoCleaner(
    dataframe=gesammelteDaten,
    ausgabe_ordner=AUSGABE_ORDNER,
    logliste=error_log
)

bereiniger.process_all_videos()

print("Bereinigung abgeschlossen.")


# ==========================================
# 3. LOG SCHREIBEN
# ==========================================
log_filename = "log_DatenAngleichen.txt"
log_path = os.path.join(BASE_DIR, log_filename)

with open(log_path, "w", encoding="utf-8") as f:
    for line in error_log:
        f.write(line + "\n")

print(f"Log gespeichert unter: {log_path}")
print(f"Bereinigte Videos befinden sich in: {AUSGABE_ORDNER}")
