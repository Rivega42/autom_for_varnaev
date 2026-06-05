"""Проверка сохранения артефактов (путь, keypoints JSON, метаданные)."""

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.pool import StaticPool
from video_analytics.artifacts import build_artifact_path, insert_artifact, save_keypoints_json
from video_analytics.tables import metadata

from monitoring_shared import Artifact, ArtifactKind

_TS = datetime(2026, 6, 5, 10, 30, tzinfo=UTC)


def test_build_artifact_path() -> None:
    art_id = uuid4()
    path = build_artifact_path("/data/artifacts", _TS, art_id, "jpg")
    assert path == f"/data/artifacts/2026-06-05/{art_id}.jpg"


def test_save_keypoints_json(tmp_path: Path) -> None:
    path = str(tmp_path / "kp.json")
    save_keypoints_json(path, {"points": [[0.1, 0.2]], "note": "тест"})
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    assert data["points"] == [[0.1, 0.2]]
    assert data["note"] == "тест"


def test_insert_artifact() -> None:
    engine: Engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    metadata.create_all(engine)
    artifact = Artifact(
        id=uuid4(),
        created_at=_TS,
        kind=ArtifactKind.SCREENSHOT,
        path="/data/artifacts/2026-06-05/x.jpg",
        room_id="room-01",
    )
    insert_artifact(engine, artifact)
    with engine.connect() as conn:
        row = conn.execute(text("SELECT kind, path FROM artifacts")).fetchone()
    assert row is not None
    assert row[0] == "screenshot"
