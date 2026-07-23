"""Realistic file-content generators for the RetailCo enterprise drive.

Each function returns ``(bytes, mime_type)`` for a given logical file so the
uploaded objects are real, openable files of the correct type rather than empty
placeholders. Content is derived deterministically from the file name + a seeded
``random.Random`` so re-runs are reproducible.

Heavy office formats (xlsx/docx/pptx/pdf/png/jpg) use optional third-party
libraries. If a library is missing the generator degrades gracefully to a
plain-text stand-in with the correct extension so the drive still populates.
"""
from __future__ import annotations

import io
import json
import random
from datetime import datetime, timedelta

# ---- optional heavy deps (degrade gracefully) -------------------------------
try:
    from openpyxl import Workbook
except Exception:  # pragma: no cover
    Workbook = None
try:
    import docx
except Exception:  # pragma: no cover
    docx = None
try:
    from pptx import Presentation
    from pptx.util import Inches, Pt
except Exception:  # pragma: no cover
    Presentation = None
try:
    from reportlab.lib.pagesizes import LETTER
    from reportlab.pdfgen import canvas as _pdfcanvas
except Exception:  # pragma: no cover
    _pdfcanvas = None
try:
    from PIL import Image, ImageDraw
except Exception:  # pragma: no cover
    Image = None

MIME = {
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "pdf": "application/pdf",
    "csv": "text/csv",
    "txt": "text/plain",
    "md": "text/markdown",
    "json": "application/json",
    "png": "image/png",
    "jpg": "image/jpeg",
}

_PRODUCTS = [
    "Aurora Wireless Earbuds", "Nomad Trail Backpack", "Cirrus Down Jacket",
    "Harbor Cast-Iron Skillet", "Vertex Running Shoe", "Lumen LED Desk Lamp",
    "Terra Ceramic Mug Set", "Pulse Fitness Tracker", "Drift Cotton Bedsheets",
    "Summit Insulated Bottle", "Grove Bamboo Cutting Board", "Echo Bluetooth Speaker",
]
_REGIONS = ["Northeast", "Southeast", "Midwest", "Southwest", "West", "Pacific Northwest"]
_STORES = [f"Store #{1000 + i}" for i in range(60)]


def _rng(name: str, seed: int) -> random.Random:
    return random.Random(f"{seed}:{name}")


def _money(r: random.Random, lo: float, hi: float) -> float:
    return round(r.uniform(lo, hi), 2)


# ---- individual format builders --------------------------------------------
def _xlsx(name: str, r: random.Random) -> bytes:
    if Workbook is None:
        return _txt_fallback(name, r)
    wb = Workbook()
    ws = wb.active
    ws.title = "Data"
    headers = ["Date", "Region", "Store", "Product", "Units", "Revenue", "Margin %"]
    ws.append(headers)
    start = datetime(2025, 1, 1)
    for i in range(r.randint(40, 200)):
        d = start + timedelta(days=r.randint(0, 480))
        units = r.randint(1, 800)
        rev = round(units * _money(r, 4.0, 240.0), 2)
        ws.append([
            d.strftime("%Y-%m-%d"), r.choice(_REGIONS), r.choice(_STORES),
            r.choice(_PRODUCTS), units, rev, round(r.uniform(8, 62), 1),
        ])
    # a small summary sheet
    s2 = wb.create_sheet("Summary")
    s2.append(["Metric", "Value"])
    s2.append(["Total Rows", ws.max_row - 1])
    s2.append(["Generated", datetime.utcnow().isoformat()])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _docx(name: str, r: random.Random) -> bytes:
    if docx is None:
        return _txt_fallback(name, r)
    doc = docx.Document()
    doc.add_heading(name, level=0)
    doc.add_paragraph(
        "RetailCo — Confidential. This document is part of the enterprise "
        "reference drive used for demonstration purposes."
    )
    for _ in range(r.randint(4, 9)):
        doc.add_heading(r.choice([
            "Executive Summary", "Objectives", "Scope", "Timeline",
            "Risks & Mitigations", "Budget", "Next Steps", "Appendix",
        ]), level=1)
        for _ in range(r.randint(2, 4)):
            doc.add_paragraph(_lorem(r, r.randint(30, 70)))
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _pptx(name: str, r: random.Random) -> bytes:
    if Presentation is None:
        return _txt_fallback(name, r)
    prs = Presentation()
    title_slide = prs.slides.add_slide(prs.slide_layouts[0])
    title_slide.shapes.title.text = name
    title_slide.placeholders[1].text = "RetailCo — Internal Deck"
    for _ in range(r.randint(4, 8)):
        s = prs.slides.add_slide(prs.slide_layouts[1])
        s.shapes.title.text = r.choice([
            "Market Overview", "Q4 Performance", "Category Strategy",
            "Store Rollout", "Customer Insights", "Roadmap", "Financials",
        ])
        body = s.placeholders[1].text_frame
        body.text = _lorem(r, 12)
        for _ in range(r.randint(2, 4)):
            p = body.add_paragraph()
            p.text = "• " + _lorem(r, r.randint(6, 12))
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


