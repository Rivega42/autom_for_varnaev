"""Проверка связности монорепо: общий пакет импортируется и версионируется."""

import monitoring_shared


def test_shared_importable_and_versioned() -> None:
    """Пакет monitoring_shared доступен и имеет непустую версию."""
    assert monitoring_shared.__version__
