import queue
import threading
import time
from typing import Optional

import cv2

from ip_camera_viewer.config import StreamConfig
from ip_camera_viewer.models import StreamEventType, StreamMessage


class CameraStreamWorker(threading.Thread):
    """Фоновый поток чтения видео с IP-камеры."""

    def __init__(self, url: str, output_queue: "queue.Queue[StreamMessage]", stream_config: StreamConfig) -> None:
        super().__init__(daemon=True)
        self.url = url
        self.output_queue = output_queue
        self.stream_config = stream_config
        self.stop_event = threading.Event()
        self.capture: Optional[cv2.VideoCapture] = None

    def run(self) -> None:
        # Сообщаем интерфейсу, что началась попытка подключения.
        self._send(StreamEventType.CONNECTING, text="Подключение к камере...")

        capture = self._open_capture()
        if capture is None:
            self._send(
                StreamEventType.ERROR,
                text=(
                    "Не удалось открыть видеопоток. Проверьте ссылку, логин, пароль, "
                    "порт и доступность камеры."
                ),
            )
            return

        self.capture = capture

        try:
            # Сначала ждём первый реальный кадр, чтобы убедиться, что поток живой.
            if not self._wait_for_first_frame():
                self._send(
                    StreamEventType.ERROR,
                    text=(
                        "Соединение установлено, но камера не отдаёт кадры. "
                        "Проверьте правильность URL потока."
                    ),
                )
                return

            failed_reads = 0

            while not self.stop_event.is_set():
                ok, frame = self.capture.read()

                if not ok or frame is None:
                    failed_reads += 1
                    if failed_reads >= self.stream_config.max_failed_reads:
                        self._send(
                            StreamEventType.ERROR,
                            text="Поток прерван или камера перестала отвечать.",
                        )
                        return

                    time.sleep(self.stream_config.read_retry_delay_sec)
                    continue

                failed_reads = 0
                self._send(StreamEventType.FRAME, frame=frame)
                time.sleep(self.stream_config.loop_sleep_sec)

        except Exception as exc:  # noqa: BLE001
            self._send(StreamEventType.ERROR, text=f"Ошибка во время чтения потока: {exc}")
        finally:
            self._release_capture()
            self._send(StreamEventType.DISCONNECTED, text="Поток остановлен.")

    def stop(self) -> None:
        self.stop_event.set()
        self._release_capture()

    def _open_capture(self) -> Optional[cv2.VideoCapture]:
        # Сначала пробуем FFMPEG, затем обычное открытие как запасной вариант.
        backend = getattr(cv2, "CAP_FFMPEG", 0)
        capture = cv2.VideoCapture(self.url, backend)

        if capture.isOpened():
            return capture

        capture.release()
        fallback_capture = cv2.VideoCapture(self.url)
        if fallback_capture.isOpened():
            return fallback_capture

        fallback_capture.release()
        return None

    def _wait_for_first_frame(self) -> bool:
        for _ in range(self.stream_config.warmup_attempts):
            if self.stop_event.is_set():
                return False

            ok, frame = self.capture.read()
            if ok and frame is not None:
                self._send(StreamEventType.CONNECTED, text="Камера подключена.")
                self._send(StreamEventType.FRAME, frame=frame)
                return True

            time.sleep(self.stream_config.warmup_delay_sec)

        return False

    def _release_capture(self) -> None:
        if self.capture is not None:
            try:
                self.capture.release()
            except Exception:
                pass
            finally:
                self.capture = None

    def _send(self, event: StreamEventType, frame=None, text: str = "") -> None:
        message = StreamMessage(event=event, frame=frame, text=text)

        # Для видео держим очередь маленькой, чтобы не копить старые кадры.
        if event == StreamEventType.FRAME and self.output_queue.full():
            try:
                self.output_queue.get_nowait()
            except queue.Empty:
                pass

        try:
            self.output_queue.put_nowait(message)
        except queue.Full:
            pass
