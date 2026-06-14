#!/usr/bin/env python3
"""Сгенерировать пару ключей Ed25519 для лицензий (один раз, вендор; #335).

Публичный ключ (hex) вписывается в продукт — константа EMBEDDED_PUBLIC_KEY_HEX
в services/api-gateway/api_gateway/licensing.py. Приватный ключ сохраняется в
файл и хранится у вендора ВНЕ репозитория (им подписываются лицензии через
scripts/gen_license.py).

  python scripts/gen_license_keypair.py            # печать public + private
  python scripts/gen_license_keypair.py --out licenses/private.hex

ВНИМАНИЕ: приватный ключ — секрет. В репозиторий не коммитить (каталог licenses/
в .gitignore). Утечка приватного ключа = возможность выпускать поддельные
лицензии; ротация = новая пара + новый публичный ключ в продукте.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def main() -> int:
    parser = argparse.ArgumentParser(description="Генерация пары ключей лицензий Ed25519")
    parser.add_argument("--out", help="файл для приватного ключа (hex); иначе печать в stderr")
    args = parser.parse_args()

    private = Ed25519PrivateKey.generate()
    priv_hex = private.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    ).hex()
    pub_hex = (
        private.public_key()
        .public_bytes(encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw)
        .hex()
    )

    # Публичный ключ — в stdout (его вписывают в продукт).
    print(pub_hex)

    note = (
        "Публичный ключ (выше) впишите в EMBEDDED_PUBLIC_KEY_HEX "
        "(services/api-gateway/api_gateway/licensing.py).\n"
        "Приватный ключ — секрет, храните вне репозитория."
    )
    if args.out:
        path = Path(args.out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(priv_hex, encoding="utf-8")
        print(f"Приватный ключ записан в {path}\n{note}", file=sys.stderr)
    else:
        print(f"PRIVATE (секрет): {priv_hex}\n{note}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
