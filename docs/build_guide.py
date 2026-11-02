"""Build the Demonstrator Guide PDF from docs/Demonstrator_Guide.md.

Documentation tooling only, not needed to run CERT:
    pip install reportlab
    python docs/build_guide.py --group G1 --url https://example.streamlit.app

Until --group and --url are given, the placeholders are printed in red so they are
not missed. Supports the Markdown subset the guide uses: headings, paragraphs,
bullet and numbered lists, tables, code blocks and **bold** / *italic* / `code`.
"""
from __future__ import annotations

import argparse
import re
from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (KeepTogether, ListFlowable, ListItem, PageBreak, Paragraph,
                                Preformatted, SimpleDocTemplate, Spacer, Table, TableStyle)

DOCS = Path(__file__).parent
SOURCE = DOCS / "Demonstrator_Guide.md"
NAVY = colors.HexColor("#16486f")
INK = colors.HexColor("#1d2733")
MUTED = colors.HexColor("#5b6773")
RULE = colors.HexColor("#c9d3dd")
SHADE = colors.HexColor("#eef3f8")
MARGIN = 2 * cm
FRAME_W = A4[0] - 2 * MARGIN

MEMBERS = [("Glen Tan Lusheng", "A0309283B"), ("Loh Kai Kiat Keith", "A0308908W"),
           ("Tan Yi Long", "A0308902H")]


def register_fonts() -> tuple[str, str]:
    """Use Arial and Consolas when available (full Unicode); fall back to the PDF base fonts."""
    fonts = Path("C:/Windows/Fonts")
    try:
        for name, file in [("Body", "arial.ttf"), ("Body-Bold", "arialbd.ttf"),
                           ("Body-Italic", "ariali.ttf"), ("Body-BoldItalic", "arialbi.ttf"),
                           ("Mono", "consola.ttf")]:
            pdfmetrics.registerFont(TTFont(name, str(fonts / file)))
        pdfmetrics.registerFontFamily("Body", normal="Body", bold="Body-Bold", italic="Body-Italic",
                                      boldItalic="Body-BoldItalic")
        return "Body", "Mono"
    except Exception:
        return "Helvetica", "Courier"


BODY, MONO = register_fonts()
BOLD = "Body-Bold" if BODY == "Body" else "Helvetica-Bold"

STYLES = {
    "body": ParagraphStyle("body", fontName=BODY, fontSize=10, leading=14.5, textColor=INK, spaceAfter=6),
    "cell": ParagraphStyle("cell", fontName=BODY, fontSize=8.8, leading=11.5, textColor=INK),
    "head": ParagraphStyle("head", fontName=BOLD, fontSize=8.8, leading=11.5, textColor=NAVY),
    "h2": ParagraphStyle("h2", fontName=BOLD, fontSize=14, leading=18, textColor=NAVY, spaceBefore=14,
                         spaceAfter=7, keepWithNext=1),
    "h3": ParagraphStyle("h3", fontName=BOLD, fontSize=11.5, leading=15, textColor=NAVY, spaceBefore=10,
                         spaceAfter=5, keepWithNext=1),
    "code": ParagraphStyle("code", fontName=MONO, fontSize=8.8, leading=12, textColor=INK),
}


def inline(text: str, placeholders: dict[str, str]) -> str:
    """Escape text, then apply inline Markdown and the placeholder values."""
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    text = re.sub(r"`([^`]+)`", rf'<font face="{MONO}">\1</font>', text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<i>\1</i>", text)
    for key, value in placeholders.items():
        text = text.replace("{{" + key + "}}", value)
    return text


def col_widths(rows: list[list[str]]) -> list[float]:
    """Share the frame width by content length, with a floor so short columns stay readable."""
    n = len(rows[0])
    weights = [max(6, min(60, max(len(r[i]) for r in rows))) for i in range(n)]
    total = sum(weights)
    return [FRAME_W * w / total for w in weights]


def make_table(rows: list[list[str]], ph: dict[str, str]) -> Table:
    data = [[Paragraph(inline(c, ph), STYLES["head" if i == 0 else "cell"]) for c in r]
            for i, r in enumerate(rows)]
    table = Table(data, colWidths=col_widths(rows), repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), SHADE),
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, NAVY),
        ("LINEBELOW", (0, 1), (-1, -1), 0.4, RULE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]))
    return table


def make_list(items: list[str], ordered: bool, ph: dict[str, str]) -> ListFlowable:
    flow = [ListItem(Paragraph(inline(t, ph), STYLES["body"]), leftIndent=16) for t in items]
    kwargs = {"bulletType": "1", "bulletFormat": "%s."} if ordered else {"bulletType": "bullet", "start": "•"}
    return ListFlowable(flow, leftIndent=16, bulletFontName=BODY, bulletFontSize=10, **kwargs)


