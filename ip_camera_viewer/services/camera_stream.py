import queue
import subprocess
import threading
from typing import Optional

import numpy as np

from ip_camera_viewer.config import StreamConfig
from ip_camera_viewer.models import StreamEventType, StreamMessage
from ip_camera_viewer.utils.ffmpeg import build_ffmpeg_command, probe_stream_info


class CameraStreamWorker(threading.Thread):
    """Фоновый поток чтения видео через FFmpeg."""

    def __init__(self, url: str, output_queue: "queue.Queue[StreamMessage]", stream_config: StreamConfig) -> None:
        super().__init__(daemon=True)
        self.url = url
        self.output_queue = output_queue
        self.stream_config = stream_config
        self.stop_event = threading.Event()
        self.process: Optional[subprocess.Popen[bytes]] = None

    def run(self) -> None:
        self._send(StreamEventType.CONNECTING, text="Подключение к камере через FFmpeg...")

        stream_info, error_text = probe_stream_info(
            url=self.url,
            timeout_sec=self.stream_config.probe_timeout_sec,
        )
        if stream_info is None:
            self._send(
                StreamEventType.ERROR,
                text=(
                    "Не удалось получить параметры потока через FFmpeg/ffprobe. "
                    f"{error_text}"
                ),
            )
            return

        try:
            command = build_ffmpeg_command(
                url=self.url,
                width=stream_info.width,
                height=stream_info.height,
            )
        except FileNotFoundError as exc:
            self._send(StreamEventType.ERROR, text=str(exc))
            return

        frame_size = stream_info.width * stream_info.height * 3
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

        try:
            self.process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,
                bufsize=10**8,
                creationflags=creationflags,
            )
        except Exception as exc:  # noqa: BLE001
            self._send(StreamEventType.ERROR, text=f"Не удалось запустить FFmpeg: {exc}")
            return

        first_frame_sent = False

        try:
            while not self.stop_event.is_set():
                if self.process.stdout is None:
                    self._send(StreamEventType.ERROR, text="FFmpeg не открыл канал чтения кадров.")
                    return

                raw_frame = self.process.stdout.read(frame_size)

                if len(raw_frame) != frame_size:
                    error_text = self._collect_process_error()
                    if self.stop_event.is_set():
                        break

                    self._send(
                        StreamEventType.ERROR,
                        text=(
                            "FFmpeg прекратил отдавать кадры. "
                            f"{error_text}"
                        ).strip(),
                    )
                    return

                frame = np.frombuffer(raw_frame, dtype=np.uint8).reshape(
                    (stream_info.height, stream_info.width, 3)
                ).copy()

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
