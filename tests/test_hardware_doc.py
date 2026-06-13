"""Раздел «Железо» (docs/11_HARDWARE.md) не должен расходиться с прошивкой.

Эталонные ESPHome-конфиги — источник истины по распиновке. Тест проверяет, что
пины I²C/ADC, указанные в документе, совпадают с пинами в firmware/esphome, а
схемы расключения существуют и подключены к разделу.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
_DOC = REPO_ROOT / "docs" / "11_HARDWARE.md"
_NODE_YAML = REPO_ROOT / "firmware" / "esphome" / "node.example.yaml"
_SVG_NODE = REPO_ROOT / "docs" / "diagrams" / "08_node_wiring.svg"
_SVG_COLD = REPO_ROOT / "docs" / "diagrams" / "09_cold_chamber_wiring.svg"


def _firmware_pins() -> dict[str, str]:
    """Извлечь пины из эталонной прошивки (regex — в YAML есть теги !secret/!lambda)."""
    text = _NODE_YAML.read_text(encoding="utf-8")
    sda = re.search(r"^\s*sda:\s*(GPIO\d+)", text, re.M)
    scl = re.search(r"^\s*scl:\s*(GPIO\d+)", text, re.M)
    adc = re.search(r"platform:\s*adc.*?pin:\s*(GPIO\d+)", text, re.S)
    assert sda and scl and adc, "не нашли пины в node.example.yaml"
    return {"sda": sda.group(1), "scl": scl.group(1), "adc": adc.group(1)}


def test_doc_pinout_matches_firmware() -> None:
    """Пины SDA/SCL/ADC из прошивки присутствуют в разделе «Железо»."""
    doc = _DOC.read_text(encoding="utf-8")
    for role, pin in _firmware_pins().items():
        assert pin in doc, f"В docs/11_HARDWARE.md нет пина {pin} ({role}) из прошивки"


def test_doc_references_wiring_diagrams() -> None:
    """Обе схемы существуют и встроены в раздел."""
    assert _SVG_NODE.is_file(), "Нет схемы обычного узла"
    assert _SVG_COLD.is_file(), "Нет схемы холодильной камеры"
    doc = _DOC.read_text(encoding="utf-8")
    assert "diagrams/08_node_wiring.svg" in doc
    assert "diagrams/09_cold_chamber_wiring.svg" in doc


def test_doc_covers_all_v1_metrics() -> None:
    """Раздел перечисляет все метрики v1 (состав узла полон)."""
    doc = _DOC.read_text(encoding="utf-8")
    for metric in ("air_temp", "humidity", "surface_ir", "uv_index", "uv_c"):
        assert metric in doc, f"В разделе «Железо» не описана метрика {metric}"
