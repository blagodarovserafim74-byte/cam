import queue
import tkinter as tk
from tkinter import messagebox
from typing import Optional

from PIL import ImageTk

from ip_camera_viewer.config import APP_CONFIG
from ip_camera_viewer.models import StreamEventType, StreamMessage
from ip_camera_viewer.services.camera_stream import CameraStreamWorker
from ip_camera_viewer.utils.image import frame_to_canvas
from ip_camera_viewer.utils.validators import validate_camera_url


class MainWindow:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(APP_CONFIG.ui.window_title)
        self.root.geometry(APP_CONFIG.ui.window_size)
        self.root.minsize(APP_CONFIG.ui.min_width, APP_CONFIG.ui.min_height)

        self.url_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Статус: не подключено")
        self.message_queue: "queue.Queue[StreamMessage]" = queue.Queue(maxsize=2)
        self.worker: Optional[CameraStreamWorker] = None
        self.current_photo: Optional[ImageTk.PhotoImage] = None

        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.after(APP_CONFIG.ui.queue_poll_ms, self._process_messages)

    def _build_ui(self) -> None:
        root_frame = tk.Frame(self.root, padx=12, pady=12)
        root_frame.pack(fill="both", expand=True)
        root_frame.columnconfigure(0, weight=1)
        root_frame.rowconfigure(1, weight=1)

        controls_frame = tk.LabelFrame(root_frame, text="Подключение к камере", padx=10, pady=10)
        controls_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        controls_frame.columnconfigure(1, weight=1)

        url_label = tk.Label(controls_frame, text="Ссылка на IP-камеру:")
        url_label.grid(row=0, column=0, sticky="w", padx=(0, 8), pady=(0, 6))

        self.url_entry = tk.Entry(controls_frame, textvariable=self.url_var, font=("Segoe UI", 10))
        self.url_entry.grid(row=0, column=1, sticky="ew", pady=(0, 6))

        self.connect_button = tk.Button(
            controls_frame,
            text="Подключиться",
            width=16,
            command=self.connect_camera,
        )
        self.connect_button.grid(row=0, column=2, padx=(8, 6), pady=(0, 6))

        self.disconnect_button = tk.Button(
            controls_frame,
            text="Отключиться",
            width=16,
            state="disabled",
            command=self.disconnect_camera,
        )
        self.disconnect_button.grid(row=0, column=3, pady=(0, 6))

        examples = (
            "Примеры ссылок:\n"
            "rtsp://login:password@192.168.1.10:554/stream\n"
            "http://192.168.1.10:8080/video"
        )
        examples_label = tk.Label(
            controls_frame,
            text=examples,
            justify="left",
            fg="#333333",
        )
        examples_label.grid(row=1, column=0, columnspan=4, sticky="w")

        self.status_label = tk.Label(
            root_frame,
            textvariable=self.status_var,
            anchor="w",
            fg="red",
            font=("Segoe UI", 10, "bold"),
        )
        self.status_label.grid(row=2, column=0, sticky="ew", pady=(0, 10))

        video_frame = tk.LabelFrame(root_frame, text="Видео", padx=10, pady=10)
        video_frame.grid(row=1, column=0, sticky="nsew")
        video_frame.rowconfigure(0, weight=1)
        video_frame.columnconfigure(0, weight=1)

        self.video_label = tk.Label(
            video_frame,
            text="Здесь будет видеопоток",
            bg="black",
            fg="white",
            font=("Segoe UI", 13),
        )
        self.video_label.grid(row=0, column=0, sticky="nsew")

    def connect_camera(self) -> None:
        url = self.url_var.get().strip()
        is_valid, error_text = validate_camera_url(url)

        if not is_valid:
            self._set_status(f"Статус: ошибка — {error_text}", "red")
            messagebox.showwarning("Неверная ссылка", error_text)
            return

        # Перед новым подключением гарантированно останавливаем старый поток.
        self.disconnect_camera(show_status=False)

        self.worker = CameraStreamWorker(
            url=url,
            output_queue=self.message_queue,
            stream_config=APP_CONFIG.stream,
        )
        self.worker.start()

        self.connect_button.config(state="disabled")
        self.disconnect_button.config(state="normal")
        self._set_status("Статус: подключение...", "orange")

    def disconnect_camera(self, show_status: bool = True) -> None:
        if self.worker is not None:
            self.worker.stop()
            self.worker.join(timeout=2)
            self.worker = None

        self.connect_button.config(state="normal")
        self.disconnect_button.config(state="disabled")
        self._clear_queue()
        self._show_placeholder("Здесь будет видеопоток")

        if show_status:
            self._set_status("Статус: отключено", "red")

    def _process_messages(self) -> None:
        try:
            while True:
                message = self.message_queue.get_nowait()

                if message.event == StreamEventType.CONNECTING:
                    self._set_status("Статус: подключение...", "orange")

                elif message.event == StreamEventType.CONNECTED:
                    self._set_status("Статус: подключено", "green")

                elif message.event == StreamEventType.FRAME:
                    self._show_frame(message)

                elif message.event == StreamEventType.ERROR:
                    self._set_status("Статус: ошибка подключения", "red")
                    self.disconnect_camera(show_status=False)
                    messagebox.showerror("Ошибка подключения", message.text)

                elif message.event == StreamEventType.DISCONNECTED:
                    if self.worker is None:
                        self._set_status("Статус: отключено", "red")

        except queue.Empty:
            pass
        finally:
            self.root.after(APP_CONFIG.ui.queue_poll_ms, self._process_messages)

    def _show_frame(self, message: StreamMessage) -> None:
        max_width = max(self.video_label.winfo_width(), APP_CONFIG.ui.video_area_min_width)
        max_height = max(self.video_label.winfo_height(), APP_CONFIG.ui.video_area_min_height)

        # Преобразуем кадр OpenCV в изображение, подходящее для Tkinter.
        canvas = frame_to_canvas(message.frame, max_width=max_width, max_height=max_height)
        self.current_photo = ImageTk.PhotoImage(canvas)
        self.video_label.config(image=self.current_photo, text="")

    def _show_placeholder(self, text: str) -> None:
        self.current_photo = None
        self.video_label.config(image="", text=text)

    def _set_status(self, text: str, color: str) -> None:
        self.status_var.set(text)
        self.status_label.config(fg=color)

    def _clear_queue(self) -> None:
        while not self.message_queue.empty():
            try:
                self.message_queue.get_nowait()
            except queue.Empty:
                break

    def on_close(self) -> None:
        self.disconnect_camera(show_status=False)
        self.root.destroy()
