from dataclasses import dataclass
from enum import Enum
from typing import Any


class StreamEventType(str, Enum):
    CONNECTING = "connecting"
    CONNECTED = "connected"
    FRAME = "frame"
    DISCONNECTED = "disconnected"
    ERROR = "error"
    DISCOVERY_STARTED = "discovery_started"
    DISCOVERY_PROGRESS = "discovery_progress"
    DISCOVERY_FOUND = "discovery_found"
    DISCOVERY_NOT_FOUND = "discovery_not_found"


@dataclass(slots=True)
class StreamMessage:
    event: StreamEventType
    frame: Any | None = None
    text: str = ""
    payload: dict[str, Any] | None = None
