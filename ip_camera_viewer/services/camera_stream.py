import queue
import subprocess
import threading
from io import BytesIO
from typing import Optional

import numpy as np
from PIL import Image

from ip_camera_viewer.config import StreamConfig
from ip_camera_viewer.models import StreamEventType, StreamMessage
from ip_camera_viewer.utils.ffmpeg import (
    build_ffmpeg_mjpeg_pipe_command,
    probe_stream_available,
)


class CameraStreamWorker(threading.Thread):
    """Фоновый поток чтения видео через FFmpeg image2pipe."""

    def __init__(self, url: str, output_queue: "queue.Queue[StreamMessage]", stream_config: StreamConfig) -> None:
        super().__init__(daemon=True)
        self.url = url
        self.output_queue = output_queue
        self.stream_config = stream_config
        self.stop_event = threading.Event()
        self.process: Optional[subprocess.Popen[bytes]] = None

    def run(self) -> None:
        self._send(StreamEventType.CONNECTING, text="Подключение к камере через FFmpeg...")

        ok, error_text = probe_stream_available(
            url=self.url,
            timeout_sec=self.stream_config.probe_timeout_sec,
        )
        if not ok:
            self._send(
                StreamEventType.ERROR,
                text=f"Не удалось получить первый кадр через FFmpeg. {error_text}".strip(),
            )
            return

        try:
            command = build_ffmpeg_mjpeg_pipe_command(self.url)
        except FileNotFoundError as exc:
            self._send(StreamEventType.ERROR, text=str(exc))
            return

        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

        try:
            self.process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,
                bufsize=0,
                creationflags=creationflags,
            )
        except Exception as exc:  # noqa: BLE001
            self._send(StreamEventType.ERROR, text=f"Не удалось запустить FFmpeg: {exc}")
            return

        buffer = bytearray()
        first_frame_sent = False

        try:
            while not self.stop_event.is_set():
                if self.process.stdout is None:
                    self._send(StreamEventType.ERROR, text="FFmpeg не открыл канал чтения кадров.")
                    return

                chunk = self.process.stdout.read(4096)

                if not chunk:
                    if self.stop_event.is_set():
                        break

                    error_text = self._collect_process_error()
                    self._send(
                        StreamEventType.ERROR,
                        text=(f"FFmpeg прекратил отдавать кадры. {error_text}").strip(),
                    )
                    return

                buffer.extend(chunk)

                while True:
                    start = buffer.find(b"\xff\xd8")
                    if start == -1:
                        if len(buffer) > 2_000_000:
                            buffer.clear()
                        break

                    end = buffer.find(b"\xff\xd9", start + 2)
                    if end == -1:
                        if start > 0:
                            del buffer[:start]
                        break

                    jpeg_bytes = bytes(buffer[start:end + 2])
                    del buffer[:end + 2]

                    frame = self._decode_jpeg_frame(jpeg_bytes)
                    if frame is None:
                        continue

                    if not first_frame_sent:
                        self._send(StreamEventType.CONNECTED, text="Камера подключена через FFmpeg.")
                        first_frame_sent = True

                    self._send(StreamEventType.FRAME, frame=frame)

        except Exception as exc:  # noqa: BLE001
            if not self.stop_event.is_set():
                self._send(StreamEventType.ERROR, text=f"Ошибка во время чтения потока FFmpeg: {exc}")
        finally:
            self._terminate_process()
            self._send(StreamEventType.DISCONNECTED, text="Поток остановлен.")

    def stop(self) -> None:
        self.stop_event.set()
        self._terminate_process()

    def _decode_jpeg_frame(self, jpeg_bytes: bytes):
        try:
            with Image.open(BytesIO(jpeg_bytes)) as image:
                rgb_image = image.convert("RGB")
                return np.array(rgb_image)
        except Exception:
            return None

    def _terminate_process(self) -> None:
        if self.process is None:
            return

        try:
            if self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=1.5)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=1.5)
        except Exception:
            pass
        finally:
            self.process = None

    def _collect_process_error(self) -> str:
        if self.process is None or self.process.stderr is None:
            return ""

        try:
            stderr_data = self.process.stderr.read().decode("utf-8", errors="ignore").strip()
            return stderr_data
        except Exception:
            return ""

    def _send(self, event: StreamEventType, frame=None, text: str = "") -> None:
        message = StreamMessage(event=event, frame=frame, text=text)

        if event == StreamEventType.FRAME and self.output_queue.full():
            try:
                self.output_queue.get_nowait()
            except queue.Empty:
                pass

        try:
            self.output_queue.put_nowait(message)
        except queue.Full:
            pass
