from urllib.parse import urlparse

from ip_camera_viewer.config import APP_CONFIG


def validate_camera_url(url: str) -> tuple[bool, str]:
    value = url.strip()
    if not value:
        return False, "Введите ссылку на IP-камеру."

    parsed = urlparse(value)
    if parsed.scheme.lower() not in APP_CONFIG.validation.allowed_schemes:
        schemes = ", ".join(APP_CONFIG.validation.allowed_schemes)
        return False, f"Поддерживаются только ссылки со схемами: {schemes}."

    if not parsed.netloc:
        return False, "Ссылка выглядит неполной. Проверьте адрес камеры, порт и логин."

    return True, ""


def validate_discovery_host(host: str) -> tuple[bool, str]:
    value = host.strip()
    if not value:
        return False, "Введите IP, доменное имя или базовый адрес камеры."

    if " " in value:
        return False, "Адрес камеры не должен содержать пробелы."

    return True, ""