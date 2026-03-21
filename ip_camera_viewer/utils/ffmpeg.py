import os
import shutil
import subprocess
from pathlib import Path


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


def probe_stream_available(url: str, timeout_sec: float) -> tuple[bool, str]:
    ffmpeg_path = get_ffmpeg_path()
    if not ffmpeg_path:
        return False, (
            "Не найден ffmpeg. Установите FFmpeg и добавьте ffmpeg/bin в PATH, "
            "либо положите ffmpeg.exe рядом с программой."
        )

    command = [
        ffmpeg_path,
        "-hide_banner",
        "-loglevel",
        "error",
    ]

    if url.lower().startswith("rtsp://"):
        command.extend(["-rtsp_transport", "tcp", "-timeout", "15000000"])

    command.extend(
        [
            "-analyzeduration",
            "10000000",
            "-probesize",
            "10000000",
            "-i",
            url,
            "-frames:v",
            "1",
            "-an",
            "-sn",
            "-dn",
            "-f",
            "image2pipe",
            "-vcodec",
            "mjpeg",
            "-",
        ]
    )

    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            timeout=timeout_sec,
            check=False,
            creationflags=creationflags,
            env=dict(os.environ),
        )
    except subprocess.TimeoutExpired:
        return False, "FFmpeg не успел получить первый кадр от камеры."
    except Exception as exc:  # noqa: BLE001
        return False, f"Не удалось запустить FFmpeg: {exc}"

    stdout_data = completed.stdout or b""
    stderr_data = (completed.stderr or b"").decode("utf-8", errors="ignore").strip()

    if stdout_data:
        return True, ""

    return False, stderr_data or "FFmpeg не смог получить первый кадр видеопотока."


def build_ffmpeg_mjpeg_pipe_command(url: str) -> list[str]:
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
    ]

    if url.lower().startswith("rtsp://"):
        command.extend(["-rtsp_transport", "tcp", "-timeout", "15000000"])

    command.extend(
        [
            "-analyzeduration",
            "10000000",
            "-probesize",
            "10000000",
            "-i",
            url,
            "-an",
            "-sn",
            "-dn",
            "-vf",
            "fps=15",
            "-f",
            "image2pipe",
            "-vcodec",
            "mjpeg",
            "-q:v",
            "5",
            "-",
        ]
    )
    return command
