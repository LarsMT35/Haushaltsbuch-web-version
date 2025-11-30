import cv2
import os
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns


# === Log Handling ===
error_log = []

# === Pfade ===
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATEN_ORDNER = os.path.join(BASE_DIR, "Datensatz")
REPORT_ORDNER = os.path.join(BASE_DIR, "Reports")

# Report Ordner prüfen, erstellen
os.makedirs(REPORT_ORDNER, exist_ok=True)
error_log.append(f"[I] Report-Ordner geprüft/erstellt: {REPORT_ORDNER}")

# === Datensammlung ===
video_infos = []

for root, dirs, files in os.walk(DATEN_ORDNER):
    for file in files:
        if file.lower().endswith(('.mp4', '.avi', '.mov', '.mkv')):
            video_path = os.path.join(root, file)
            label = os.path.basename(os.path.dirname(video_path))

            try:
                file_size_mb = os.path.getsize(video_path) / (1024 * 1024)
            except Exception as e:
                error_log.append(f"[E] Konnte Dateigröße nicht bestimmen: {video_path} | {str(e)}")
                file_size_mb = None

            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                error_log.append(f"[E] Konnte Video nicht öffnen: {video_path}")
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
                "Dateigröße_MB": round(file_size_mb, 2) if file_size_mb else None,
                "Frames": frame_count,
                "FPS": round(fps, 2),
                "Dauer_s": round(duration, 2),
                "Breite": width,
                "Höhe": height,
                "Auflösung": f"{width}x{height}",
                "Pfad": video_path
            })
            error_log.append(f"[I] Video verarbeitet: {video_path} | Dauer: {round(duration,2)}s | FPS: {round(fps,2)}")

# === DataFrame ===
gesammelteDaten = pd.DataFrame(video_infos)
if gesammelteDaten.empty:
    error_log.append(f"[W] Keine Videos gefunden _ Pandas DataFrame leer.")
    with open("_log.txt", "w", encoding="utf-8") as f:
        for line in error_log:
            f.write(line + "\n")
    exit()

error_log.append(f"[I] Insgesamt Videos verarbeitet: {len(gesammelteDaten)}")

# Gemeinsame Funktion zum Zeichnen von Histogrammen/Balken mit Zahlenbeschriftung
def plot_histogram(data, titel, xlabel, ylabel, dateiname, bins=30, range=None, 
                   xtick_step=None, ytick_step=None):
    plt.figure(figsize=(12, 6))
    counts, edges, patches = plt.hist(data, bins=bins, range=range, color="royalblue", alpha=0.7)
    
    # Zahlenbeschriftung für jeden Balken
    for rect, count in zip(patches, counts):
        height = rect.get_height()
        if height > 0:
            plt.text(rect.get_x() + rect.get_width()/2, height + 0.02*max(counts), str(int(count)), 
                     ha='center', va='bottom', fontsize=9)
    
    # X-Achse: mehr Ticks
    if xtick_step:
        plt.xticks(ticks=[edges[0] + i*xtick_step for i in range(int((edges[-1]-edges[0])/xtick_step)+1)])
    
    # Y-Achse: mehr Ticks
    if ytick_step:
        ymax = max(counts)
        plt.yticks(ticks=[i for i in range(0, int(ymax)+1, ytick_step)])
    
    plt.title(titel)
    plt.xlabel(xlabel)
    plt.ylabel(ylabel)
    plt.tight_layout()
    plt.savefig(os.path.join(REPORT_ORDNER, dateiname))
    plt.close()
    error_log.append(f"[I] Diagramm erstellt: {dateiname}")

# -----------------------------
# 1. Videolängen
# -----------------------------
plot_histogram(
    data=gesammelteDaten["Dauer_s"],
    titel="Verteilung der Videolängen (Anzahl Videos)",
    xlabel="Videodauer (Sekunden)",
    ylabel="Anzahl Videos",
    dateiname="videolaengen_verteilung.png",
    bins=30,
    range=(0, 100)
)

# -----------------------------
# 2. FPS
# -----------------------------
plot_histogram(
    data=gesammelteDaten["FPS"],
    titel="FPS-Verteilung (Anzahl Videos)",
    xlabel="FPS",
    ylabel="Anzahl Videos",
    dateiname="fps_verteilung.png",
    bins=10
)

# -----------------------------
# 3. Anzahl Videos pro Übung
# -----------------------------
plt.figure(figsize=(12, 6))
video_counts = gesammelteDaten["Übung"].value_counts()
bars = plt.bar(video_counts.index, video_counts.values, color="royalblue", alpha=0.7)

# Zahlenbeschriftung für jeden Balken
for bar in bars:
    height = bar.get_height()
    plt.text(bar.get_x() + bar.get_width()/2, height + 0.05*max(video_counts.values), str(int(height)), 
             ha='center', va='bottom', fontsize=9)

plt.title("Anzahl der Videos pro Übung")
plt.xlabel("Übung")
plt.ylabel("Anzahl Videos")
plt.xticks(rotation=45, ha="right")
plt.tight_layout()
plt.savefig(os.path.join(REPORT_ORDNER, "anzahl_videos_pro_uebung.png"))
plt.close()
error_log.append(f"[I] Diagramm erstellt: anzahl_videos_pro_uebung.png")

# -----------------------------
# 4. Heatmap: Auflösung (Höhe x Breite)
# -----------------------------
# Zähle wie viele Videos jede Kombination aus Breite und Höhe haben
resolution_counts = gesammelteDaten.groupby(["Höhe", "Breite"]).size().reset_index(name='Anzahl')

# Pivot-Tabelle für Heatmap: Zeilen = Höhe, Spalten = Breite, Werte = Anzahl
resolution_pivot = resolution_counts.pivot(index='Höhe', columns='Breite', values='Anzahl').fillna(0)

plt.figure(figsize=(12, 8))
sns.heatmap(resolution_pivot, annot=True, fmt=".0f", cmap="Blues")
plt.title("Heatmap der Videoauflösungen (Höhe vs. Breite)")
plt.xlabel("Breite")
plt.ylabel("Höhe")
plt.tight_layout()
plt.savefig(os.path.join(REPORT_ORDNER, "auflösung_heatmap.png"))
plt.close()
error_log.append(f"[I] Heatmap Auflösung erstellt: auflösung_heatmap.png")

# -----------------------------
# 5. Dateigröße
# -----------------------------
plot_histogram(
    data=gesammelteDaten["Dateigröße_MB"],
    titel="Verteilung der Dateigröße (Anzahl Videos)",
    xlabel="Dateigröße (MB)",
    ylabel="Anzahl Videos",
    dateiname="dateigroesse_verteilung.png",
    bins=30
)

# -----------------------------
# Log speichern
# -----------------------------
with open("_log.txt", "w", encoding="utf-8") as f:
    for line in error_log:
        f.write(line + "\n")

print("Log gespeichert: _log.txt")
