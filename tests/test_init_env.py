"""Проверка генератора .env (scripts/init_env.py)."""

from init_env import SECRET_KEYS, render_env

_SAMPLE = """\
# комментарий
POSTGRES_PASSWORD=change-me      # ЗАМЕНИ
POSTGRES_USER=monitoring
API_KEY=change-me
MQTT_PASSWORD=
GF_SECURITY_ADMIN_PASSWORD=change-me
"""


def test_secrets_are_generated_and_unique() -> None:
    """Секреты заменяются случайными значениями, не-секреты не трогаются."""
    text, generated = render_env(_SAMPLE)
    assert set(generated) == {"POSTGRES_PASSWORD", "API_KEY", "GF_SECURITY_ADMIN_PASSWORD"}
    # значения непустые, не плейсхолдер и различны
    assert all(v and v != "change-me" for v in generated.values())
    assert len(set(generated.values())) == len(generated)
    # не-секреты сохранены как есть
    assert "POSTGRES_USER=monitoring" in text
    assert "MQTT_PASSWORD=" in text  # анонимный MQTT не трогаем
    # сгенерированные значения попали в текст
    assert f"API_KEY={generated['API_KEY']}" in text


def test_secret_keys_cover_required() -> None:
    """В наборе секретов есть ключ API и пароли БД/Grafana."""
    assert {"API_KEY", "POSTGRES_PASSWORD", "POSTGRES_RO_PASSWORD"} <= SECRET_KEYS