def _pdf(name: str, r: random.Random) -> bytes:
    if _pdfcanvas is None:
        return _txt_fallback(name, r)
    buf = io.BytesIO()
    c = _pdfcanvas.Canvas(buf, pagesize=LETTER)
    width, height = LETTER
    for page in range(r.randint(1, 4)):
        c.setFont("Helvetica-Bold", 16)
        c.drawString(72, height - 72, name if page == 0 else f"{name} (cont.)")
        c.setFont("Helvetica", 10)
        y = height - 110
        for _ in range(r.randint(20, 34)):
            c.drawString(72, y, _lorem(r, r.randint(8, 16)))
            y -= 16
            if y < 72:
                break
        c.showPage()
    c.save()
    return buf.getvalue()


def _csv(name: str, r: random.Random) -> bytes:
    rows = ["date,region,store,product,units,revenue"]
    start = datetime(2025, 1, 1)
    for _ in range(r.randint(50, 400)):
        d = start + timedelta(days=r.randint(0, 480))
        units = r.randint(1, 900)
        rows.append(
            f"{d.strftime('%Y-%m-%d')},{r.choice(_REGIONS)},{r.choice(_STORES)},"
            f"\"{r.choice(_PRODUCTS)}\",{units},{round(units*_money(r,4,240),2)}"
        )
    return ("\n".join(rows) + "\n").encode()


def _json(name: str, r: random.Random) -> bytes:
    obj = {
        "name": name,
        "generatedAt": datetime.utcnow().isoformat() + "Z",
        "records": [
            {
                "id": r.randint(10000, 99999),
                "product": r.choice(_PRODUCTS),
                "region": r.choice(_REGIONS),
                "store": r.choice(_STORES),
                "units": r.randint(1, 500),
                "revenue": _money(r, 100, 50000),
            }
            for _ in range(r.randint(10, 60))
        ],
    }
    return json.dumps(obj, indent=2).encode()


def _md(name: str, r: random.Random) -> bytes:
    lines = [f"# {name}", "", "> RetailCo internal reference document.", ""]
    for _ in range(r.randint(3, 6)):
        lines.append("## " + r.choice([
            "Overview", "Details", "Process", "Owners", "SLAs", "Checklist",
        ]))
        lines.append("")
        for _ in range(r.randint(3, 6)):
            lines.append("- " + _lorem(r, r.randint(6, 14)))
        lines.append("")
    return ("\n".join(lines)).encode()


def _txt(name: str, r: random.Random) -> bytes:
    return _lorem(r, r.randint(80, 240)).encode()


def _txt_fallback(name: str, r: random.Random) -> bytes:
    return (f"{name}\n\n" + _lorem(r, 120)).encode()


def _png(name: str, r: random.Random) -> bytes:
    if Image is None:
        return _tiny_png()
    w, h = 640, 360
    img = Image.new("RGB", (w, h), (r.randint(20, 60), r.randint(40, 90), r.randint(80, 160)))
    d = ImageDraw.Draw(img)
    for _ in range(r.randint(8, 20)):
        x0, y0 = r.randint(0, w), r.randint(0, h)
        x1, y1 = x0 + r.randint(20, 180), y0 + r.randint(20, 120)
        d.rectangle([x0, y0, x1, y1], fill=(r.randint(0, 255), r.randint(0, 255), r.randint(0, 255)))
    d.text((16, 16), name[:40], fill=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _jpg(name: str, r: random.Random) -> bytes:
    if Image is None:
        return _tiny_png()
    w, h = 800, 600
    img = Image.new("RGB", (w, h), (r.randint(60, 200), r.randint(60, 200), r.randint(60, 200)))
    d = ImageDraw.Draw(img)
    for _ in range(r.randint(10, 25)):
        cx, cy = r.randint(0, w), r.randint(0, h)
        rad = r.randint(10, 90)
        d.ellipse([cx - rad, cy - rad, cx + rad, cy + rad],
                  fill=(r.randint(0, 255), r.randint(0, 255), r.randint(0, 255)))
    d.text((16, 16), name[:40], fill=(0, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=82)
    return buf.getvalue()


def _tiny_png() -> bytes:
    return bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
        "0000000d49444154789c6360000002000100" "05fe02fea7d0e3450000000049454e44ae426082"
    )


_LOREM = (
    "revenue margin inventory assortment planogram markdown replenishment "
    "supplier logistics fulfillment omnichannel loyalty conversion basket "
    "shrinkage forecast promotion category vendor compliance staffing footfall "
    "clearance seasonal warehouse distribution merchandising procurement audit"
).split()


def _lorem(r: random.Random, n: int) -> str:
    words = [r.choice(_LOREM) for _ in range(n)]
    words[0] = words[0].capitalize()
    return " ".join(words) + "."


_BUILDERS = {
    "xlsx": _xlsx, "docx": _docx, "pptx": _pptx, "pdf": _pdf, "csv": _csv,
    "json": _json, "md": _md, "txt": _txt, "png": _png, "jpg": _jpg,
}


def build(ext: str, name: str, seed: int) -> tuple[bytes, str]:
    """Return (bytes, mime_type) for a file of type ``ext`` named ``name``."""
    ext = ext.lower()
    r = _rng(name, seed)
    builder = _BUILDERS.get(ext, _txt)
    data = builder(name, r)
    return data, MIME.get(ext, "application/octet-stream")