def parse(markdown: str, ph: dict[str, str]) -> list:
    """Convert the guide body (from the first '## ' heading) into flowables."""
    lines = markdown.splitlines()
    lines = lines[next(i for i, l in enumerate(lines) if l.startswith("## ")):]
    story, i = [], 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
        elif line.startswith("```"):
            j = lines.index("```", i + 1) if "```" in lines[i + 1:] else len(lines)
            block = Preformatted("\n".join(lines[i + 1:j]), STYLES["code"])
            story.append(Table([[block]], colWidths=[FRAME_W], style=[
                ("BACKGROUND", (0, 0), (-1, -1), SHADE), ("BOX", (0, 0), (-1, -1), 0.4, RULE),
                ("LEFTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
            story.append(Spacer(1, 8))
            i = j + 1
        elif line.startswith("## "):
            story.append(Paragraph(inline(line[3:], ph), STYLES["h2"]))
            i += 1
        elif line.startswith("### "):
            story.append(Paragraph(inline(line[4:], ph), STYLES["h3"]))
            i += 1
        elif line.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-+:?", c) for c in cells):
                    rows.append(cells)
                i += 1
            story += [make_table(rows, ph), Spacer(1, 10)]
        elif re.match(r"(\* |\d+\. )", line):
            ordered = bool(re.match(r"\d+\. ", line))
            items = []
            while i < len(lines) and (re.match(r"(\* |\d+\. )", lines[i]) or lines[i].startswith("  ")):
                if lines[i].startswith("  "):
                    items[-1] += " " + lines[i].strip()
                else:
                    items.append(re.sub(r"^(\* |\d+\. )", "", lines[i]))
                i += 1
            story += [make_list(items, ordered, ph), Spacer(1, 4)]
        else:
            para = [line]
            i += 1
            while i < len(lines) and lines[i].strip() and not re.match(r"(#|\||\* |\d+\. |```)", lines[i]):
                para.append(lines[i])
                i += 1
            story.append(Paragraph(inline(" ".join(para), ph), STYLES["body"]))
    return keep_headings_with_next(story)


def keep_headings_with_next(story: list) -> list:
    """Bind each heading to the block after it so no heading is stranded at the foot of a page."""
    out, i = [], 0
    while i < len(story):
        item = story[i]
        is_heading = isinstance(item, Paragraph) and item.style.name in ("h2", "h3")
        if is_heading and i + 1 < len(story) and not isinstance(story[i + 1], KeepTogether):
            out.append(KeepTogether([item, story[i + 1]]))
            i += 2
        else:
            out.append(item)
            i += 1
    return out


def cover(group: str, url: str) -> list:
    title = ParagraphStyle("t", fontName=BOLD, fontSize=26, leading=32, textColor=NAVY)
    sub = ParagraphStyle("s", fontName=BODY, fontSize=14, leading=19, textColor=INK)
    small = ParagraphStyle("m", fontName=BODY, fontSize=10.5, leading=15, textColor=MUTED)
    members = make_table([["Student name", "Matriculation number"], *[list(m) for m in MEMBERS]], {})
    members._argW = [FRAME_W * 0.6, FRAME_W * 0.4]
    return [
        Spacer(1, 5 * cm),
        Paragraph("CERT – Case Evidence Review Tracker", title),
        Spacer(1, 6),
        Paragraph("Demonstrator Guide", sub),
        Spacer(1, 18),
        Paragraph("IS4234 Governance, Regulation and Compliance Technology · NUS, AY2026/27 Semester 1", small),
        Paragraph(f"Group: {group}", small),
        Paragraph(f"Hosted demonstrator: {url}", small),
        Paragraph(f"Prepared {date.today():%d %B %Y}", small),
        Spacer(1, 1.2 * cm),
        members,
        Spacer(1, 1.2 * cm),
        Paragraph("A technology demonstrator for the Post Office Horizon case. All people, branches and "
                  "records in the prototype are fictional.", small),
        PageBreak(),
    ]


def footer(canvas, doc):
    if doc.page == 1:
        return
    canvas.saveState()
    canvas.setFont(BODY, 8.5)
    canvas.setFillColor(MUTED)
    canvas.drawString(MARGIN, 1.2 * cm, "CERT – Demonstrator Guide")
    canvas.drawRightString(A4[0] - MARGIN, 1.2 * cm, f"Page {doc.page - 1}")
    canvas.setStrokeColor(RULE)
    canvas.line(MARGIN, 1.55 * cm, A4[0] - MARGIN, 1.55 * cm)
    canvas.restoreState()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--group", help="Group ID, e.g. G1")
    ap.add_argument("--url", help="Hosted Streamlit link")
    ap.add_argument("--out", help="Output PDF path (default docs/<Group>_Demonstrator_Guide.pdf)")
    args = ap.parse_args()

    red = '<font color="#b42318"><b>{}</b></font>'
    group = args.group or red.format("[Group ID]")
    url = f'<link href="{args.url}" color="#16486f"><u>{args.url}</u></link>' if args.url \
        else red.format("[hosted link to be added]")
    out = Path(args.out) if args.out else DOCS / f"{args.group or 'GroupID'}_Demonstrator_Guide.pdf"

    ph = {"GROUP_ID": group, "HOSTED_URL": url}
    doc = SimpleDocTemplate(str(out), pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN, topMargin=MARGIN,
                            bottomMargin=MARGIN, title="CERT – Demonstrator Guide",
                            author="; ".join(n for n, _ in MEMBERS), subject="IS4234 prototype guide")
    doc.build(cover(group, url) + parse(SOURCE.read_text(encoding="utf-8"), ph),
              onFirstPage=footer, onLaterPages=footer)
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
