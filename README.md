# IP Camera Viewer

Программа для подключения к IP-камере по RTSP/HTTP, показа потока через FFmpeg и детекции человека через YOLO11m.

## Что внутри

- подключение к камере через FFmpeg;
- поиск типовой ссылки потока прямо в программе;
- детекция **человека** через YOLO11m;
- детекция работает в **отдельном потоке**, чтобы интерфейс не зависал;
- отображаются рамки и статус обнаружения.

## Структура проекта

```text
cam/
├── main.py
├── requirements.txt
├── README.md
└── ip_camera_viewer/
    ├── __init__.py
    ├── app.py
    ├── config.py
    ├── models.py
    ├── services/
    │   ├── __init__.py
    │   ├── camera_stream.py
    │   ├── person_detector.py
    │   └── url_discovery.py
    ├── ui/
    │   ├── __init__.py
    │   └── main_window.py
    └── utils/
        ├── __init__.py
        ├── ffmpeg.py
        ├── image.py
        └── validators.py
```

## Установка

```bash
pip install -r requirements.txt
```

Также рядом с `main.py` должны лежать `ffmpeg.exe` и `ffprobe.exe`, либо они должны быть доступны через PATH.

## Запуск

```bash
python main.py
```

## YOLO11m

Используется модель `yolo11m.pt`. При первом запуске библиотека Ultralytics может скачать веса автоматически.

## Важно

Для баланса качества и нагрузки лучше использовать sub-stream, например `102`, если камера его поддерживает.

Примеры ссылок:

```text
rtsp://login:password@192.168.1.10:554/stream
http://192.168.1.10:8080/video
```
