import cv2 #from opencv-python
import os
import shutil
import numpy as np


class VideoCleaner:
    """
    Diese Klasse führt alle Schritte der Datenbereinigung aus:
    1. Auflösung prüfen und ausreißer entfernen/komprimieren
    2. FPS auf 25 vereinheitlichen
    3. Videolängen harmonisieren
    4. Entfernen unbrauchbarer Videos
    5. Sicherstellen, dass Frameanzahl nach Harmonisierung übereinstimmt
    """

    def __init__(self, dataframe, ausgabe_ordner, logliste):
        self.df = dataframe
        self.output_dir = ausgabe_ordner
        self.error_log = logliste

        os.makedirs(self.output_dir, exist_ok=True)
        self.error_log.append(f"[I] Ausgabeordner geprüft/erstellt: {self.output_dir}")

        # Parameter
        self.min_res = (250, 250)      # Minimal empfohlene Auflösung
        self.max_res = (1920, 1080)    # Maximal empfohlene Auflösung
        self.target_fps = 25           # Einheitliches FPS-Ziel
        self.target_duration = None     # Einheitliche Dauer wird dynamisch ermittelt

    # -------------------------------------------------------------
    # 1. Auflösungsbereinigung
    # -------------------------------------------------------------
    def check_resolution(self, video_path, width, height):
        """
        Prüft, ob die Auflösung innerhalb der Empfehlung liegt.
        Niedrige Auflösungen werden entfernt, zu hohe verkleinert.
        """
        if width < self.min_res[0] or height < self.min_res[1]:
            self.error_log.append(f"[W] Video-Auflösung zu gering -> Entfernt: {video_path}")
            return "remove"

        if width > self.max_res[0] or height > self.max_res[1]:
            self.error_log.append(f"[I] Video zu groß -> Kompression nötig: {video_path}")
            return "compress"

        return "ok"

    def compress_resolution(self, cap, out_path, target_width=1920, target_height=1080):
        """Skaliert ein Video auf maximal Full HD herunter."""
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(out_path, fourcc, self.target_fps, (target_width, target_height))

        while True:
            ret, frame = cap.read()
            if not ret:
                break
            resized = cv2.resize(frame, (target_width, target_height))
            writer.write(resized)

        writer.release()

    # -------------------------------------------------------------
    # 2. FPS-Harmonisierung (25 FPS)
    # -------------------------------------------------------------
    def adjust_fps(self, frames, orig_fps):
        """
        Bei höherer FPS → Frames ausdünnen
        Bei niedriger FPS → Frames duplizieren
        """
        if orig_fps == self.target_fps:
            return frames

        ratio = orig_fps / self.target_fps

        if orig_fps > self.target_fps:
            # Frames verringern
            indices = np.arange(0, len(frames), ratio).astype(int)
            return [frames[i] for i in indices if i < len(frames)]

        else:
            # Frames verdoppeln
            factor = int(round(self.target_fps / orig_fps))
            extended = []
            for f in frames:
                extended.extend([f] * factor)
            return extended

    # -------------------------------------------------------------
    # 3 + 4. Videolängen-Harmonisierung
    # -------------------------------------------------------------
    def determine_target_duration(self):
        """Ermittelt die Ziel-Videodauer, indem der Median gewählt wird."""
        self.target_duration = self.df["Dauer_s"].median()
        self.error_log.append(f"[I] Ziel-Videodauer bestimmt: {self.target_duration} Sekunden")

    def trim_or_pad_video(self, frames, fps):
        """Passt die Videolänge an das Zielmaß an."""
        target_frame_count = int(self.target_duration * fps)
        current_count = len(frames)

        # Fall 1: Video ist zu lang -> schneiden
        if current_count > target_frame_count:
            cut_index = (current_count - target_frame_count) // 2
            return frames[cut_index:cut_index + target_frame_count]

        # Fall 2: Video ist zu kurz -> letzte Frames kopieren                   #Später schauen, ob Klassifizierer damit umgehen kann, wenn am Ende Standbild
        if current_count < target_frame_count and current_count > 0:
            missing = target_frame_count - current_count
            return frames + [frames[-1]] * missing

        return frames

    # -------------------------------------------------------------
    # 5. Vollständige Pipeline
    # -------------------------------------------------------------
    def process_all_videos(self):
        """Führt alle Bereinigungsschritte durch."""
        self.determine_target_duration()

        for idx, row in self.df.iterrows():
            path = row["Pfad"]
            width, height = row["Breite"], row["Höhe"]
            fps_original = row["FPS"]

            res_status = self.check_resolution(path, width, height)

            # Entfernen
            if res_status == "remove":
                continue

            cap = cv2.VideoCapture(path)
            if not cap.isOpened():
                self.error_log.append(f"[E] Video konnte nicht geöffnet werden: {path}")
                continue

            # Frames lesen
            frames = []
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                frames.append(frame)

            # Komprimieren falls nötig
            if res_status == "compress":
                self.error_log.append(f"[I] Starte Kompression: {path}")
                compressed_path = os.path.join(self.output_dir, f"COMP_{row['Datei']}")
                cap.release()
                cap = cv2.VideoCapture(path)
                self.compress_resolution(cap, compressed_path)
                cap.release()
                path = compressed_path

            # FPS harmonisieren
            frames = self.adjust_fps(frames, fps_original)

            # Länge harmonisieren
            frames = self.trim_or_pad_video(frames, self.target_fps)

            # Ergebnisvideo speichern
            out_path = os.path.join(self.output_dir, f"BEREINIGT_{row['Datei']}")
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            height_out, width_out = frames[0].shape[:2]
            writer = cv2.VideoWriter(out_path, fourcc, self.target_fps, (width_out, height_out))

            for fr in frames:
                writer.write(fr)

            writer.release()
            self.error_log.append(f"[I] Video bereinigt: {out_path}")

        self.error_log.append("[I] Bereinigungsprozess abgeschlossen.")
