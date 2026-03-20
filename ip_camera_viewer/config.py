from dataclasses import dataclass, field


@dataclass(frozen=True)
class UIConfig:
    window_title: str = "IP Camera Viewer"
    window_size: str = "1180x760"
    min_width: int = 980
    min_height: int = 680
    queue_poll_ms: int = 30
    video_area_min_width: int = 720
    video_area_min_height: int = 520


@dataclass(frozen=True)
class StreamConfig:
    probe_timeout_sec: float = 8.0
    read_chunk_timeout_sec: float = 10.0


@dataclass(frozen=True)
class DiscoveryConfig:
    probe_timeout_sec: float = 5.0
    progress_delay_sec: float = 0.05


@dataclass(frozen=True)
class ValidationConfig:
    allowed_schemes: tuple[str, ...] = ("rtsp", "http", "https")


@dataclass(frozen=True)
class AppConfig:
    ui: UIConfig = field(default_factory=UIConfig)
    stream: StreamConfig = field(default_factory=StreamConfig)
    discovery: DiscoveryConfig = field(default_factory=DiscoveryConfig)
    validation: ValidationConfig = field(default_factory=ValidationConfig)


APP_CONFIG = AppConfig()
