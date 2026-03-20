import queue
import threading
import tkinter as tk
from dataclasses import dataclass
from tkinter import ttk
from typing import Optional

import cv2
from PIL import Image, ImageTk


@dataclass
class FrameMessage:
    """Message passed from the camera thread to the GUI thread."""

    frame: Optional["cv2.typing.MatLike"] = None
    error: Optional[str] = None
    status: Optional[str] = None


class CameraWorker(threading.Thread):
    """Background worker that reads frames from the camera stream."""

    def __init__(self, stream_url: str, output_queue: queue.Queue, stop_event: threading.Event):
        super().__init__(daemon=True)
        self.stream_url = stream_url
        self.output_queue = output_queue
        self.stop_event = stop_event
        self.capture: Optional[cv2.VideoCapture] = None

    def run(self) -> None:
        try:
            self.capture = cv2.VideoCapture(self.stream_url, cv2.CAP_FFMPEG)

            if not self.capture.isOpened():
                self.output_queue.put(
                    FrameMessage(
                        error=(
                            "Не удалось открыть видеопоток. Проверьте ссылку, логин, пароль "
                            "и доступность IP-камеры."
                        )
                    )
                )
                return

            self.output_queue.put(FrameMessage(status="connected"))

            while not self.stop_event.is_set():
                ok, frame = self.capture.read()
                if not ok or frame is None:
                    self.output_queue.put(
                        FrameMessage(
                            error=(
                                "Поток недоступен или чтение кадров прервано. "
                                "Камера могла отключиться или ссылка может быть неверной."
                            )
                        )
                    )
                    return

                if self.output_queue.full():
                    try:
                        self.output_queue.get_nowait()
                    except queue.Empty:
                        pass

                self.output_queue.put(FrameMessage(frame=frame))

        except Exception as exc:  # noqa: BLE001 - friendly UI error is needed
            self.output_queue.put(FrameMessage(error=f"Ошибка подключения: {exc}"))
        finally:
            if self.capture is not None:
                self.capture.release()


