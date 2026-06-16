"""СТЫК-АУРА D.5: отправитель уведомлений о готовности задания (#350)."""

from __future__ import annotations

import json
from uuid import uuid4

import httpx
from video_analytics.aura_callback import AuraNotifier

_URL = "http://aura/notify"


def _notifier(handler: httpx.MockTransport, **kw: object) -> AuraNotifier:
    return AuraNotifier(client=httpx.Client(transport=handler), **kw)  # type: ignore[arg-type]


def test_notify_posts_notice_and_returns_true() -> None:
    """notify шлёт POST с {task_id, status, artifacts} и возвращает True при 2xx."""
    seen: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == _URL
        seen.append(json.loads(request.content))
        return httpx.Response(200)

    tid = uuid4()
    ok = _notifier(httpx.MockTransport(handler)).notify(_URL, tid, "done", ["/a.jpg"])
    assert ok is True
    assert seen == [{"task_id": str(tid), "status": "done", "artifacts": ["/a.jpg"]}]


def test_notify_returns_false_on_5xx_after_retries() -> None:
    """Постоянный 5xx → False; ретраи исчерпываются (retries+1 попыток)."""
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(503)

    ok = _notifier(httpx.MockTransport(handler), retries=2).notify(_URL, uuid4(), "done")
    assert ok is False
    assert calls["n"] == 3  # 1 основная + 2 ретрая


def test_notify_succeeds_after_transient_failure() -> None:
    """Первый запрос упал, второй ок → True (ретрай помог)."""
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200 if calls["n"] >= 2 else 500)

    ok = _notifier(httpx.MockTransport(handler), retries=2).notify(_URL, uuid4(), "done")
    assert ok is True
    assert calls["n"] == 2


def test_notify_swallows_connection_error() -> None:
    """Ошибка соединения не бросается наружу → False (best-effort)."""
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        raise httpx.ConnectError("нет связи")

    ok = _notifier(httpx.MockTransport(handler), retries=1).notify(_URL, uuid4(), "failed")
    assert ok is False
    assert calls["n"] == 2  # ретраи отрабатывают и на ошибке соединения


def test_notify_blocks_disallowed_host() -> None:
    """allowlist задан, хост callback_url не в нём → блок (SSRF), запроса нет."""
    called = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        called["n"] += 1
        return httpx.Response(200)

    notifier = _notifier(httpx.MockTransport(handler), allowed_hosts=frozenset({"aura"}))
    assert notifier.notify("http://evil.local/x", uuid4(), "done") is False
    assert notifier.notify("http://aura/notify", uuid4(), "done") is True  # разрешённый хост ок
    assert called["n"] == 1  # запрос ушёл только на разрешённый хост


def test_notify_rejects_non_http_scheme() -> None:
    """callback_url не http(s) → False без запроса."""
    called = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        called["n"] += 1
        return httpx.Response(200)

    notifier = _notifier(httpx.MockTransport(handler))
    assert notifier.notify("ftp://aura/x", uuid4(), "done") is False
    assert called["n"] == 0
