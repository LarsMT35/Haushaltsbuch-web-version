import cv2
import mediapipe as mp
import numpy as np

# Mediapipe-Module für Pose und Zeichnung laden
mp_pose = mp.solutions.pose
mp_drawing = mp.solutions.drawing_utils

# Pose-Tracker initialisieren
pose = mp_pose.Pose(static_image_mode=False,
                    model_complexity=1,
                    enable_segmentation=False,
                    min_detection_confidence=0.5,
                    min_tracking_confidence=0.5)

# Webcam starten
cap = cv2.VideoCapture(0)

print("Starte Live-Pose-Erkennung... Drücke ESC zum Beenden.")

while cap.isOpened():
    success, frame = cap.read()
    if not success:
        print("Kein Kamerabild gefunden.")
        break

    # Mediapipe erwartet RGB-Bilder
    image_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    # Pose schätzen
    results = pose.process(image_rgb)

    # Ergebnisse visualisieren
    annotated = frame.copy()
    if results.pose_landmarks:
        mp_drawing.draw_landmarks(
            annotated,
            
            results.pose_landmarks,
            mp_pose.POSE_CONNECTIONS,
            mp_drawing.DrawingSpec(color=(0, 255, 0), thickness=2, circle_radius=2),
            mp_drawing.DrawingSpec(color=(0, 0, 255), thickness=2, circle_radius=2),
        )

        # Keypoints extrahieren (x, y, z, visibility)
        landmarks = results.pose_landmarks.landmark
        keypoints = np.array([[lm.x, lm.y, lm.z, lm.visibility] for lm in landmarks])

        # Beispiel: Ausgabe der ersten 5 Punkte
        print(keypoints[:5])  # kannst du später an dein Modell übergeben

    # Anzeige
    cv2.imshow("Mediapipe Pose Estimation", annotated)

    # ESC zum Beenden
    if cv2.waitKey(1) & 0xFF == 27:
        break

cap.release()
cv2.destroyAllWindows()

### Arbeiten mit Regularisieren... was mach bei unserem Modell Sinn

### Basien Optimasation, Hyperparameter optimierung, Trian, Test, Valis sonst nur Train/Test

### Infos für das Projekt, ggf. mit Corssvalidation arbeiten, da wir nur 650 Viedeos für die verschiedenen Übungen haben.
    ### Falls die Trainingsdaten nicht reichen.
