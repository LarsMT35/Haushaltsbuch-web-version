import cv2
import os
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

# === Pfade ===
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATEN_ORDNER = os.path.join(BASE_DIR, "Datensatz")

# === Datensammlung ===
video_infos = []

for root, dirs, files in os.walk(DATEN_ORDNER):
    for file in files:
        if file.lower().endswith(('.mp4', '.avi', '.mov', '.mkv')):
            video_path = os.path.join(root, file)
            label = os.path.basename(os.path.dirname(video_path))  # Ordnername = Übung

            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                print(f"⚠️ Konnte Video nicht öffnen: {video_path}")
                continue

            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = cap.get(cv2.CAP_PROP_FPS)
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            duration = frame_count / fps if fps > 0 else 0

            cap.release()

            video_infos.append({
                "Übung": label,
                "Datei": file,
                "Frames": frame_count,
                "FPS": round(fps, 2),
                "Dauer (s)": round(duration, 2),
                "Auflösung": f"{width}x{height}",
                "Pfad": video_path
            })

# === DataFrame erstellen ===
df = pd.DataFrame(video_infos)
if df.empty:
    print("❌ Keine Videos im Datensatz gefunden!")
    exit()

print("\n📊 Übersicht über die Videos:")
print(df.head())

# === Statistiken ===
print("\n🔍 Zusammenfassung pro Übung:")
print(df.groupby("Übung")[["Frames", "Dauer (s)"]].describe())

# === Plot: Verteilung der Videolängen pro Übung ===
plt.figure(figsize=(12, 7))
sns.boxplot(data=df, x="Übung", y="Dauer (s)", palette="viridis")
sns.stripplot(data=df, x="Übung", y="Dauer (s)", color="black", size=4, alpha=0.5)

plt.title("📦 Verteilung der Videolängen pro Übung", fontsize=14)
plt.xlabel("Übung", fontsize=12)
plt.ylabel("Videolänge (Sekunden)", fontsize=12)
plt.xticks(rotation=45, ha="right")
plt.tight_layout()
plt.show()
