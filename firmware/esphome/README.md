# firmware/esphome

YAML-конфиги узлов датчиков (ESPHome, без кода) для ESP32-C3 + SHT41/SHT40 +
MLX90614 на I²C. Узлы сами публикуют показания по MQTT в формате
`docs/08_MQTT_CONTRACT.md` (топик `monitoring/<node_id>/<metric>`, JSON
`{"value":…, "unit":…}`). Эпик E2.

- `node.example.yaml` — эталонный узел помещения (Wi-Fi, OTA, I²C, 60с).
- `cold_chamber.example.yaml` — вариант для холодильной камеры (E2.12).

**Секреты** (Wi-Fi/MQTT/OTA) — в `secrets.yaml` рядом через `!secret`; в репозиторий
кладутся только примеры без реальных значений (CLAUDE.md §5).
