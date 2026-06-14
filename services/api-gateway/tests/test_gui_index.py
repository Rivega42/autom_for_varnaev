"""GUI настройки после редизайна (#321): вкладки, шапка, сохранённые секции."""

from __future__ import annotations

from api_gateway.app import create_app
from api_gateway.config import Settings
from api_gateway.tables import metadata
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.pool import StaticPool

_SETTINGS = Settings(
    log_service_url="http://log-service:8000",
    api_key=None,
    aura_integration_enabled=False,
)


def _engine() -> Engine:
    eng = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    metadata.create_all(eng)
    return eng


def _index() -> str:
    client = TestClient(create_app(settings=_SETTINGS, engine=_engine()))
    resp = client.get("/ui/")
    assert resp.status_code == 200
    body: str = resp.text
    return body


def test_tabs_navigation_present() -> None:
    """Шесть вкладок по доменам + контейнеры разделов."""
    text = _index()
    for tab in ("object", "cameras", "thresholds", "control", "schedules", "reports"):
        assert f'data-tab="{tab}"' in text, f"Нет кнопки вкладки {tab}"
        assert f'id="tab-{tab}"' in text, f"Нет контейнера вкладки {tab}"


def test_header_has_key_state_and_overview_link() -> None:
    """Шапка: индикатор состояния ключа и переход на обзорный экран."""
    text = _index()
    assert 'id="keystate"' in text
    assert "overview.html" in text


def test_license_banner_present() -> None:
    """Баннер лицензии в шапке: тариф, расход и поле ввода ключа (#335)."""
    text = _index()
    for el in ("licbar", "lictier", "licusage", "lickey", "lickeySave", "lickeyClear"):
        assert f'id="{el}"' in text, f"Нет элемента баннера лицензии {el}"


def test_all_sections_preserved() -> None:
    """Редизайн не потерял ни одной секции и интерактивных элементов."""
    text = _index()
    for section in (
        "directories-panel",
        "cameras",
        "editor",
        "thresholds-panel",
        "cleaning-panel",
        "presence-panel",
        "schedules-panel",
        "report-panel",
    ):
        assert f'id="{section}"' in text, f"Потеряна секция {section}"
    # Ключевые интерактивные элементы, на которые завязан app.js.
    for el in ("canvas", "camlist", "liveMount", "rm_add", "th_add", "sc_add", "rp_csv"):
        assert f'id="{el}"' in text, f"Потерян элемент {el}"
