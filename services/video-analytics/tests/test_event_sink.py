"""Проверка отправки событий аналитики в log-service."""

import json
from datetime import UTC, datetime
from uuid import uuid4

import httpx
from video_analytics.event_sink import CollectingEventSink, HttpEventSink

from monitoring_shared import Event, EventSource, EventType, Severity


def _event() -> Event:
    return Event(
        id=uuid4(),
        ts=datetime(2026, 6, 5, 10, 0, tzinfo=UTC),
        source=EventSource.ANALYTICS,
        type=EventType.POSE_EVENT,
        room_id="room-01",
        severity=Severity.INFO,
        message="Поднята правая рука",
        payload={"pose": "right_arm_up", "limb": "right_arm"},
    )


def test_http_sink_posts_event() -> None:
    """HttpEventSink шлёт POST /events с JSON события."""
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"status": "ok"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    HttpEventSink("http://log-service:8000", client=client).emit(_event())

    assert str(captured["url"]).endswith("/events")
    body = captured["body"]
    assert isinstance(body, dict)
    assert body["type"] == "pose_event"


def test_collecting_sink() -> None:
    """CollectingEventSink накапливает события."""
    sink = CollectingEventSink()
    sink.emit(_event())
    assert len(sink.events) == 1
