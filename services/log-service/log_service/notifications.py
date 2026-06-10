"""Активные уведомления о событиях (#264).

После записи события в журнал диспетчер оценивает правило (по важности и типу) и,
если событие проходит, шлёт его в настроенные каналы: Telegram, e-mail (SMTP),
generic webhook. Каналы инъектируемы — логика тестируется фейками; реальные
адаптеры проверяются на хосте. Доставка — best-effort: сбой канала логируется и
НЕ влияет на запись события (оно уже сохранено).

Конфигурация — через окружение (.env), секреты в репозиторий не кладутся.
"""

from __future__ import annotations

import logging
import os
import smtplib
from collections.abc import Sequence
from email.message import EmailMessage
from typing import Protocol

import httpx

from monitoring_shared import Event, Severity

logger = logging.getLogger(__name__)

# Порядок важности для порога уведомлений.
_SEVERITY_ORDER = {Severity.INFO: 0, Severity.WARNING: 1, Severity.CRITICAL: 2}


class Channel(Protocol):
    """Канал доставки уведомления (Telegram/e-mail/webhook/фейк в тестах)."""

    def send(self, subject: str, body: str, event: Event) -> None:
        """Отправить уведомление; исключения наружу — диспетчер их гасит."""
        ...


def format_event(event: Event) -> tuple[str, str]:
    """Сформировать (заголовок, тело) уведомления на русском из события."""
    room = event.room_id or "—"
    subject = f"[{event.severity.value}] {event.type.value} · {room}"
    body = (
        f"{event.message}\n"
        f"Помещение: {room}\n"
        f"Тип: {event.type.value}\n"
        f"Важность: {event.severity.value}\n"
        f"Время: {event.ts.isoformat()}"
    )
    return subject, body


class TelegramChannel:
    """Отправка в Telegram-бот (sendMessage). Проверяется на хосте."""

    def __init__(self, token: str, chat_id: str, timeout: float = 10.0) -> None:
        self._url = f"https://api.telegram.org/bot{token}/sendMessage"
        self._chat_id = chat_id
        self._timeout = timeout

    def send(self, subject: str, body: str, event: Event) -> None:
        text = f"{subject}\n\n{body}"
        if len(text) > 4096:  # лимит Telegram sendMessage — иначе HTTP 400
            text = text[:4093] + "…"
        with httpx.Client(timeout=self._timeout) as client:
            resp = client.post(self._url, json={"chat_id": self._chat_id, "text": text})
        resp.raise_for_status()


class WebhookChannel:
    """POST события в произвольный webhook (в т.ч. будущий внешний приёмник)."""

    def __init__(self, url: str, timeout: float = 10.0) -> None:
        self._url = url
        self._timeout = timeout

    def send(self, subject: str, body: str, event: Event) -> None:
        with httpx.Client(timeout=self._timeout) as client:
            resp = client.post(
                self._url,
                json={"subject": subject, "body": body, "event": event.model_dump(mode="json")},
            )
        resp.raise_for_status()


class EmailChannel:
    """Отправка e-mail по SMTP. Проверяется на хосте."""

    def __init__(
        self,
        host: str,
        port: int,
        sender: str,
        recipients: Sequence[str],
        *,
        user: str | None = None,
        password: str | None = None,
        use_tls: bool = True,
        timeout: float = 10.0,
    ) -> None:
        self._host, self._port, self._sender = host, port, sender
        self._recipients = list(recipients)
        self._user, self._password = user, password
        self._use_tls, self._timeout = use_tls, timeout

    def send(self, subject: str, body: str, event: Event) -> None:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = self._sender
        msg["To"] = ", ".join(self._recipients)
        msg.set_content(body)
        with smtplib.SMTP(self._host, self._port, timeout=self._timeout) as smtp:
            if self._use_tls:
                smtp.starttls()
            if self._user:
                smtp.login(self._user, self._password or "")
            smtp.send_message(msg)


class Notifier:
    """Диспетчер: фильтрует событие по правилу и рассылает в каналы (best-effort)."""

    def __init__(
        self,
        channels: Sequence[Channel],
        *,
        min_severity: Severity = Severity.WARNING,
        types: frozenset[str] | None = None,
    ) -> None:
        self._channels = list(channels)
        self._min_severity = min_severity
        # None = любой тип; иначе только перечисленные типы событий.
        self._types = types

    def _passes(self, event: Event) -> bool:
        if _SEVERITY_ORDER[event.severity] < _SEVERITY_ORDER[self._min_severity]:
            return False
        return self._types is None or event.type.value in self._types

    def notify(self, event: Event) -> int:
        """Разослать событие в каналы; вернуть число успешных отправок."""
        if not self._channels or not self._passes(event):
            return 0
        subject, body = format_event(event)
        sent = 0
        for ch in self._channels:
            try:
                ch.send(subject, body, event)
                sent += 1
            except Exception:
                # Сбой канала не должен влиять на запись события и другие каналы.
                logger.exception(
                    "Канал уведомления %s не доставил событие %s", type(ch).__name__, event.id
                )
        return sent


def build_notifier_from_env() -> Notifier:
    """Собрать диспетчер из окружения (.env). Без настроенных каналов — пустой."""
    channels: list[Channel] = []

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if token and chat_id:
        channels.append(TelegramChannel(token, chat_id))

    webhook = os.getenv("NOTIFY_WEBHOOK_URL")
    if webhook:
        channels.append(WebhookChannel(webhook))

    smtp_host = os.getenv("SMTP_HOST")
    mail_to = os.getenv("NOTIFY_EMAIL_TO")
    mail_from = os.getenv("NOTIFY_EMAIL_FROM")
    if smtp_host and mail_to and mail_from:
        try:
            smtp_port = int(os.getenv("SMTP_PORT", "587").strip())
        except ValueError:
            logger.warning("SMTP_PORT некорректен — использую 587")
            smtp_port = 587
        channels.append(
            EmailChannel(
                smtp_host,
                smtp_port,
                mail_from,
                [r.strip() for r in mail_to.split(",") if r.strip()],
                user=os.getenv("SMTP_USER"),
                password=os.getenv("SMTP_PASSWORD"),
                use_tls=os.getenv("SMTP_TLS", "true").lower() == "true",
            )
        )

    try:
        min_sev = Severity(os.getenv("NOTIFY_MIN_SEVERITY", "warning").strip().lower())
    except ValueError:
        logger.warning("NOTIFY_MIN_SEVERITY некорректен — использую warning")
        min_sev = Severity.WARNING
    types_env = os.getenv("NOTIFY_TYPES")  # CSV типов; пусто = любой
    types = frozenset(t.strip() for t in types_env.split(",") if t.strip()) if types_env else None

    if not channels:
        logger.info("Каналы уведомлений не настроены — уведомления отключены")
    return Notifier(channels, min_severity=min_sev, types=types)
