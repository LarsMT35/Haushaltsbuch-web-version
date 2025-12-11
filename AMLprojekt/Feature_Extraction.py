import cv2
import os
import numpy as np


class VideoCleaner:

    def __init__(self, dataframe, ausgabe_ordner, logliste):
        self.df = dataframe
        self.output_dir = ausgabe_ordner
        self.error_log = logliste

        os.makedirs(self.output_dir, exist_ok=True)
        self.error_log.append(f"[I] Ausgabeordner geprüft/erstellt: {self.output_dir}")

        self.min_res = (250, 250)
        self.max_res = (1920, 1080)
        self.target_fps = 25
        self.target_duration = None

    # -------------------------------------------------------------
    # Resolution check
    # -------------------------------------------------------------
    def check_resolution(self, video_path, width, height):
        if width < self.min_res[0] or height < self.min_res[1]:
            self.error_log.append(f"[W] Auflösung zu gering → Entfernt: {video_path}")
            return "remove"

        if width > self.max_res[0] or height > self.max_res[1]:
            self.error_log.append(f"[I] Video zu groß → Kompression nötig: {video_path}")
            return "compress"

        return "ok"

    # -------------------------------------------------------------
    # Compression
    # -------------------------------------------------------------
    def compress_resolution(self, cap, out_path, target_width=1920, target_height=1080):
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(out_path, fourcc, self.target_fps,
                                 (target_width, target_height))

        while True:
            ret, frame = cap.read()
            if not ret:
                break
            resized = cv2.resize(frame, (target_width, target_height))
            writer.write(resized)

        writer.release()

    # -------------------------------------------------------------
    # FPS-Harmonisierung
    # -------------------------------------------------------------
    def adjust_fps(self, frames, orig_fps):
        if orig_fps == self.target_fps:
            return frames

        if orig_fps <= 0 or len(frames) == 0:
            return frames

        ratio = orig_fps / self.target_fps

        if orig_fps > self.target_fps:
            indices = np.arange(0, len(frames), ratio).astype(int)
            return [frames[i] for i in indices if i < len(frames)]

        factor = int(round(self.target_fps / orig_fps))
        extended = []
        for f in frames:
            extended.extend([f] * factor)

        return extended

    # -------------------------------------------------------------
    # Harmonisierung (mit Mindestdauer 5s)
    # -------------------------------------------------------------
    def determine_target_duration(self):
        median_duration = self.df["Dauer_s"].median()

        # Mindestlänge 15 Sekunden
        self.target_duration = max(5, median_duration)

        self.error_log.append(
            f"[I] Ziel-Videodauer bestimmt: {self.target_duration}s (Median: {median_duration})"
        )

    def trim_or_pad_video(self, frames, fps):
        if len(frames) == 0:
            return frames

        target_frame_count = int(self.target_duration * fps)
        current_count = len(frames)

        if current_count > target_frame_count:
            cut_idx = (current_count - target_frame_count) // 2
            return frames[cut_idx:cut_idx + target_frame_count]

        if current_count < target_frame_count:
            missing = target_frame_count - current_count
            return frames + [frames[-1]] * missing

        return frames

    # -------------------------------------------------------------
    # Hauptpipeline
    # -------------------------------------------------------------
    def process_all_videos(self):
        self.determine_target_duration()

        for idx, row in self.df.iterrows():
            path = row["Pfad"]
            width, height = int(row["Breite"]), int(row["Höhe"])
            fps_original = row["FPS"]

            res_status = self.check_resolution(path, width, height)
            if res_status == "remove":
                continue

            # Unterordnerstruktur erzeugen
            original_folder = os.path.basename(os.path.dirname(path))
            target_subfolder = os.path.join(self.output_dir, original_folder)
            os.makedirs(target_subfolder, exist_ok=True)

            # Video laden
            cap = cv2.VideoCapture(path)
            if not cap.isOpened():
                self.error_log.append(f"[E] Kann nicht geöffnet werden: {path}")
                continue

            frames = []
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                frames.append(frame)
            cap.release()

            if len(frames) == 0:
                self.error_log.append(f"[E] Keine Frames → Übersprungen: {path}")
                continue

            # Kompression falls nötig
            if res_status == "compress":
                comp_path = os.path.join(target_subfolder, f"COMP_{row['Datei']}")
                cap = cv2.VideoCapture(path)
                self.compress_resolution(cap, comp_path)
                cap.release()
                path = comp_path

                # Frames nach Kompression erneut laden
                cap = cv2.VideoCapture(path)
                frames = []
                while True:
                    ret, frame = cap.read()
                    if not ret:
                        break
                    frames.append(frame)
                cap.release()

            if len(frames) == 0:
                self.error_log.append(f"[E] Komprimiertes Video leer → {path}")
                continue

            # FPS anpassen
            frames = self.adjust_fps(frames, fps_original)

            # Länge harmonisieren
            frames = self.trim_or_pad_video(frames, self.target_fps)

            if len(frames) == 0:
                self.error_log.append(f"[E] Nach Harmonisierung leer → {path}")
                continue

            # Speichern
            out_path = os.path.join(target_subfolder, f"BEREINIGT_{row['Datei']}")
            height_out, width_out = frames[0].shape[:2]

            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            writer = cv2.VideoWriter(out_path, fourcc, self.target_fps,
                                     (width_out, height_out))

            for fr in frames:
                writer.write(fr)
            writer.release()

            self.error_log.append(f"[I] Gespeichert: {out_path}")

        self.error_log.append("[I] Bereinigungsprozess abgeschlossen.")
