import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FFmpegStreamInfo:
    width: int
    height: int


def locate_binary(binary_name: str) -> str | None:
    resolved = shutil.which(binary_name)
    if resolved:
        return resolved

    candidates = [
        Path.cwd() / binary_name,
        Path.cwd() / f"{binary_name}.exe",
        Path(__file__).resolve().parent.parent.parent / binary_name,
        Path(__file__).resolve().parent.parent.parent / f"{binary_name}.exe",
    ]

    for candidate in candidates:
        if candidate.exists():
            return str(candidate)

    return None


def get_ffmpeg_path() -> str | None:
    return locate_binary("ffmpeg")


def get_ffprobe_path() -> str | None:
    return locate_binary("ffprobe")


def probe_stream_info(url: str, timeout_sec: float) -> tuple[FFmpegStreamInfo | None, str]:
    ffprobe_path = get_ffprobe_path()
    if not ffprobe_path:
        return None, (
            "Не найден ffprobe. Установите FFmpeg и добавьте ffmpeg/bin в PATH, "
            "либо положите ffprobe.exe рядом с программой."
        )

    command = [
        ffprobe_path,
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height",
        "-of",
        "csv=p=0:s=x",
        url,
    ]

    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
            creationflags=creationflags,
            env=_ffmpeg_env(),
        )
    except subprocess.TimeoutExpired:
        return None, "ffprobe не успел получить информацию о потоке."
    except Exception as exc:  # noqa: BLE001
        return None, f"Не удалось запустить ffprobe: {exc}"

    output = (completed.stdout or "").strip()
    if completed.returncode != 0 or not output:
        stderr = (completed.stderr or "").strip()
        error_text = stderr or "ffprobe не смог прочитать видеопоток."
        return None, error_text

    try:
        width_text, height_text = output.split("x", maxsplit=1)
        width = int(width_text.strip())
        height = int(height_text.strip())
    except Exception:
        return None, f"Не удалось разобрать размеры видеопотока: {output}"

    if width <= 0 or height <= 0:
        return None, "ffprobe вернул некорректные размеры видеопотока."

    return FFmpegStreamInfo(width=width, height=height), ""


def build_ffmpeg_command(url: str, width: int, height: int) -> list[str]:
    ffmpeg_path = get_ffmpeg_path()
    if not ffmpeg_path:
        raise FileNotFoundError(
            "Не найден ffmpeg. Установите FFmpeg и добавьте ffmpeg/bin в PATH, "
            "либо положите ffmpeg.exe рядом с программой."
        )

    command = [
        ffmpeg_path,
        "-hide_banner",
        "-loglevel",
        "error",
        "-fflags",
        "nobuffer",
        "-flags",
        "low_delay",
    ]

    if url.lower().startswith("rtsp://"):
        command.extend(["-rtsp_transport", "tcp"])

    command.extend(
        [
            "-i",
            url,
            "-an",
            "-sn",
            "-dn",
            "-pix_fmt",
            "rgb24",
            "-vcodec",
            "rawvideo",
            "-f",
            "rawvideo",
            "-",
        ]
    )
    return command


def _ffmpeg_env() -> dict[str, str]:
    env = dict(os.environ)
    return env
