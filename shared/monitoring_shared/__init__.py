"""Общие модели контура мониторинга.

Единый конверт API и схемы событий/заданий/артефактов, чтобы сервисы не
расходились в форматах (см. docs/03_API_CONTRACT.md, docs/04_DATA_MODEL.md).
"""

from monitoring_shared.models import Metric, Reading, Room, SensorNode

__version__ = "0.1.0"

__all__ = ["Metric", "Reading", "Room", "SensorNode", "__version__"]
