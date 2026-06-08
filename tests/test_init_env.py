"""Проверка генератора .env (scripts/init_env.py)."""

import stat
import sys
from pathlib import Path

import pytest

import init_env
from init_env import SECRET_KEYS, render_env

_SAMPLE = """\
# комментарий
POSTGRES_PASSWORD=change-me      # ЗАМЕНИ
POSTGRES_USER=monitoring
API_KEY=change-me
MQTT_PASSWORD=
GF_SECURITY_ADMIN_PASSWORD=change-me
"""


def test_secrets_are_generated_and_unique() -> None:
    """Секреты заменяются случайными значениями, не-секреты не трогаются."""
    text, generated = render_env(_SAMPLE)
    assert set(generated) == {"POSTGRES_PASSWORD", "API_KEY", "GF_SECURITY_ADMIN_PASSWORD"}
    # значения непустые, не плейсхолдер и различны
    assert all(v and v != "change-me" for v in generated.values())
    assert len(set(generated.values())) == len(generated)
    # не-секреты сохранены как есть
    assert "POSTGRES_USER=monitoring" in text
    assert "MQTT_PASSWORD=" in text  # анонимный MQTT не трогаем
    # сгенерированные значения попали в текст
    assert f"API_KEY={generated['API_KEY']}" in text


def test_secret_keys_cover_required() -> None:
    """В наборе секретов есть ключ API и пароли БД/Grafana."""
    assert {"API_KEY", "POSTGRES_PASSWORD", "POSTGRES_RO_PASSWORD"} <= SECRET_KEYS


def _full_example() -> str:
    """Пример .env со всеми требуемыми секретами (для тестов main)."""
    return "\n".join(f"{key}=change-me" for key in sorted(SECRET_KEYS)) + "\nPOSTGRES_USER=mon\n"


def test_main_creates_env_with_0600(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """main() создаёт .env с правами 0600 (секреты не читаемы другим)."""
    example = tmp_path / ".env.example"
    env = tmp_path / ".env"
    example.write_text(_full_example(), encoding="utf-8")
    monkeypatch.setattr(init_env, "EXAMPLE", example)
    monkeypatch.setattr(init_env, "ENV", env)
    monkeypatch.setattr(sys, "argv", ["init_env"])

    assert init_env.main() == 0
    assert env.exists()
    mode = stat.S_IMODE(env.stat().st_mode)
    assert mode == 0o600, f"ожидались права 0600, получены {oct(mode)}"


def test_main_fails_on_missing_secret(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Если в .env.example нет какого-то секрета — main() падает, .env не создаётся."""
    example = tmp_path / ".env.example"
    env = tmp_path / ".env"
    # Убираем один обязательный секрет из примера.
    dropped = sorted(SECRET_KEYS)[0]
    lines = [f"{k}=change-me" for k in sorted(SECRET_KEYS) if k != dropped]
    example.write_text("\n".join(lines) + "\n", encoding="utf-8")
    monkeypatch.setattr(init_env, "EXAMPLE", example)
    monkeypatch.setattr(init_env, "ENV", env)
    monkeypatch.setattr(sys, "argv", ["init_env"])

    assert init_env.main() == 1
    assert not env.exists()
