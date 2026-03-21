import queue
import threading
from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np
from ultralytics import YOLO

from ip_camera_viewer.config import PersonDetectionConfig


@dataclass(slots=True)
class PersonBox:
    x1: int
    y1: int
    x2: int
    y2: int
    confidence: float


@dataclass(slots=True)
class DetectionSnapshot:
    boxes: list[PersonBox]
    person_count: int
    frame_width: int
    frame_height: int


class PersonDetectorService:
    """Детекция человека через YOLO11m в отдельном потоке."""

    def __init__(self, config: PersonDetectionConfig) -> None:
        self.config = config
        self.frame_queue: "queue.Queue[np.ndarray]" = queue.Queue(maxsize=config.max_pending_frames)
        self.stop_event = threading.Event()
        self.thread: Optional[threading.Thread] = None
        self.model: Optional[YOLO] = None
        self.last_snapshot = DetectionSnapshot(boxes=[], person_count=0, frame_width=0, frame_height=0)
        self.status_text = "YOLO: не запущен"
        self._lock = threading.Lock()

    def start(self) -> None:
        if self.thread and self.thread.is_alive():
            return

        self.stop_event.clear()
        self.thread = threading.Thread(target=self._worker_loop, daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2)
        self.thread = None

    def submit_frame(self, frame_rgb: np.ndarray) -> None:
        if self.stop_event.is_set():
            return

        try:
            if self.frame_queue.full():
                self.frame_queue.get_nowait()
        except queue.Empty:
            pass

        try:
            self.frame_queue.put_nowait(frame_rgb)
        except queue.Full:
            pass

    def get_snapshot(self) -> DetectionSnapshot:
        with self._lock:
            return self.last_snapshot

    def get_status_text(self) -> str:
        with self._lock:
            return self.status_text

    def _worker_loop(self) -> None:
        try:
            self._set_status("YOLO: загрузка модели...")
            self.model = YOLO(self.config.model_name)
            self._set_status(f"YOLO: модель {self.config.model_name} загружена")
        except Exception as exc:  # noqa: BLE001
            self._set_status(f"YOLO: ошибка загрузки модели ({exc})")
            return

        while not self.stop_event.is_set():
            try:
                frame_rgb = self.frame_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            try:
                snapshot = self._detect(frame_rgb)
                with self._lock:
                    self.last_snapshot = snapshot
                    self.status_text = f"YOLO: людей обнаружено {snapshot.person_count}"
            except Exception as exc:  # noqa: BLE001
                self._set_status(f"YOLO: ошибка детекции ({exc})")

    def _detect(self, frame_rgb: np.ndarray) -> DetectionSnapshot:
        height, width = frame_rgb.shape[:2]
        ratio = 1.0

        if width > self.config.detection_max_width:
            ratio = self.config.detection_max_width / width
            resized = cv2.resize(
                frame_rgb,
                (int(width * ratio), int(height * ratio)),
                interpolation=cv2.INTER_AREA,
            )
        else:
            resized = frame_rgb

        # Ultralytics обычно ожидает ndarray в стиле OpenCV
        bgr_frame = cv2.cvtColor(resized, cv2.COLOR_RGB2BGR)

        results = self.model.predict(
            source=bgr_frame,
            imgsz=self.config.inference_size,
            conf=self.config.confidence,
            classes=[0],  # person
            verbose=False,
        )

        result = results[0]
        boxes: list[PersonBox] = []

        if result.boxes is not None and len(result.boxes) > 0:
            xyxy = result.boxes.xyxy.cpu().numpy()
            confs = result.boxes.conf.cpu().numpy()

            inv_ratio = 1.0 / ratio
            for coords, confidence in zip(xyxy, confs, strict=False):
                x1, y1, x2, y2 = coords.tolist()
                boxes.append(
                    PersonBox(
                        x1=int(x1 * inv_ratio),
                        y1=int(y1 * inv_ratio),
                        x2=int(x2 * inv_ratio),
                        y2=int(y2 * inv_ratio),
                        confidence=float(confidence),
                    )
                )

        return DetectionSnapshot(
            boxes=boxes,
            person_count=len(boxes),
            frame_width=width,
            frame_height=height,
        )

    def _set_status(self, text: str) -> None:
        with self._lock:
            self.status_text = text
