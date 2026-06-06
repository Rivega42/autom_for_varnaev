"""Программный запуск api-gateway через uvicorn.

В dev-образе сервис стартует командой `uvicorn api_gateway.app:app`. В закрытой
(Nuitka) сборке исходников нет и CLI-импорт по строке недоступен, поэтому точка
входа — этот модуль: импортирует приложение и запускает uvicorn программно.
Запуск: `python -m api_gateway` или скомпилированный бинарь.
"""

from __future__ import annotations

import os

import uvicorn

from api_gateway.app import app


def main() -> None:
    """Запустить ASGI-приложение api-gateway через uvicorn."""
    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", "8000"))
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
