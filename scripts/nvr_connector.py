#!/usr/bin/env python3
"""Коннектор NVR → наш анализ (эпик docs/17_NVR_FRIGATE.md).

По триггеру (расписание / запрос оператора / в v2 — команда АУРА) берёт КУСОЧЕК
записи за интервал и отдаёт его НАШЕМУ воркеру file-заданием. Запись делает
Frigate (NVR), мы не жуём поток 24/7 — разбираем только нужный фрагмент нужными
проверками (тумблеры камеры). Источник фрагмента:

  • прод   — Frigate API: GET /api/<камера>/start/<unix>/end/<unix>/clip.mp4;
  • PoC    — локальный клип, вырезаем интервал через ffmpeg (имитация записи).

Пример (PoC, без Frigate): вырезать 0:05–0:35 из ролика и отдать на анализ кухни:
  python scripts/nvr_connector.py --camera-id <uuid> --clip /clips/kitchen.mp4 \\
      --start 5 --duration 30 --clips-dir ./samples --api-url http://localhost:8000

Пример (прод, Frigate):
  FRIGATE_URL=http://frigate:5000 python scripts/nvr_connector.py \\
      --camera-id <uuid> --frigate-camera kitchen --last-minutes 10
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx

API_URL = os.getenv("API_URL", "http://localhost:8000")
API_KEY = os.getenv("API_KEY", "")
FRIGATE_URL = os.getenv("FRIGATE_URL", "")


def _fragment_name(prefix: str) -> str:
    """Имя файла фрагмента: <prefix>_<unix>.mp4 (детерминированно по времени)."""
    return f"{prefix}_{int(time.time())}.mp4"


def fragment_from_frigate(camera: str, start: int, end: int, dest: Path) -> Path:
    """Вырезать клип из Frigate за [start..end] (unix-секунды) и сохранить в dest."""
    url = f"{FRIGATE_URL}/api/{camera}/start/{start}/end/{end}/clip.mp4"
    with httpx.stream("GET", url, timeout=120) as resp:
        resp.raise_for_status()
        with open(dest, "wb") as fh:
            for chunk in resp.iter_bytes():
                fh.write(chunk)
    return dest


def fragment_from_clip(clip: Path, start: float, duration: float, dest: Path) -> Path:
    """PoC: вырезать [start..start+duration] из локального клипа через ffmpeg."""
    subprocess.run(
        ["ffmpeg", "-y", "-ss", str(start), "-t", str(duration), "-i", str(clip),
         "-c", "copy", str(dest)],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return dest


def submit_analysis(source_ref: str, camera_id: str, api_url: str,
                    pipeline: str = "pose_v1") -> dict:
    """Создать file-задание нашему воркеру на разбор фрагмента."""
    resp = httpx.post(
        f"{api_url}/api/v1/analysis-tasks",
        headers={"X-API-Key": API_KEY, "Content-Type": "application/json"},
        json={
            "source_type": "file",
            "source_ref": source_ref,
            "camera_id": camera_id,
            "pipeline": pipeline,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def main() -> int:
    p = argparse.ArgumentParser(description="Коннектор NVR → выборочный анализ фрагмента")
    p.add_argument("--camera-id", required=True, help="UUID нашей камеры (для тумблеров/зон)")
    p.add_argument("--clips-dir", default="/clips", help="каталог, где живут ролики (том /clips)")
    p.add_argument("--clip-url-prefix", default="/clips", help="префикс source_ref для воркера")
    # PoC-источник (локальный клип):
    p.add_argument("--clip", help="PoC: локальный клип-«запись», из которого режем")
    p.add_argument("--start", type=float, default=0.0, help="PoC: начало фрагмента, с")
    p.add_argument("--duration", type=float, default=30.0, help="PoC: длительность фрагмента, с")
    # Прод-источник (Frigate):
    p.add_argument("--frigate-camera", help="имя камеры в Frigate")
    p.add_argument("--last-minutes", type=float, help="взять последние N минут из Frigate")
    p.add_argument("--api-url", default=API_URL)
    args = p.parse_args()

    clips_dir = Path(args.clips_dir)
    clips_dir.mkdir(parents=True, exist_ok=True)
    frag = clips_dir / _fragment_name(f"frag_{args.camera_id[:8]}")

    if FRIGATE_URL and args.frigate_camera and args.last_minutes:
        end = int(time.time())
        start = end - int(args.last_minutes * 60)
        print(f"[connector] Frigate {args.frigate_camera} {start}..{end} → {frag.name}")
        fragment_from_frigate(args.frigate_camera, start, end, frag)
    elif args.clip:
        print(f"[connector] PoC: ffmpeg вырезает {args.start}..{args.start + args.duration} c "
              f"из {args.clip} → {frag.name}")
        fragment_from_clip(Path(args.clip), args.start, args.duration, frag)
    else:
        p.error("укажите источник: --frigate-camera+--last-minutes (Frigate) или --clip (PoC)")

    source_ref = f"{args.clip_url_prefix.rstrip('/')}/{frag.name}"
    result = submit_analysis(source_ref, args.camera_id, args.api_url)
    task_id = result.get("data", {}).get("id")
    print(f"[connector] file-задание создано: {task_id} (source_ref={source_ref})")
    print("[connector] события появятся в журнале (GET /events) и на дашборде.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
