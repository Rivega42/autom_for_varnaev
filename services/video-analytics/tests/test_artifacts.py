"""Проверка сохранения артефактов (путь, keypoints JSON, метаданные)."""

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import numpy as np
import pytest
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.pool import StaticPool
from video_analytics.artifacts import (
    build_artifact_path,
    ensure_artifact_dir,
    insert_artifact,
    save_keypoints_json,
    save_screenshot,
)
from video_analytics.sources import Frame
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


def test_ensure_artifact_dir_creates_nested(tmp_path: Path) -> None:
    """Создаёт подкаталог по дате (как /data/artifacts/<YYYY-MM-DD>/)."""
    path = tmp_path / "2026-06-24" / "abc.jpg"
    ensure_artifact_dir(str(path))
    assert path.parent.is_dir()


def test_ensure_artifact_dir_permission_error_is_actionable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Отказ в правах (root-owned том) → понятная ошибка с подсказкой про uid 10001.

    Эмулируем продовую ситуацию #380: общий том принадлежит root, mkdir под
    appuser падает с PermissionError. Помощник должен переупаковать её в внятное
    сообщение, а не пробрасывать «голый» Errno 13.
    """

    def _deny(*_args: object, **_kwargs: object) -> None:
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(Path, "mkdir", _deny)
    with pytest.raises(PermissionError, match="uid 10001"):
        ensure_artifact_dir(str(tmp_path / "2026-06-24" / "x.jpg"))


def test_save_screenshot_writes_real_jpg(tmp_path: Path) -> None:
    """REAL-путь записи кадра-улики: создаётся подкаталог по дате и непустой .jpg.

    Прогоняет настоящий save_screenshot (кодирование OpenCV), без подмены — это и
    есть путь, который падал в проде на root-owned томе (#380). Пропускается, если
    cv2 не установлен (его нет в dev/CI-зависимостях, только в рантайм-образе)."""
    cv2 = pytest.importorskip("cv2")

    frame: Frame = np.zeros((8, 8, 3), dtype=np.uint8)
    path = tmp_path / "2026-06-24" / "shot.jpg"
    save_screenshot(frame, str(path))

    assert path.is_file()
    assert path.stat().st_size > 0
    # Файл действительно декодируется как изображение.
    assert cv2.imread(str(path)) is not None


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
