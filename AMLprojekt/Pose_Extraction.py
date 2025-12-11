import os
import cv2
import csv
import mediapipe as mp
from mediapipe.tasks.python import vision

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VIDEO_ORDNER = os.path.join(BASE_DIR, "Bereinigt")
POSE_ORDNER = os.path.join(BASE_DIR, "Pose")
os.makedirs(POSE_ORDNER, exist_ok=True)

MODEL_PATH = "Test/AMLprojekt/pose_landmarker_full.task"

# Tasks API initialisieren
options = vision.PoseLandmarkerOptions(
    base_options=mp.tasks.BaseOptions(model_asset_path=MODEL_PATH),
    running_mode=vision.RunningMode.VIDEO
)
landmarker = vision.PoseLandmarker.create_from_options(options)

for file in os.listdir(VIDEO_ORDNER):
    if not file.lower().endswith((".mp4", ".avi", ".mov", ".mkv")):
        continue

    video_path = os.path.join(VIDEO_ORDNER, file)
    csv_path = os.path.join(POSE_ORDNER, file.replace((".mp4", ".avi", ".mov", ".mkv"), ".csv"))

    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    frame_idx = 0
    rows = []

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        timestamp_ms = int(frame_idx / fps * 1000)
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_rgb)

        results = landmarker.detect_for_video(mp_image, timestamp_ms)

        if results.pose_landmarks:
            flat = []
            for lm in results.pose_landmarks:
                flat.extend([lm.x, lm.y, lm.z, lm.visibility])
        else:
            flat = [0.0] * (33*4)

        rows.append([frame_idx / fps] + flat)
        frame_idx += 1

    cap.release()

    # CSV schreiben
    cols = ["timestamp"]
    for i in range(33):
        cols += [f"lm{i}_x", f"lm{i}_y", f"lm{i}_z", f"lm{i}_vis"]

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(cols)
        writer.writerows(rows)

    print(f"[OK] CSV gespeichert: {csv_path}")

landmarker.close()
