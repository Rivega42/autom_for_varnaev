#!/usr/bin/env python3
"""Выпустить лицензионный ключ: подписать тариф приватным ключом (вендор; #335).

Подписывает payload (клиент, тариф, лимиты, срок) приватным ключом Ed25519 →
строка лицензии `payload.signature` (base64url), которую клиент вставляет в GUI
или переменную LICENSE_KEY. Проверяется продуктом офлайн (docs/14_LICENSING.md).

  LICENSE_PRIVATE_KEY_HEX=<hex> python scripts/gen_license.py \
      --customer "ООО Пекарня №1" --tier pro \
      --cameras 20 --nodes 30 --rooms 10 --expires 2027-06-13

  # приватный ключ из файла:
  python scripts/gen_license.py --private-key licenses/private.hex --customer ... --cameras 20

Лимит «без ограничения» — значение 0 (пишется как null в payload). Приватный
ключ берётся из --private-key (файл) или LICENSE_PRIVATE_KEY_HEX; в репозиторий
не коммитится.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def _b64url(data: bytes) -> str:
    """base64url без паддинга (как ожидает продукт)."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _limit(value: int) -> int | None:
    """0 на входе → None (без ограничения)."""
    return None if value == 0 else value


def main() -> int:
    parser = argparse.ArgumentParser(description="Выпуск лицензионного ключа")
    parser.add_argument("--customer", required=True, help="имя клиента (в подпись)")
    parser.add_argument("--tier", default="pro", help="название тарифа")
    parser.add_argument(
        "--rooms", type=int, default=0, help="лимит помещений (0 = без ограничения)"
    )
    parser.add_argument("--cameras", type=int, default=0, help="лимит камер (0 = без ограничения)")
    parser.add_argument("--nodes", type=int, default=0, help="лимит узлов (0 = без ограничения)")
    parser.add_argument("--issued", help="дата выпуска YYYY-MM-DD (для записи в ключ)")
    parser.add_argument(
        "--expires", help="срок действия YYYY-MM-DD (подписка); без него — бессрочно"
    )
    parser.add_argument("--private-key", help="файл с приватным ключом (hex)")
    args = parser.parse_args()

    if args.private_key:
        priv_hex = Path(args.private_key).read_text(encoding="utf-8").strip()
    else:
        priv_hex = (os.getenv("LICENSE_PRIVATE_KEY_HEX") or "").strip()
    if not priv_hex:
        parser.error("укажите --private-key <файл> или LICENSE_PRIVATE_KEY_HEX")

    private = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(priv_hex))

    payload: dict[str, object] = {
        "customer": args.customer,
        "tier": args.tier,
        "max_rooms": _limit(args.rooms),
        "max_cameras": _limit(args.cameras),
        "max_nodes": _limit(args.nodes),
    }
    if args.issued:
        payload["issued"] = args.issued
    if args.expires:
        payload["expires"] = args.expires

    # Компактный детерминированный JSON (подпись над этими же байтами).
    payload_bytes = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    signature = private.sign(payload_bytes)
    print(f"{_b64url(payload_bytes)}.{_b64url(signature)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
