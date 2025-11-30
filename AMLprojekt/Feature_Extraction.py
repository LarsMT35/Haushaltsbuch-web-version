import os
import cv2
import mediapipe as mp
import numpy as np

# Ordnerpfade
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATEN_ORDNER = os.path.join(BASE_DIR, "Datensatz")
AUSGABE_ORDNER = os.path.join(BASE_DIR, "RAW_Data")


# Mediapipe initialisieren
mp_pose = mp.solutions.pose
pose = mp_pose.Pose(static_image_mode=False, min_detection_confidence=0.5)
mp_drawing = mp.solutions.drawing_utils

# RAW_Data-Ordner anlegen, falls nicht vorhanden
os.makedirs(AUSGABE_ORDNER, exist_ok=True)

# Alle Unterordner (Übungen) durchlaufen
for label in os.listdir(DATEN_ORDNER):
    label_pfad = os.path.join(DATEN_ORDNER, label)
    if not os.path.isdir(label_pfad):
        continue  # Überspringt Dateien

    print(f"Verarbeite Übung: {label}")

    # Ausgabe-Unterordner für diese Übung anlegen
    ziel_ordner = os.path.join(AUSGABE_ORDNER, label)
    os.makedirs(ziel_ordner, exist_ok=True)

    # Alle Videos im Unterordner verarbeiten
    for datei in os.listdir(label_pfad):
        if not datei.lower().endswith((".mp4", ".avi", ".mov")):
            continue

        video_pfad = os.path.join(label_pfad, datei)
        print(f"{datei}")

        cap = cv2.VideoCapture(video_pfad)
        frame_daten = []

        while cap.isOpened():
            success, frame = cap.read()
            if not success:
                break

            # Mediapipe erwartet RGB
            image_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            result = pose.process(image_rgb)

            if result.pose_landmarks:
                keypoints = np.array(
                    [[lm.x, lm.y, lm.z, lm.visibility] for lm in result.pose_landmarks.landmark]
                )
            else:
                # Leeres Frame, falls keine Pose erkannt
                keypoints = np.zeros((33, 4))

            frame_daten.append(keypoints)

        cap.release()

        # In NumPy-Array umwandeln (Frames × 33 × 4)
        daten_array = np.array(frame_daten)

        # Ergebnis speichern
        basisname = os.path.splitext(datei)[0]
        ausgabe_datei = os.path.join(ziel_ordner, f"{basisname}.npy")
        np.save(ausgabe_datei, daten_array)

        print(f"Gespeichert unter: {ausgabe_datei}")

print("Fertig! Alle Videos verarbeitet.")
