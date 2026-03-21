import queue
import threading
import time
from dataclasses import dataclass
from urllib.parse import urlparse

from ip_camera_viewer.config import DiscoveryConfig
from ip_camera_viewer.models import StreamEventType, StreamMessage
from ip_camera_viewer.utils.ffmpeg import probe_stream_available


@dataclass(frozen=True)
class DiscoveryRequest:
    host: str
    username: str = ""
    password: str = ""


class URLDiscoveryWorker(threading.Thread):
    """Ищет рабочую ссылку потока для указанного хоста камеры."""

    def __init__(
        self,
        request: DiscoveryRequest,
        output_queue: "queue.Queue[StreamMessage]",
        config: DiscoveryConfig,
    ) -> None:
        super().__init__(daemon=True)
        self.request = request
        self.output_queue = output_queue
        self.config = config
        self.stop_event = threading.Event()

    def run(self) -> None:
        self._send(StreamEventType.DISCOVERY_STARTED, text="Идёт поиск рабочей ссылки...")

        candidates = self._build_candidates(
            host_input=self.request.host,
            username=self.request.username,
            password=self.request.password,
        )

        checked_count = 0
        for candidate in candidates:
            if self.stop_event.is_set():
                return

            checked_count += 1
            self._send(
                StreamEventType.DISCOVERY_PROGRESS,
                text=f"Проверяется: {candidate}",
                payload={"checked": checked_count, "url": candidate},
            )

            if self._probe_candidate(candidate):
                self._send(
                    StreamEventType.DISCOVERY_FOUND,
                    text=candidate,
                    payload={"url": candidate},
                )
                return

            time.sleep(self.config.progress_delay_sec)

        self._send(
            StreamEventType.DISCOVERY_NOT_FOUND,
            text=(
                "Не удалось автоматически найти рабочую ссылку. "
                "Проверьте адрес камеры, логин/пароль и документацию производителя."
            ),
        )

    def stop(self) -> None:
        self.stop_event.set()

    def _probe_candidate(self, url: str) -> bool:
        ok, _ = probe_stream_available(url=url, timeout_sec=self.config.probe_timeout_sec)
        return ok

    @staticmethod
    def _build_candidates(host_input: str, username: str, password: str) -> list[str]:
        normalized_host, direct_url = URLDiscoveryWorker._normalize_host(host_input)

        credentials = ""
        if username:
            credentials = username
            if password:
                credentials += f":{password}"
            credentials += "@"

        candidates: list[str] = []

        if direct_url:
            candidates.append(direct_url)

        rtsp_candidates = [
            f"rtsp://{credentials}{normalized_host}:554/stream",
            f"rtsp://{credentials}{normalized_host}:554/live/ch00_0",
            f"rtsp://{credentials}{normalized_host}:554/Streaming/Channels/101",
            f"rtsp://{credentials}{normalized_host}:554/Streaming/Channels/102",
            f"rtsp://{credentials}{normalized_host}:554/h264Preview_01_main",
            f"rtsp://{credentials}{normalized_host}:554/cam/realmonitor?channel=1&subtype=0",
        ]
        http_candidates = [
            f"http://{normalized_host}:8080/video",
            f"http://{normalized_host}/video",
            f"http://{normalized_host}:4747/video",
            f"http://{normalized_host}:81/stream",
            f"http://{normalized_host}/mjpeg",
        ]

        for item in rtsp_candidates + http_candidates:
            if item not in candidates:
                candidates.append(item)

        return candidates

    @staticmethod
    def _normalize_host(host_input: str) -> tuple[str, str | None]:
        raw = host_input.strip()

        if "://" in raw:
            parsed = urlparse(raw)
            host = parsed.hostname or parsed.netloc or raw
            direct_url = raw
            return host, direct_url

        if "/" in raw:
            cleaned = raw.split("/")[0]
            return cleaned, None

        return raw, None

    def _send(self, event: StreamEventType, text: str = "", payload=None) -> None:
        try:
            self.output_queue.put_nowait(StreamMessage(event=event, text=text, payload=payload))
        except queue.Full:
            try:
                self.output_queue.get_nowait()
            except queue.Empty:
                pass
            try:
                self.output_queue.put_nowait(StreamMessage(event=event, text=text, payload=payload))
            except queue.Full:
                pass
