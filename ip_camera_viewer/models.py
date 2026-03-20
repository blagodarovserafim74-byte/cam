from dataclasses import dataclass
from enum import Enum
from typing import Any


class StreamEventType(str, Enum):
    CONNECTING = "connecting"
    CONNECTED = "connected"
    FRAME = "frame"
    DISCONNECTED = "disconnected"
    ERROR = "error"


@dataclass(slots=True)
class StreamMessage:
    event: StreamEventType
    frame: Any | None = None
    text: str = ""
