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


@dataclass(frozen=True)
class DiscoveryConfig:
    probe_timeout_sec: float = 5.0
    progress_delay_sec: float = 0.05


@dataclass(frozen=True)
class ValidationConfig:
    allowed_schemes: tuple[str, ...] = ("rtsp", "http", "https")


@dataclass(frozen=True)
class PersonDetectionConfig:
    enabled_by_default: bool = False
    model_name: str = "yolo11m.pt"
    inference_size: int = 640
    confidence: float = 0.35
    detection_max_width: int = 960
    detect_every_n_frames: int = 3
    max_pending_frames: int = 1


@dataclass(frozen=True)
class AppConfig:
    ui: UIConfig = field(default_factory=UIConfig)
    stream: StreamConfig = field(default_factory=StreamConfig)
    discovery: DiscoveryConfig = field(default_factory=DiscoveryConfig)
    validation: ValidationConfig = field(default_factory=ValidationConfig)
    person_detection: PersonDetectionConfig = field(default_factory=PersonDetectionConfig)


APP_CONFIG = AppConfig()
