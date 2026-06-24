"""Файловое хранилище артефактов-доказательств (стоп-кадры браузерного анализа).

Воркер видеоаналитики кладёт скриншоты на общий том по схеме
`/<dir>/<YYYY-MM-DD>/<id>.<ext>` (docs/01 §6). Здесь — чистые помощники для
api-gateway: построить путь, безопасно прочитать файл (только внутри каталога
артефактов) и разобрать data-URL снимка из браузера. Без рантайм-зависимостей —
тестируется на временных каталогах.
"""

from __future__ import annotations

import base64
import binascii
from datetime import datetime
from pathlib import Path
from uuid import UUID

# Допустимые MIME картинок-снимков из браузера → расширение файла.
_IMAGE_EXT = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}


def build_artifact_path(artifacts_dir: str, ts: datetime, artifact_id: UUID, ext: str) -> str:
    """Путь артефакта по схеме /<dir>/<YYYY-MM-DD>/<id>.<ext> (как у воркера)."""
    return f"{artifacts_dir}/{ts:%Y-%m-%d}/{artifact_id}.{ext}"


# Предел размера стоп-кадра (декодированного) — защита от переполнения диска/памяти.
MAX_IMAGE_BYTES = 8 * 1024 * 1024


def decode_data_url(data_url: str, max_bytes: int = MAX_IMAGE_BYTES) -> tuple[bytes, str]:
    """Разобрать data-URL картинки (`data:image/jpeg;base64,...`) → (байты, mime).

    Поднимает ValueError при неверном формате, неподдерживаемом типе или
    превышении `max_bytes` — вызов обязан сконвертировать это в 422, а не уронить
    запрос.
    """
    if not data_url.startswith("data:"):
        raise ValueError("ожидается data-URL картинки (data:image/...;base64,...)")
    header, sep, payload = data_url[5:].partition(",")
    if not sep:
        raise ValueError("ожидается base64-кодированный data-URL")
    # Параметры заголовка: первый — mime, среди остальных должен быть токен base64
    # (без учёта регистра; строгое сравнение, чтобы не принять, напр., 'base64x').
    params = [p.strip().lower() for p in header.split(";")]
    mime = params[0]
    if "base64" not in params[1:]:
        raise ValueError("ожидается base64-кодированный data-URL")
    if mime not in _IMAGE_EXT:
        raise ValueError(f"неподдерживаемый тип картинки: {mime}")
    try:
        raw = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError):
        raise ValueError("повреждённый base64 в data-URL") from None
    if not raw:
        raise ValueError("пустая картинка")
    if len(raw) > max_bytes:
        raise ValueError(f"картинка больше допустимых {max_bytes} байт")
    return raw, mime


def ext_for_mime(mime: str) -> str:
    """Расширение файла для MIME картинки (jpg по умолчанию)."""
    return _IMAGE_EXT.get(mime, "jpg")


def ensure_artifact_dir(path: str) -> None:
    """Создать родительский каталог артефакта; при отказе в правах — понятная ошибка.

    Общий том /data/artifacts Docker инициализирует владельцем root, а api-gateway
    работает под непривилегированным пользователем (uid 10001). Владельца тома
    выставляет one-shot сервис `artifacts-init` (docker-compose) ДО старта сервиса.
    Если каталог недоступен на запись (нестандартный запуск или том пересоздан без
    artifacts-init) — даём оператору внятную причину, а не «голый» PermissionError.
    См. docs/01 §6.
    """
    parent = Path(path).parent
    try:
        parent.mkdir(parents=True, exist_ok=True)
    except PermissionError as exc:
        raise PermissionError(
            f"Нет прав на запись каталога артефактов {parent}: общий том должен "
            "принадлежать пользователю uid 10001 (в docker-compose это делает сервис "
            "artifacts-init на старте; см. docs/01 §6)."
        ) from exc


def save_bytes(path: str, data: bytes) -> None:
    """Записать байты артефакта, создав подкаталог по дате при необходимости."""
    ensure_artifact_dir(path)
    Path(path).write_bytes(data)


def read_artifact_bytes(artifacts_dir: str, path: str) -> bytes | None:
    """Прочитать файл артефакта, не выпуская чтение за пределы каталога артефактов.

    Защита от path traversal: путь из БД резолвится и проверяется, что он внутри
    `artifacts_dir`. Возвращает None, если файла нет или он вне каталога.
    """
    base = Path(artifacts_dir).resolve()
    candidate = Path(path).resolve()
    try:
        candidate.relative_to(base)
    except ValueError:
        return None  # путь вне каталога артефактов — не отдаём
    if not candidate.is_file():
        return None
    return candidate.read_bytes()
