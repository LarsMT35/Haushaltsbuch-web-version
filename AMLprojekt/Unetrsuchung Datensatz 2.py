import cv2
import os
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

# === Pfade ===
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATEN_ORDNER = os.path.join(BASE_DIR, "Datensatz")
REPORT_ORDNER = os.path.join(BASE_DIR, "reports")

# Ensure report folder exists
os.makedirs(REPORT_ORDNER, exist_ok=True)

# === Datensammlung ===
video_infos = []

for root, dirs, files in os.walk(DATEN_ORDNER):
    for file in files:
        if file.lower().endswith(('.mp4', '.avi', '.mov', '.mkv')):
            video_path = os.path.join(root, file)

            # Art der Übung
            label = os.path.basename(os.path.dirname(video_path))

            # Dateigröße in MB
            file_size_mb = os.path.getsize(video_path) / (1024 * 1024)

            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                print(f"Konnte Video nicht öffnen: {video_path}")
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
                "Dateigröße_MB": round(file_size_mb, 2),
                "Frames": frame_count,
                "FPS": round(fps, 2),
                "Dauer_s": round(duration, 2),
                "Breite": width,
                "Höhe": height,
                "Auflösung": f"{width}x{height}",
                "Pfad": video_path
            })

# === DataFrame ===
df = pd.DataFrame(video_infos)
if df.empty:
    print("Keine Videos gefunden.")
    exit()

print("Übersicht:")
print(df.head())

# --------------------------------------------------------
# 1. Balkendiagramm: Wiedergabezeit (Mean + Std)
# --------------------------------------------------------
mean_std_duration = df.groupby("Übung")["Dauer_s"].agg(["mean", "std"])

plt.figure(figsize=(12, 6))
mean_std_duration["mean"].plot(kind="bar", yerr=mean_std_duration["std"], capsize=4, color="skyblue")
plt.title("Durchschnittliche Wiedergabezeit pro Übung")
plt.xlabel("Übung")
plt.ylabel("Dauer (Sekunden)")
plt.xticks(rotation=45, ha="right")
plt.tight_layout()
plt.savefig(os.path.join(REPORT_ORDNER, "wiedergabezeit_bar.png"))
plt.close()


# --------------------------------------------------------
# 2. Heatmap: Auflösung
# --------------------------------------------------------
resolution_counts = df.groupby(["Breite", "Höhe"]).size().reset_index(name="Anzahl")
pivot = resolution_counts.pivot(index="Höhe", columns="Breite", values="Anzahl")

plt.figure(figsize=(10, 8))
sns.heatmap(pivot, annot=True, fmt="g", cmap="Blues")
plt.title("Heatmap der Auflösungsverteilung")
plt.xlabel("Breite (px)")
plt.ylabel("Höhe (px)")
plt.tight_layout()
plt.savefig(os.path.join(REPORT_ORDNER, "aufloesung_heatmap.png"))
plt.close()


# --------------------------------------------------------
# 3. Balkendiagramm: Dateigröße (Mean + STD)
# --------------------------------------------------------
mean_std_size = df.groupby("Übung")["Dateigröße_MB"].agg(["mean", "std"])

plt.figure(figsize=(12, 6))
mean_std_size["mean"].plot(kind="bar", yerr=mean_std_size["std"], capsize=4)
plt.title("Durchschnittliche Dateigröße pro Übung")
plt.xlabel("Übung")
plt.ylabel("Dateigröße (MB)")
plt.xticks(rotation=45, ha="right")
plt.tight_layout()
plt.savefig(os.path.join(REPORT_ORDNER, "dateigroesse_bar.png"))
plt.close()


# --------------------------------------------------------
# 4. Histogramm-Overlay: FPS
# --------------------------------------------------------
plt.figure(figsize=(12, 6))
for uebung in df["Übung"].unique():
    sns.histplot(df[df["Übung"] == uebung]["FPS"], kde=False, label=uebung, bins=10, alpha=0.5)

plt.title("FPS-Verteilung pro Übung")
plt.xlabel("FPS")
plt.ylabel("Anzahl")
plt.legend(title="Übung")
plt.tight_layout()
plt.savefig(os.path.join(REPORT_ORDNER, "fps_histogramm.png"))
plt.close()


# --------------------------------------------------------
# 5. Balkendiagramm: Frameanzahl (Mean + STD)
# --------------------------------------------------------
mean_std_frames = df.groupby("Übung")["Frames"].agg(["mean", "std"])

plt.figure(figsize=(12, 6))
mean_std_frames["mean"].plot(kind="bar", yerr=mean_std_frames["std"], capsize=4)
plt.title("Durchschnittliche Frameanzahl pro Übung")
plt.xlabel("Übung")
plt.ylabel("Frames")
plt.xticks(rotation=45, ha="right")
plt.tight_layout()
plt.savefig(os.path.join(REPORT_ORDNER, "frameanzahl_bar.png"))
plt.close()

# # === Plot-Funktion ===
# def save_plot(x, y, title, ylabel, filename):
#     plt.figure(figsize=(12, 6))
#     sns.boxplot(data=df, x=x, y=y)
#     sns.stripplot(data=df, x=x, y=y, color="black", size=3, alpha=0.5)

#     plt.title(title, fontsize=14)
#     plt.xlabel(x, fontsize=12)
#     plt.ylabel(ylabel, fontsize=12)
#     plt.xticks(rotation=45, ha="right")
#     plt.tight_layout()

#     out_path = os.path.join(REPORT_ORDNER, filename)
#     plt.savefig(out_path)
#     plt.close()
#     print(f"Gespeichert: {out_path}")


# # === KPI Grafiken erzeugen ===

# # 1. Wiedergabezeit
# save_plot(
#     x="Übung",
#     y="Dauer_s",
#     title="Verteilung der Wiedergabezeit pro Übung",
#     ylabel="Dauer (Sekunden)",
#     filename="wiedergabezeit.png"
# )

# # 2. Auflösung (Breite)
# save_plot(
#     x="Übung",
#     y="Breite",
#     title="Verteilung der Videobreite pro Übung",
#     ylabel="Breite (px)",
#     filename="aufloesung_breite.png"
# )

# # 2b. Auflösung (Höhe)
# save_plot(
#     x="Übung",
#     y="Höhe",
#     title="Verteilung der Videohöhe pro Übung",
#     ylabel="Höhe (px)",
#     filename="aufloesung_hoehe.png"
# )

# # 3. Dateigröße
# save_plot(
#     x="Übung",
#     y="Dateigröße_MB",
#     title="Verteilung der Dateigröße pro Übung",
#     ylabel="Dateigröße (MB)",
#     filename="dateigroesse.png"
# )

# # 4. FPS
# save_plot(
#     x="Übung",
#     y="FPS",
#     title="Verteilung der FPS pro Übung",
#     ylabel="FPS",
#     filename="fps.png"
# )

# # 5. Frameanzahl
# save_plot(
#     x="Übung",
#     y="Frames",
#     title="Verteilung der Frameanzahl pro Übung",
#     ylabel="Frames",
#     filename="frameanzahl.png"
# )

# # 6. Art der Übung (bereits x-Achse)

print("Alle KPI-Grafiken wurden im Ordner 'reports' gespeichert.")
