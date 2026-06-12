#!/usr/bin/env python3
# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Build docs/proposal/service-proposal.pdf from service-proposal.md.

Requires: pip install markdown weasyprint, plus a Japanese font
(e.g. Debian/Ubuntu package ``fonts-noto-cjk``).

Usage:
    python scripts/build_proposal_pdf.py [input.md] [output.pdf]
"""

from __future__ import annotations

import sys
from pathlib import Path

import markdown
from weasyprint import HTML

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MD = REPO_ROOT / "docs" / "proposal" / "service-proposal.md"
DEFAULT_PDF = REPO_ROOT / "docs" / "proposal" / "service-proposal.pdf"

CSS = """
@page {
    size: A4;
    margin: 20mm 18mm 22mm 18mm;
    @bottom-center {
        content: counter(page) " / " counter(pages);
        font-size: 8.5pt;
        color: #888;
    }
}
body {
    font-family: "Noto Sans CJK JP", "Noto Sans JP", sans-serif;
    font-size: 10pt;
    line-height: 1.75;
    color: #1a202c;
}
h1 {
    font-size: 17pt;
    line-height: 1.4;
    color: #0f2a43;
    border-bottom: 3px solid #1565c0;
    padding-bottom: 6pt;
    margin: 0 0 14pt 0;
}
h2 {
    font-size: 13pt;
    color: #0f2a43;
    border-left: 5px solid #1565c0;
    padding-left: 8pt;
    margin: 18pt 0 8pt 0;
    page-break-after: avoid;
}
h3 {
    font-size: 11pt;
    color: #1565c0;
    margin: 12pt 0 4pt 0;
    page-break-after: avoid;
}
p { margin: 6pt 0; }
hr {
    border: none;
    border-top: 1px solid #d0d7de;
    margin: 12pt 0;
}
table {
    border-collapse: collapse;
    width: 100%;
    margin: 8pt 0;
    font-size: 9.5pt;
    page-break-inside: avoid;
}
th, td {
    border: 1px solid #c4cdd5;
    padding: 5pt 7pt;
    text-align: left;
    vertical-align: top;
}
th { background: #eef3f8; color: #0f2a43; }
tr:nth-child(even) td { background: #f8fafc; }
ul, ol { margin: 6pt 0; padding-left: 18pt; }
li { margin: 2pt 0; }
strong { color: #0f2a43; }
em { color: #555; }
"""


def build(md_path: Path, pdf_path: Path) -> None:
    md_text = md_path.read_text(encoding="utf-8")
    body = markdown.markdown(
        md_text,
        extensions=["tables", "sane_lists", "smarty"],
        output_format="html5",
    )
    html = (
        "<!DOCTYPE html><html lang='ja'><head><meta charset='utf-8'>"
        f"<style>{CSS}</style></head><body>{body}</body></html>"
    )
    HTML(string=html, base_url=str(md_path.parent)).write_pdf(str(pdf_path))
    print(f"Wrote {pdf_path} ({pdf_path.stat().st_size:,} bytes)")


if __name__ == "__main__":
    md = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_MD
    pdf = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_PDF
    build(md, pdf)