class IPCameraApp:
    """Stylized desktop application for viewing an IP camera stream."""

    BG_COLOR = "#0f172a"
    PANEL_COLOR = "#111827"
    PANEL_ALT_COLOR = "#1f2937"
    INPUT_COLOR = "#0b1220"
    TEXT_PRIMARY = "#f8fafc"
    TEXT_SECONDARY = "#cbd5e1"
    ACCENT = "#38bdf8"
    SUCCESS = "#22c55e"
    WARNING = "#f59e0b"
    ERROR = "#ef4444"

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Просмотр IP-камеры")
        self.root.geometry("1180x760")
        self.root.minsize(980, 640)
        self.root.configure(bg=self.BG_COLOR)

        self.frame_queue: queue.Queue[FrameMessage] = queue.Queue(maxsize=3)
        self.stop_event = threading.Event()
        self.worker: Optional[CameraWorker] = None
        self.photo_image: Optional[ImageTk.PhotoImage] = None

        self.url_var = tk.StringVar(value="rtsp://login:password@192.168.1.10:554/stream")
        self.status_var = tk.StringVar(value="● Не подключено")
        self.status_hint_var = tk.StringVar(
            value="Вставьте ссылку на поток камеры и нажмите «Подключиться»."
        )

        self._configure_styles()
        self._build_ui()
        self._set_status("idle")

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.after(30, self.process_queue)

    def _configure_styles(self) -> None:
        style = ttk.Style(self.root)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        elif "clam" in style.theme_names():
            style.theme_use("clam")

        default_font = ("Segoe UI", 10)
        title_font = ("Segoe UI Semibold", 11)
        style.configure("App.TFrame", background=self.BG_COLOR)
        style.configure("Panel.TFrame", background=self.PANEL_COLOR)
        style.configure("Surface.TFrame", background=self.PANEL_ALT_COLOR)
        style.configure(
            "Title.TLabel",
            background=self.BG_COLOR,
            foreground=self.TEXT_PRIMARY,
            font=("Segoe UI Semibold", 22),
        )
        style.configure(
            "Subtitle.TLabel",
            background=self.BG_COLOR,
            foreground=self.TEXT_SECONDARY,
            font=default_font,
        )
        style.configure(
            "PanelTitle.TLabel",
            background=self.PANEL_COLOR,
            foreground=self.TEXT_PRIMARY,
            font=title_font,
        )
        style.configure(
            "PanelText.TLabel",
            background=self.PANEL_COLOR,
            foreground=self.TEXT_SECONDARY,
            font=default_font,
        )
        style.configure(
            "Hint.TLabel",
            background=self.PANEL_ALT_COLOR,
            foreground=self.TEXT_SECONDARY,
            font=("Segoe UI", 9),
        )
        style.configure(
            "Status.TLabel",
            background=self.PANEL_ALT_COLOR,
            foreground=self.TEXT_PRIMARY,
            font=("Segoe UI Semibold", 11),
        )
        style.configure(
            "StatusHint.TLabel",
            background=self.PANEL_ALT_COLOR,
            foreground=self.TEXT_SECONDARY,
            font=("Segoe UI", 9),
        )
        style.configure(
            "Primary.TButton",
            font=("Segoe UI Semibold", 10),
            padding=(16, 10),
        )
        style.map(
            "Primary.TButton",
            foreground=[("active", "#082f49")],
            background=[("active", "#7dd3fc")],
        )
        style.configure(
            "Secondary.TButton",
            font=("Segoe UI Semibold", 10),
            padding=(16, 10),
        )
        style.configure(
            "Camera.TEntry",
            fieldbackground=self.INPUT_COLOR,
            foreground=self.TEXT_PRIMARY,
            borderwidth=0,
            insertcolor=self.TEXT_PRIMARY,
            padding=10,
        )

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root, style="App.TFrame", padding=18)
        outer.pack(fill=tk.BOTH, expand=True)
        outer.columnconfigure(0, weight=2)
        outer.columnconfigure(1, weight=5)
        outer.rowconfigure(1, weight=1)

        self._build_header(outer)
        self._build_sidebar(outer)
        self._build_workspace(outer)

    def _build_header(self, parent: ttk.Frame) -> None:
        header = ttk.Frame(parent, style="App.TFrame")
        header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 16))
        header.columnconfigure(0, weight=1)

        ttk.Label(header, text="IP Camera Viewer", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            header,
            text="Красиво оформленная рабочая область для подключения к RTSP / HTTP-потоку камеры.",
            style="Subtitle.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(6, 0))

    def _build_sidebar(self, parent: ttk.Frame) -> None:
        sidebar = ttk.Frame(parent, style="Panel.TFrame", padding=18)
        sidebar.grid(row=1, column=0, sticky="nsew", padx=(0, 14))
        sidebar.columnconfigure(0, weight=1)

        ttk.Label(sidebar, text="Подключение", style="PanelTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            sidebar,
            text="Вставьте ссылку на поток камеры. Поддерживаются RTSP и HTTP/MJPEG потоки.",
            style="PanelText.TLabel",
            wraplength=300,
            justify="left",
        ).grid(row=1, column=0, sticky="ew", pady=(8, 16))

        ttk.Label(sidebar, text="URL камеры", style="PanelText.TLabel").grid(row=2, column=0, sticky="w")
        self.url_entry = ttk.Entry(sidebar, textvariable=self.url_var, style="Camera.TEntry")
        self.url_entry.grid(row=3, column=0, sticky="ew", pady=(8, 8), ipady=5)

        ttk.Button(sidebar, text="Подключиться", command=self.connect_camera, style="Primary.TButton").grid(
            row=4, column=0, sticky="ew", pady=(6, 8)
        )
        ttk.Button(sidebar, text="Отключиться", command=self.disconnect_camera, style="Secondary.TButton").grid(
            row=5, column=0, sticky="ew"
        )

        self._build_example_card(sidebar, row=6)
        self._build_tips_card(sidebar, row=7)

        sidebar.rowconfigure(8, weight=1)

    def _build_example_card(self, parent: ttk.Frame, row: int) -> None:
        card = tk.Frame(parent, bg=self.PANEL_ALT_COLOR, highlightthickness=1, highlightbackground="#334155")
        card.grid(row=row, column=0, sticky="ew", pady=(18, 12))
        card.grid_columnconfigure(0, weight=1)

        tk.Label(
            card,
            text="Примеры ссылок",
            bg=self.PANEL_ALT_COLOR,
            fg=self.TEXT_PRIMARY,
            font=("Segoe UI Semibold", 11),
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=14, pady=(14, 6))

        tk.Label(
            card,
            text="RTSP: rtsp://login:password@192.168.1.10:554/stream",
            bg=self.PANEL_ALT_COLOR,
            fg=self.ACCENT,
            font=("Consolas", 9),
            anchor="w",
            justify="left",
            wraplength=280,
        ).grid(row=1, column=0, sticky="ew", padx=14, pady=4)

        tk.Label(
            card,
            text="HTTP: http://192.168.1.10:8080/video",
            bg=self.PANEL_ALT_COLOR,
            fg=self.ACCENT,
            font=("Consolas", 9),
            anchor="w",
            justify="left",
            wraplength=280,
        ).grid(row=2, column=0, sticky="ew", padx=14, pady=(0, 14))

    def _build_tips_card(self, parent: ttk.Frame, row: int) -> None:
        card = tk.Frame(parent, bg=self.PANEL_ALT_COLOR, highlightthickness=1, highlightbackground="#334155")
        card.grid(row=row, column=0, sticky="ew")
        card.grid_columnconfigure(0, weight=1)

        tk.Label(
            card,
            text="Подсказки",
            bg=self.PANEL_ALT_COLOR,
            fg=self.TEXT_PRIMARY,
            font=("Segoe UI Semibold", 11),
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=14, pady=(14, 6))

        tips = (
            "• Для RTSP обычно нужны логин и пароль.\n"
            "• Если поток не открывается, проверьте порт и сетевую доступность камеры.\n"
            "• После отключения поток останавливается без зависания окна."
        )
        tk.Label(
            card,
            text=tips,
            bg=self.PANEL_ALT_COLOR,
            fg=self.TEXT_SECONDARY,
            font=("Segoe UI", 9),
            justify="left",
            anchor="w",
            wraplength=280,
        ).grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 14))

    def _build_workspace(self, parent: ttk.Frame) -> None:
        workspace = ttk.Frame(parent, style="App.TFrame")
        workspace.grid(row=1, column=1, sticky="nsew")
        workspace.columnconfigure(0, weight=1)
        workspace.rowconfigure(1, weight=1)

        status_card = ttk.Frame(workspace, style="Surface.TFrame", padding=16)
        status_card.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        status_card.columnconfigure(0, weight=1)

        self.status_badge = tk.Label(
            status_card,
            textvariable=self.status_var,
            bg=self.PANEL_ALT_COLOR,
            fg=self.WARNING,
            font=("Segoe UI Semibold", 12),
            anchor="w",
        )
        self.status_badge.grid(row=0, column=0, sticky="ew")

        ttk.Label(status_card, textvariable=self.status_hint_var, style="StatusHint.TLabel", wraplength=720).grid(
            row=1, column=0, sticky="ew", pady=(8, 0)
        )

        video_shell = tk.Frame(
            workspace,
            bg="#020617",
            highlightthickness=1,
            highlightbackground="#1e293b",
            bd=0,
        )
        video_shell.grid(row=1, column=0, sticky="nsew")
        video_shell.grid_rowconfigure(1, weight=1)
        video_shell.grid_columnconfigure(0, weight=1)

        top_bar = tk.Frame(video_shell, bg="#0b1220", height=54)
        top_bar.grid(row=0, column=0, sticky="ew")
        top_bar.grid_columnconfigure(1, weight=1)

        tk.Label(
            top_bar,
            text="Рабочая область камеры",
            bg="#0b1220",
            fg=self.TEXT_PRIMARY,
            font=("Segoe UI Semibold", 12),
        ).grid(row=0, column=0, sticky="w", padx=(18, 12), pady=14)

        tk.Label(
            top_bar,
            text="Живой поток отображается здесь",
            bg="#0b1220",
            fg=self.TEXT_SECONDARY,
            font=("Segoe UI", 9),
        ).grid(row=0, column=1, sticky="w", pady=14)

        self.video_label = tk.Label(
            video_shell,
            text="\nПодключите IP-камеру, чтобы увидеть видео в этой области.\n\n"
            "Ссылка вставляется в левую панель, в поле «URL камеры».",
            bg="#020617",
            fg="#94a3b8",
            font=("Segoe UI", 15),
            justify="center",
        )
        self.video_label.grid(row=1, column=0, sticky="nsew", padx=18, pady=(10, 18))

    def connect_camera(self) -> None:
        stream_url = self.url_var.get().strip()
        if not stream_url:
            self._set_status(
                "error",
                "Введите ссылку на IP-камеру перед подключением.",
            )
            self.url_entry.focus_set()
            return

        self.disconnect_camera(clear_status=False)
        self._set_status("connecting", "Выполняется подключение к камере. Подождите несколько секунд.")

        self.stop_event = threading.Event()
        self.worker = CameraWorker(stream_url, self.frame_queue, self.stop_event)
        self.worker.start()

    def disconnect_camera(self, clear_status: bool = True) -> None:
        if self.worker and self.worker.is_alive():
            self.stop_event.set()
            self.worker.join(timeout=2)

        self.worker = None
        self._clear_queue()
        self._show_placeholder(
            "Видео остановлено.\n\nНажмите «Подключиться», чтобы снова открыть поток камеры."
        )

        if clear_status:
            self._set_status("idle")

    def process_queue(self) -> None:
        try:
            while True:
                message = self.frame_queue.get_nowait()

                if message.error:
                    self.disconnect_camera(clear_status=False)
                    self._set_status("error", message.error)
                    break

                if message.status == "connected":
                    self._set_status(
                        "connected",
                        "Соединение установлено. Видео с IP-камеры выводится в рабочую область справа.",
                    )

                if message.frame is not None:
                    self.show_frame(message.frame)
        except queue.Empty:
            pass
        finally:
            self.root.after(30, self.process_queue)

    def show_frame(self, frame) -> None:
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        max_width = max(self.video_label.winfo_width(), 720)
        max_height = max(self.video_label.winfo_height(), 520)
        resized_frame = self._resize_to_fit(rgb_frame, max_width, max_height)

        image = Image.fromarray(resized_frame)
        self.photo_image = ImageTk.PhotoImage(image=image)
        self.video_label.configure(image=self.photo_image, text="")

    @staticmethod
    def _resize_to_fit(frame, max_width: int, max_height: int):
        height, width = frame.shape[:2]
        scale = min(max_width / width, max_height / height)
        scale = max(scale, 0.1)
        new_size = (int(width * scale), int(height * scale))
        return cv2.resize(frame, new_size, interpolation=cv2.INTER_AREA)

    def _clear_queue(self) -> None:
        while not self.frame_queue.empty():
            try:
                self.frame_queue.get_nowait()
            except queue.Empty:
                return

    def _show_placeholder(self, text: str) -> None:
        self.photo_image = None
        self.video_label.configure(image="", text=text)

    def _set_status(self, mode: str, hint: Optional[str] = None) -> None:
        status_config = {
            "idle": ("● Не подключено", self.WARNING, "Вставьте ссылку на поток камеры и нажмите «Подключиться»."),
            "connecting": ("● Подключение...", self.ACCENT, hint or "Идёт попытка открыть видеопоток."),
            "connected": (
                "● Камера подключена",
                self.SUCCESS,
                hint or "Соединение установлено, кадры успешно отображаются.",
            ),
            "error": (
                "● Ошибка подключения",
                self.ERROR,
                hint or "Не удалось открыть поток камеры.",
            ),
        }
        status_text, color, status_hint = status_config[mode]
        self.status_var.set(status_text)
        self.status_hint_var.set(status_hint)
        self.status_badge.configure(fg=color)

    def on_close(self) -> None:
        self.disconnect_camera()
        self.root.destroy()


if __name__ == "__main__":
    app_root = tk.Tk()
    application = IPCameraApp(app_root)
    app_root.mainloop()
