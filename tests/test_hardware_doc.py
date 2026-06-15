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
_QUICKSTART = REPO_ROOT / "docs" / "15_SENSOR_QUICKSTART.md"
_NODE_YAML = REPO_ROOT / "firmware" / "esphome" / "node.example.yaml"
_KIT_YAML = REPO_ROOT / "firmware" / "esphome" / "node_sht30.example.yaml"
_SVG_FLOW = REPO_ROOT / "docs" / "diagrams" / "11_flashing_flow.svg"
_SVG_NODE = REPO_ROOT / "docs" / "diagrams" / "08_node_wiring.svg"
_SVG_COLD = REPO_ROOT / "docs" / "diagrams" / "09_cold_chamber_wiring.svg"
_SVG_PINOUT = REPO_ROOT / "docs" / "diagrams" / "10_esp32c3_pinout.svg"


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
    """Схемы и распиновка платы существуют и встроены в раздел."""
    assert _SVG_NODE.is_file(), "Нет схемы обычного узла"
    assert _SVG_COLD.is_file(), "Нет схемы холодильной камеры"
    assert _SVG_PINOUT.is_file(), "Нет распиновки платы ESP32-C3"
    doc = _DOC.read_text(encoding="utf-8")
    assert "diagrams/08_node_wiring.svg" in doc
    assert "diagrams/09_cold_chamber_wiring.svg" in doc
    assert "diagrams/10_esp32c3_pinout.svg" in doc


def test_doc_warns_about_silkscreen_pins() -> None:
    """Раздел предупреждает, что шёлкография SDA/SCL (8/9) ≠ пины прошивки (5/6)."""
    doc = _DOC.read_text(encoding="utf-8")
    assert "шёлкограф" in doc.lower() or "8 и 9" in doc, "Нет предупреждения про пины 8/9"
    # SHT30 требует другой платформы ESPHome, чем SHT4x — это должно быть отражено.
    assert "sht3xd" in doc, "Нет указания платформы sht3xd для SHT30"


def test_doc_covers_all_v1_metrics() -> None:
    """Раздел перечисляет все метрики v1 (состав узла полон)."""
    doc = _DOC.read_text(encoding="utf-8")
    for metric in ("air_temp", "humidity", "surface_ir", "uv_index", "uv_c"):
        assert metric in doc, f"В разделе «Железо» не описана метрика {metric}"


# ── Пошаговое руководство (docs/15) и готовый конфиг под комплект из 2 датчиков ──


def test_kit_config_is_sht30_two_sensors_no_uv() -> None:
    """node_sht30.example.yaml — под GY-SHT30-D + MLX90614: sht3xd, без УФ, те же I²C-пины."""
    cfg = _KIT_YAML.read_text(encoding="utf-8")
    assert "platform: sht3xd" in cfg, "Комплектный конфиг должен использовать sht3xd (SHT30)"
    assert "platform: mlx90614" in cfg, "Нет MLX90614 (ИК-температура поверхности)"
    # УФ-датчиков в комплекте нет — их платформ не должно быть в конфиге
    # (упоминание в комментарии «убраны ltr390 и adc» допустимо, проверяем platform:).
    assert "platform: ltr390" not in cfg and "platform: adc" not in cfg, (
        "В комплектном конфиге не должно быть УФ-датчиков"
    )
    # Пины I²C совпадают с эталоном (источник истины — node.example.yaml).
    pins = _firmware_pins()
    assert f"sda: {pins['sda']}" in cfg and f"scl: {pins['scl']}" in cfg


def test_quickstart_exists_and_links_kit() -> None:
    """Руководство docs/15 существует, ссылается на комплектный конфиг и схему прошивки."""
    assert _QUICKSTART.is_file(), "Нет пошагового руководства docs/15_SENSOR_QUICKSTART.md"
    assert _SVG_FLOW.is_file(), "Нет схемы процесса прошивки 11_flashing_flow.svg"
    guide = _QUICKSTART.read_text(encoding="utf-8")
    assert "node_sht30.example.yaml" in guide, "Руководство не ссылается на комплектный конфиг"
    assert "diagrams/11_flashing_flow.svg" in guide, "Руководство не встраивает схему прошивки"
    # Документ 11 направляет новичка в руководство 15.
    assert "15_SENSOR_QUICKSTART.md" in _DOC.read_text(encoding="utf-8")
