"""Генерация .env с автоматическими секретами из .env.example.

Заполняет секреты (пароли БД, ключ API, пароль Grafana) криптостойкими
случайными значениями, остальные строки берёт как есть из .env.example.
Идемпотентно: существующий .env не перезаписывается без --force.

Запуск:
    python scripts/init_env.py            # создать .env (если нет)
    python scripts/init_env.py --force    # перезаписать .env
"""

from __future__ import annotations

import re
import secrets
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = REPO_ROOT / ".env.example"
ENV = REPO_ROOT / ".env"

# Переменные, которым генерируем секрет (анонимный MQTT не трогаем).
SECRET_KEYS = frozenset(
    {
        "POSTGRES_PASSWORD",
        "POSTGRES_RO_PASSWORD",
        "API_KEY",
        "GF_SECURITY_ADMIN_PASSWORD",
    }
)


def _gen_secret() -> str:
    """Криптостойкий секрет, безопасный для .env (без спецсимволов)."""
    return secrets.token_urlsafe(24)


def render_env(example_text: str) -> tuple[str, dict[str, str]]:
    """Подставить секреты в текст .env.example; вернуть (текст, сгенерированные)."""
    generated: dict[str, str] = {}
    out: list[str] = []
    for line in example_text.splitlines():
        match = re.match(r"^([A-Z0-9_]+)=", line)
        if match and match.group(1) in SECRET_KEYS:
            key = match.group(1)
            value = _gen_secret()
            generated[key] = value
            out.append(f"{key}={value}")
        else:
            out.append(line)
    return "\n".join(out) + "\n", generated


def main() -> int:
    """Создать .env со сгенерированными секретами."""
    force = "--force" in sys.argv
    if ENV.exists() and not force:
        print(".env уже существует — пропускаю (используйте --force для перезаписи)")
        return 0
    text, generated = render_env(EXAMPLE.read_text(encoding="utf-8"))
    ENV.write_text(text, encoding="utf-8")
    print(f"Создан {ENV} со сгенерированными секретами:")
    for key, value in generated.items():
        print(f"  {key}={value}")
    print("Сохраните API_KEY — он нужен для доступа к API и веб-интерфейсу.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
