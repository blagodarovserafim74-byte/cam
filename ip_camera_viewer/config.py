from dataclasses import dataclass, field


@dataclass(frozen=True)
class UIConfig:
    window_title: str = "IP Camera Viewer"
    window_size: str = "1100x720"
    min_width: int = 900
    min_height: int = 620
    queue_poll_ms: int = 30
    video_area_min_width: int = 720
    video_area_min_height: int = 480


@dataclass(frozen=True)
class StreamConfig:
    warmup_attempts: int = 30
    warmup_delay_sec: float = 0.10
    max_failed_reads: int = 20
    read_retry_delay_sec: float = 0.05
    loop_sleep_sec: float = 0.01


@dataclass(frozen=True)
class ValidationConfig:
    allowed_schemes: tuple[str, ...] = ("rtsp", "http", "https")


@dataclass(frozen=True)
class AppConfig:
    ui: UIConfig = field(default_factory=UIConfig)
    stream: StreamConfig = field(default_factory=StreamConfig)
    validation: ValidationConfig = field(default_factory=ValidationConfig)


APP_CONFIG = AppConfig()
