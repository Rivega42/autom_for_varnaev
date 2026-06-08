"""Сборка готового документа для заказчика из Markdown в HTML и PDF.

Markdown — это исходник; для передачи нужен отрисованный документ, где схемы
встроены, а ссылки кликабельны. Скрипт:
  1. конвертирует РУКОВОДСТВО_ЗАКАЗЧИКА.md в HTML (заголовки получают якоря в стиле
     GitHub, чтобы внутренние ссылки документа работали);
  2. сохраняет самодостаточный HTML (схемы встроены как base64-SVG);
  3. рендерит PDF через WeasyPrint (нативно рисует SVG, кириллицу, оглавление и
     кликабельные внутренние ссылки).

Результат — в docs/customer/build/: Rukovodstvo_zakazchika.html и .pdf.

Запуск:
    python scripts/build_customer_doc.py
"""

from __future__ import annotations

import base64
import re
import sys
from pathlib import Path

import markdown
from weasyprint import HTML

REPO_ROOT = Path(__file__).resolve().parents[1]
CUSTOMER_DIR = REPO_ROOT / "docs" / "customer"
GUIDE_MD = CUSTOMER_DIR / "РУКОВОДСТВО_ЗАКАЗЧИКА.md"
DIAGRAMS_DIR = CUSTOMER_DIR / "diagrams"
BUILD_DIR = CUSTOMER_DIR / "build"

# Имя выходных файлов (латиницей — дружелюбнее к разным ОС/почте).
OUT_STEM = "Rukovodstvo_zakazchika"


def gh_slug(value: str, separator: str = "-") -> str:
    """Якорь в стиле GitHub: нижний регистр, пробелы→дефис, без пунктуации.

    Совпадает с якорями, на которые ссылается сам документ (включая кириллицу).
    """
    value = value.strip().lower().replace(" ", separator)
    return "".join(c for c in value if c.isalnum() or c in "-_" or "а" <= c <= "я" or c == "ё")


def _embed_diagrams(html: str) -> str:
    """Встроить схемы: <img src="diagrams/X.svg"> → base64-данные (самодостаточно)."""

    def repl(match: re.Match[str]) -> str:
        svg = DIAGRAMS_DIR / match.group(1)
        if not svg.is_file():
            return match.group(0)
        data = base64.b64encode(svg.read_bytes()).decode("ascii")
        return f'src="data:image/svg+xml;base64,{data}"'

    return re.sub(r'src="diagrams/([^"]+\.svg)"', repl, html)


_CSS = """
@page { size: A4; margin: 18mm 16mm;
        @bottom-right { content: counter(page) " / " counter(pages);
                        font-size: 8pt; color: #888; } }
body { font-family: 'DejaVu Sans', sans-serif; font-size: 10.5pt; line-height: 1.45;
       color: #10204a; }
h1 { font-size: 21pt; color: #1a2f6b; border-bottom: 2px solid #3367d6; padding-bottom: 5px; }
h2 { font-size: 15pt; border-bottom: 1px solid #d0d7de; padding-bottom: 3px;
     margin-top: 22px; break-after: avoid; }
h3 { font-size: 12.5pt; margin-top: 16px; break-after: avoid; }
a { color: #3367d6; text-decoration: none; }
code, pre { font-family: 'DejaVu Sans Mono', monospace; }
pre { background: #f6f8fa; border: 1px solid #d0d7de; border-radius: 6px; padding: 8px;
      font-size: 8.5pt; white-space: pre-wrap; word-wrap: break-word; break-inside: avoid; }
code { background: #f0f2f5; padding: 1px 3px; border-radius: 3px; font-size: 9pt; }
pre code { background: none; padding: 0; }
table { border-collapse: collapse; width: 100%; margin: 8px 0; font-size: 9.5pt;
        break-inside: avoid; }
th, td { border: 1px solid #d0d7de; padding: 4px 7px; text-align: left; vertical-align: top; }
th { background: #f6f8fa; }
img { max-width: 100%; height: auto; border: 1px solid #e0e4e8; break-inside: avoid; }
blockquote { border-left: 4px solid #3367d6; margin: 8px 0; padding: 2px 12px;
             color: #57606a; background: #f8fafd; }
"""


def build() -> tuple[Path, Path]:
    """Собрать HTML и PDF; вернуть пути к ним."""
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    body = markdown.markdown(
        GUIDE_MD.read_text(encoding="utf-8"),
        extensions=["extra", "toc", "sane_lists"],
        extension_configs={"toc": {"slugify": gh_slug}},
    )
    body = _embed_diagrams(body)
    html = (
        "<!doctype html>\n<html lang='ru'><head><meta charset='utf-8'>"
        f"<title>Руководство заказчика</title><style>{_CSS}</style></head>"
        f"<body>\n{body}\n</body></html>"
    )
    html_path = BUILD_DIR / f"{OUT_STEM}.html"
    html_path.write_text(html, encoding="utf-8")

    pdf_path = BUILD_DIR / f"{OUT_STEM}.pdf"
    HTML(string=html, base_url=str(CUSTOMER_DIR)).write_pdf(str(pdf_path))
    return html_path, pdf_path


def main() -> int:
    """Собрать документ заказчика (HTML + PDF)."""
    html_path, pdf_path = build()
    print(f"Готово:\n  {html_path.relative_to(REPO_ROOT)}\n  {pdf_path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
