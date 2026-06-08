# firmware/esphome

YAML-конфиги узлов датчиков (ESPHome, без кода) для ESP32-C3 + SHT41/SHT40 +
MLX90614 на I²C. Узлы сами публикуют показания по MQTT в формате
`docs/08_MQTT_CONTRACT.md` (топик `monitoring/<node_id>/<metric>`, JSON
`{"value":…, "unit":…}`). Эпик E2.

- `node.example.yaml` — эталонный узел помещения (Wi-Fi, OTA, I²C, 60с).
- `cold_chamber.example.yaml` — вариант для холодильной камеры (E2.12).

**Секреты** (Wi-Fi/MQTT/OTA) — в `secrets.yaml` рядом через `!secret`; в репозиторий
кладётся только пример `secrets.yaml.example` без реальных значений (CLAUDE.md §5).

## Как прошить узел

1. Установить ESPHome (одноразово): `pip install esphome`.
2. Создать секреты из примера и заполнить их:
   ```bash
   cd firmware/esphome
   cp secrets.yaml.example secrets.yaml   # secrets.yaml в .gitignore, не коммитится
   # отредактировать secrets.yaml: wifi_ssid/password, mqtt_broker (IP сервера), ota_password
   ```
3. Сделать конфиг узла из эталона — **по файлу на каждый физический узел**:
   ```bash
   cp node.example.yaml node-01.yaml      # для холодильной камеры — cold_chamber.example.yaml
   # в node-01.yaml поправить substitutions: node_id и topic_base (node-01, node-02, …)
   ```
   **Важно:** `node_id` в прошивке обязан совпадать с `sensor_nodes.id` в справочнике
   (REST/GUI или сид) — иначе ingest-sensors отбросит показания как «неизвестный узел».
4. Прошить:
   ```bash
   esphome run node-01.yaml               # 1-й раз — по USB; далее обновления по OTA (Wi-Fi)
   ```
5. Проверить, что показания идут: на сервере посмотреть топики брокера
   (`mosquitto_sub -h <сервер> -t 'monitoring/#' -v`) или ряды в Grafana.

Узлы датчиков физически не входят в Docker-контур: контроллер ESP32-C3 сам
подключается к Wi-Fi и публикует MQTT на брокер сервера (см. `docs/02_NETWORK.md`).
