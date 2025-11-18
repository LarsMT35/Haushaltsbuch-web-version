import os
import cv2
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from fpdf import FPDF

# ==== EINSTELLUNGEN ====
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATEN_ORDNER = os.path.join(BASE_DIR, "Datensatz")
AUSGABE_ORDNER = "Reports"
os.makedirs(AUSGABE_ORDNER, exist_ok=True)

# ==== DATEN SAMMELN ====
daten = []

for uebung in os.listdir(DATEN_ORDNER):
    uebungspfad = os.path.join(DATEN_ORDNER, uebung)
    if not os.path.isdir(uebungspfad):
        continue

    for video_datei in os.listdir(uebungspfad):
        if not video_datei.lower().endswith((".mp4", ".avi", ".mov", ".mkv")):
            continue

        video_pfad = os.path.join(uebungspfad, video_datei)
        cap = cv2.VideoCapture(video_pfad)

        if not cap.isOpened():
            print(f"⚠️ Konnte {video_datei} nicht öffnen")
            continue

        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        dauer = frame_count / fps if fps > 0 else 0

        daten.append({
            "Übung": uebung,
            "Datei": video_datei,
            "Frames": frame_count,
            "FPS": fps,
            "Dauer (s)": dauer,
            "Auflösung": f"{width}x{height}",
            "Breite": width,
            "Höhe": height
        })

        cap.release()

# ==== DATAFRAME ====
df = pd.DataFrame(daten)
print(df.head())

# ==== PLOTS ====
sns.set(style="whitegrid")

# Plot 1: Anzahl & durchschnittliche Länge je Übung
plt.figure(figsize=(10, 6))
sns.barplot(
    data=df,
    x="Übung",
    y="Frames",
    hue="Übung",
    palette="viridis",
    legend=False
)
plt.title("📊 Anzahl der Frames pro Übung")
plt.ylabel("Anzahl Frames")
plt.xticks(rotation=45)
plt.tight_layout()
plt.savefig(os.path.join(AUSGABE_ORDNER, "frames_per_uebung.png"))
plt.close()

# Plot 2: FPS-Verteilung
plt.figure(figsize=(10, 6))
sns.boxplot(
    data=df,
    x="Übung",
    y="FPS",
    hue="Übung",
    palette="crest",
    legend=False
)
plt.title("🎞️ FPS-Verteilung pro Übung")
plt.ylabel("Frames per Second")
plt.xticks(rotation=45)
plt.tight_layout()
plt.savefig(os.path.join(AUSGABE_ORDNER, "fps_per_uebung.png"))
plt.close()

# Plot 3: Videodauer-Verteilung
plt.figure(figsize=(10, 6))
sns.boxplot(
    data=df,
    x="Übung",
    y="Dauer (s)",
    hue="Übung",
    palette="mako",
    legend=False
)
plt.title("⏱️ Dauer der Videos pro Übung (Sekunden)")
plt.ylabel("Dauer (s)")
plt.xticks(rotation=45)
plt.tight_layout()
plt.savefig(os.path.join(AUSGABE_ORDNER, "duration_per_uebung.png"))
plt.close()

# Plot 4: Auflösungsverteilung
plt.figure(figsize=(10, 6))
sns.scatterplot(
    data=df,
    x="Breite",
    y="Höhe",
    hue="Übung",
    palette="tab10"
)
plt.title("🖼️ Auflösungen der Videos")
plt.tight_layout()
plt.savefig(os.path.join(AUSGABE_ORDNER, "resolution_scatter.png"))
plt.close()

# ==== PDF REPORT ====
pdf_path = os.path.join(AUSGABE_ORDNER, "Dataset_Report.pdf")
pdf = FPDF()
pdf.add_page()
pdf.set_font("Helvetica", "B", 18)
pdf.cell(0, 10, "📊 Datensatzanalyse – Fitnessübungen", ln=True, align="C")

pdf.set_font("Helvetica", size=12)
pdf.multi_cell(0, 10, "\nÜberblick über den vorhandenen Videodatensatz.")
pdf.ln(5)

pdf.cell(0, 10, "1️⃣ Übersicht (Anzahl, Frames, FPS, Dauer):", ln=True)
pdf.image(os.path.join(AUSGABE_ORDNER, "frames_per_uebung.png"), w=180)
pdf.ln(10)

pdf.cell(0, 10, "2️⃣ FPS-Verteilung:", ln=True)
pdf.image(os.path.join(AUSGABE_ORDNER, "fps_per_uebung.png"), w=180)
pdf.ln(10)

pdf.cell(0, 10, "3️⃣ Dauer der Videos:", ln=True)
pdf.image(os.path.join(AUSGABE_ORDNER, "duration_per_uebung.png"), w=180)
pdf.ln(10)

pdf.cell(0, 10, "4️⃣ Auflösungsverteilung:", ln=True)
pdf.image(os.path.join(AUSGABE_ORDNER, "resolution_scatter.png"), w=180)

pdf.ln(10)
pdf.set_font("Helvetica", "I", 10)
pdf.cell(0, 10, "Automatisch generiert mit Python 🐍", ln=True, align="C")

pdf.output(pdf_path)
print(f"✅ PDF-Report erstellt: {pdf_path}")
