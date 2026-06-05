"""Pydantic-модели общих сущностей контура.

Соответствуют таблицам из docs/04_DATA_MODEL.md. Здесь — справочники и
показания датчиков (E1.13); остальные сущности добавляются в E1.14.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel


class Metric(StrEnum):
    """Метрики показаний датчиков (v1)."""

    AIR_TEMP = "air_temp"  # температура воздуха, °C
    HUMIDITY = "humidity"  # влажность, %
    SURFACE_IR = "surface_ir"  # бесконтактная ИК-температура поверхности, °C


class Room(BaseModel):
    """Помещение объекта (таблица rooms)."""

    id: str
    name: str
    is_cold: bool = False


class SensorNode(BaseModel):
    """Узел датчиков — контроллер (таблица sensor_nodes)."""

    id: str
    room_id: str
    placement: str | None = None
    power: str | None = None
    note: str | None = None


class Reading(BaseModel):
    """Показание датчика — точка временного ряда (таблица sensor_readings)."""

    ts: datetime
    node_id: str
    room_id: str
    metric: Metric
    value: float
    unit: str
