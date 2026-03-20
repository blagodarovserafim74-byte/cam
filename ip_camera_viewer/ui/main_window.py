import queue
import tkinter as tk
from tkinter import messagebox
from typing import Optional

from PIL import ImageTk

from ip_camera_viewer.config import APP_CONFIG
from ip_camera_viewer.models import StreamEventType, StreamMessage
from ip_camera_viewer.services.camera_stream import CameraStreamWorker
from ip_camera_viewer.services.url_discovery import DiscoveryRequest, URLDiscoveryWorker
from ip_camera_viewer.utils.image import frame_to_canvas
from ip_camera_viewer.utils.validators import validate_camera_url, validate_discovery_host


class MainWindow:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(APP_CONFIG.ui.window_title)
        self.root.geometry(APP_CONFIG.ui.window_size)
        self.root.minsize(APP_CONFIG.ui.min_width, APP_CONFIG.ui.min_height)

        self.url_var = tk.StringVar()
        self.discovery_host_var = tk.StringVar()
        self.discovery_user_var = tk.StringVar()
        self.discovery_password_var = tk.StringVar()
        self.discovery_result_var = tk.StringVar(value="Найденная ссылка появится здесь.")
        self.status_var = tk.StringVar(value="Статус: не подключено")
        self.message_queue: "queue.Queue[StreamMessage]" = queue.Queue(maxsize=20)

        self.stream_worker: Optional[CameraStreamWorker] = None
        self.discovery_worker: Optional[URLDiscoveryWorker] = None
        self.current_photo: Optional[ImageTk.PhotoImage] = None

        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.after(APP_CONFIG.ui.queue_poll_ms, self._process_messages)

    def _build_ui(self) -> None:
        root_frame = tk.Frame(self.root, padx=12, pady=12)
        root_frame.pack(fill="both", expand=True)
        root_frame.columnconfigure(0, weight=1)
        root_frame.rowconfigure(2, weight=1)

        connection_frame = tk.LabelFrame(root_frame, text="Подключение к камере", padx=10, pady=10)
        connection_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        connection_frame.columnconfigure(1, weight=1)

        tk.Label(connection_frame, text="Ссылка на IP-камеру:").grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.url_entry = tk.Entry(connection_frame, textvariable=self.url_var, font=("Segoe UI", 10))
        self.url_entry.grid(row=0, column=1, sticky="ew")

        self.connect_button = tk.Button(
            connection_frame,
            text="Подключиться",
            width=16,
            command=self.connect_camera,
        )
        self.connect_button.grid(row=0, column=2, padx=(8, 6))

        self.disconnect_button = tk.Button(
            connection_frame,
            text="Отключиться",
            width=16,
            state="disabled",
            command=self.disconnect_camera,
        )
        self.disconnect_button.grid(row=0, column=3)

        examples = (
            "Примеры ссылок:\n"
            "rtsp://login:password@192.168.1.10:554/stream\n"
            "http://192.168.1.10:8080/video"
        )
        tk.Label(connection_frame, text=examples, justify="left", fg="#333333").grid(
            row=1, column=0, columnspan=4, sticky="w", pady=(8, 0)
        )

        discovery_frame = tk.LabelFrame(root_frame, text="Поиск ссылки прямо в программе", padx=10, pady=10)
        discovery_frame.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        discovery_frame.columnconfigure(1, weight=1)

        tk.Label(discovery_frame, text="Адрес или IP камеры:").grid(row=0, column=0, sticky="w", padx=(0, 8))
        tk.Entry(discovery_frame, textvariable=self.discovery_host_var, font=("Segoe UI", 10)).grid(
            row=0, column=1, sticky="ew"
        )

        tk.Label(discovery_frame, text="Логин:").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=(8, 0))
        tk.Entry(discovery_frame, textvariable=self.discovery_user_var, font=("Segoe UI", 10)).grid(
            row=1, column=1, sticky="ew", pady=(8, 0)
        )

        tk.Label(discovery_frame, text="Пароль:").grid(row=1, column=2, sticky="w", padx=(8, 8), pady=(8, 0))
        tk.Entry(
            discovery_frame,
            textvariable=self.discovery_password_var,
            font=("Segoe UI", 10),
            show="*",
        ).grid(row=1, column=3, sticky="ew", pady=(8, 0))
        discovery_frame.columnconfigure(3, weight=1)

        self.find_button = tk.Button(
            discovery_frame,
            text="Найти ссылку",
            width=16,
            command=self.find_camera_url,
        )
        self.find_button.grid(row=0, column=2, columnspan=2, padx=(8, 0))

        tk.Label(
            discovery_frame,
            text=(
                "Укажи IP/адрес своей камеры, а программа проверит типовые RTSP/HTTP-ссылки "
                "для этого хоста через FFmpeg/ffprobe. Сканирование всей сети не используется."
            ),
            justify="left",
            fg="#333333",
        ).grid(row=2, column=0, columnspan=4, sticky="w", pady=(8, 0))

        tk.Label(discovery_frame, text="Найденная ссылка:").grid(row=3, column=0, sticky="w", pady=(8, 0))
        tk.Label(
            discovery_frame,
            textvariable=self.discovery_result_var,
            justify="left",
            wraplength=950,
            fg="#0b5ed7",
        ).grid(row=3, column=1, columnspan=3, sticky="w", pady=(8, 0))

        self.status_label = tk.Label(
            root_frame,
            textvariable=self.status_var,
            anchor="w",
            fg="red",
            font=("Segoe UI", 10, "bold"),
        )
        self.status_label.grid(row=3, column=0, sticky="ew", pady=(0, 10))

        video_frame = tk.LabelFrame(root_frame, text="Видео", padx=10, pady=10)
        video_frame.grid(row=2, column=0, sticky="nsew")
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

        self.disconnect_camera(show_status=False)

        self.stream_worker = CameraStreamWorker(
            url=url,
            output_queue=self.message_queue,
            stream_config=APP_CONFIG.stream,
        )
        self.stream_worker.start()

        self.connect_button.config(state="disabled")
        self.disconnect_button.config(state="normal")
        self._set_status("Статус: подключение...", "orange")

    def disconnect_camera(self, show_status: bool = True) -> None:
        if self.stream_worker is not None:
            self.stream_worker.stop()
            self.stream_worker.join(timeout=2)
            self.stream_worker = None

        self.connect_button.config(state="normal")
        self.disconnect_button.config(state="disabled")
        self._clear_queue_frames()
        self._show_placeholder("Здесь будет видеопоток")

        if show_status:
            self._set_status("Статус: отключено", "red")

    def find_camera_url(self) -> None:
        host = self.discovery_host_var.get().strip()
        username = self.discovery_user_var.get().strip()
        password = self.discovery_password_var.get().strip()

        is_valid, error_text = validate_discovery_host(host)
        if not is_valid:
            self._set_status(f"Статус: ошибка — {error_text}", "red")
            messagebox.showwarning("Неверный адрес", error_text)
            return

        self.stop_discovery()
        self.discovery_result_var.set("Поиск ещё не завершён...")

        request = DiscoveryRequest(host=host, username=username, password=password)
        self.discovery_worker = URLDiscoveryWorker(
            request=request,
            output_queue=self.message_queue,
            config=APP_CONFIG.discovery,
        )
        self.discovery_worker.start()

        self.find_button.config(state="disabled")
        self._set_status("Статус: поиск ссылки...", "orange")

    def stop_discovery(self) -> None:
        if self.discovery_worker is not None:
            self.discovery_worker.stop()
            self.discovery_worker.join(timeout=1)
            self.discovery_worker = None

        self.find_button.config(state="normal")

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
                    if self.stream_worker is None:
                        self._set_status("Статус: отключено", "red")

                elif message.event == StreamEventType.DISCOVERY_STARTED:
                    self._set_status("Статус: поиск ссылки...", "orange")

                elif message.event == StreamEventType.DISCOVERY_PROGRESS:
                    checked_url = message.payload.get("url", "") if message.payload else ""
                    self.discovery_result_var.set(f"Проверяется: {checked_url}")

                elif message.event == StreamEventType.DISCOVERY_FOUND:
                    found_url = message.payload.get("url", message.text) if message.payload else message.text
                    self.url_var.set(found_url)
                    self.discovery_result_var.set(found_url)
                    self.stop_discovery()
                    self._set_status("Статус: ссылка найдена", "green")
                    messagebox.showinfo(
                        "Ссылка найдена",
                        "Рабочая ссылка найдена и автоматически вставлена в поле подключения.",
                    )

                elif message.event == StreamEventType.DISCOVERY_NOT_FOUND:
                    self.stop_discovery()
                    self.discovery_result_var.set("Автоматически найти ссылку не удалось.")
                    self._set_status("Статус: ссылка не найдена", "red")
                    messagebox.showwarning("Ссылка не найдена", message.text)

        except queue.Empty:
            pass
        finally:
            self.root.after(APP_CONFIG.ui.queue_poll_ms, self._process_messages)

    def _show_frame(self, message: StreamMessage) -> None:
        max_width = max(self.video_label.winfo_width(), APP_CONFIG.ui.video_area_min_width)
        max_height = max(self.video_label.winfo_height(), APP_CONFIG.ui.video_area_min_height)

        canvas = frame_to_canvas(message.frame, max_width=max_width, max_height=max_height)
        self.current_photo = ImageTk.PhotoImage(canvas)
        self.video_label.config(image=self.current_photo, text="")

    def _show_placeholder(self, text: str) -> None:
        self.current_photo = None
        self.video_label.config(image="", text=text)

    def _set_status(self, text: str, color: str) -> None:
        self.status_var.set(text)
        self.status_label.config(fg=color)

    def _clear_queue_frames(self) -> None:
        items: list[StreamMessage] = []
        while not self.message_queue.empty():
            try:
                item = self.message_queue.get_nowait()
                if item.event != StreamEventType.FRAME:
                    items.append(item)
            except queue.Empty:
                break

        for item in items:
            try:
                self.message_queue.put_nowait(item)
            except queue.Full:
                break

    def on_close(self) -> None:
        self.stop_discovery()
        self.disconnect_camera(show_status=False)
        self.root.destroy()
