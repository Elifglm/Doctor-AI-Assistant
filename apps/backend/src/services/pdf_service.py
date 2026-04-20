"""PDF report generator — creates HBYS-format clinical reports."""

from __future__ import annotations

import io
import logging
import os
import platform
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    HRFlowable,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Font registration (Turkish character support)
# ---------------------------------------------------------------------------

_FONTS_REGISTERED = False


def _register_fonts() -> None:
    """Register system fonts with Turkish character support."""
    global _FONTS_REGISTERED
    if _FONTS_REGISTERED:
        return

    font_dirs = []
    if platform.system() == "Darwin":
        font_dirs.append("/System/Library/Fonts/Supplemental")
    elif platform.system() == "Windows":
        font_dirs.append(r"C:\Windows\Fonts")
    else:
        font_dirs.extend(["/usr/share/fonts/truetype/dejavu", "/usr/share/fonts"])

    # Try Arial first, then DejaVu as fallback
    font_map = {
        "HastaneFont": ["Arial.ttf", "DejaVuSans.ttf"],
        "HastaneFont-Bold": ["Arial Bold.ttf", "DejaVuSans-Bold.ttf"],
    }

    for font_name, candidates in font_map.items():
        registered = False
        for candidate in candidates:
            for font_dir in font_dirs:
                font_path = os.path.join(font_dir, candidate)
                if os.path.exists(font_path):
                    try:
                        pdfmetrics.registerFont(TTFont(font_name, font_path))
                        registered = True
                        break
                    except Exception:
                        continue
            if registered:
                break

        if not registered:
            logger.warning("Font '%s' not registered, using Helvetica", font_name)

    _FONTS_REGISTERED = True


# ---------------------------------------------------------------------------
# Styles
# ---------------------------------------------------------------------------

def _build_styles() -> dict[str, ParagraphStyle]:
    """Build paragraph styles for hospital report."""
    base = getSampleStyleSheet()

    font = "HastaneFont"
    font_bold = "HastaneFont-Bold"

    # Check if fonts registered, fallback to Helvetica
    try:
        pdfmetrics.getFont(font)
    except KeyError:
        font = "Helvetica"
        font_bold = "Helvetica-Bold"

    return {
        "hospital_name": ParagraphStyle(
            "HospitalName", parent=base["Normal"],
            fontName=font_bold, fontSize=14, alignment=1,
            spaceAfter=2 * mm,
        ),
        "report_title": ParagraphStyle(
            "ReportTitle", parent=base["Normal"],
            fontName=font_bold, fontSize=12, alignment=1,
            spaceAfter=4 * mm, textColor=colors.HexColor("#1e3a5f"),
        ),
        "section_title": ParagraphStyle(
            "SectionTitle", parent=base["Normal"],
            fontName=font_bold, fontSize=9, spaceBefore=3 * mm,
            spaceAfter=1.5 * mm, textColor=colors.HexColor("#1e3a5f"),
        ),
        "section_content": ParagraphStyle(
            "SectionContent", parent=base["Normal"],
            fontName=font, fontSize=9, leading=13,
            spaceAfter=1 * mm,
        ),
        "meta_label": ParagraphStyle(
            "MetaLabel", parent=base["Normal"],
            fontName=font_bold, fontSize=9,
        ),
        "meta_value": ParagraphStyle(
            "MetaValue", parent=base["Normal"],
            fontName=font, fontSize=9,
        ),
        "footer": ParagraphStyle(
            "Footer", parent=base["Normal"],
            fontName=font, fontSize=7, textColor=colors.grey,
            alignment=1,
        ),
        "signature": ParagraphStyle(
            "Signature", parent=base["Normal"],
            fontName=font, fontSize=9, alignment=2,
            spaceBefore=8 * mm,
        ),
        "signature_bold": ParagraphStyle(
            "SignatureBold", parent=base["Normal"],
            fontName=font_bold, fontSize=9, alignment=2,
        ),
    }


# ---------------------------------------------------------------------------
# Section display config
# ---------------------------------------------------------------------------

# Sections to skip in PDF (shown separately or not relevant)
_SKIP_SECTIONS = {"icd10_list", "sut_tetkik_list"}

# Vital signs that should be shown in a compact table
_VITAL_KEYS = {
    "sistolik", "diyastolik", "nabiz", "ates", "solunum_sayisi",
    "spo2", "kilo", "boy",
}

_VITAL_LABELS = {
    "sistolik": "Sistolik (mmHg)",
    "diyastolik": "Diyastolik (mmHg)",
    "nabiz": "Nabiz (/dk)",
    "ates": "Ates (°C)",
    "solunum_sayisi": "Solunum (/dk)",
    "spo2": "SpO2 (%)",
    "kilo": "Kilo (kg)",
    "boy": "Boy (cm)",
}

_EMPTY_MARKERS = {"", "BELIRTILMEDI", "BELIRTILMEDI.", "BILGI YOK"}


# ---------------------------------------------------------------------------
# PDF Generation
# ---------------------------------------------------------------------------

def generate_report_pdf(
    session_data: dict,
    report_data: dict,
    hospital_name: str = "KLINIK ASISTAN HASTANE BILGI SISTEMI",
) -> bytes:
    """Generate a PDF report and return raw bytes.

    Args:
        session_data: dict with patient_id, patient_name, doctor_name, visit_type, created_at
        report_data: dict with sections list (key, title, content), approved_at
    """
    _register_fonts()
    styles = _build_styles()

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=1.5 * cm,
        bottomMargin=2 * cm,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
    )

    elements: list = []

    # ---- Header ----
    elements.append(Paragraph(hospital_name, styles["hospital_name"]))
    elements.append(Paragraph("ANAMNEZ RAPORU", styles["report_title"]))
    elements.append(HRFlowable(
        width="100%", thickness=1, color=colors.HexColor("#1e3a5f"),
        spaceAfter=4 * mm,
    ))

    # ---- Patient/Doctor Info Table ----
    created = session_data.get("created_at", "")
    if isinstance(created, datetime):
        created = created.strftime("%d.%m.%Y %H:%M")
    elif isinstance(created, str) and "T" in created:
        try:
            created = datetime.fromisoformat(created.replace("Z", "+00:00")).strftime("%d.%m.%Y %H:%M")
        except ValueError:
            pass

    visit_labels = {
        "ilk_muayene": "Ilk Muayene",
        "kontrol": "Kontrol",
        "konsultasyon": "Konsultasyon",
        "acil": "Acil",
    }

    meta_data = [
        [
            Paragraph("<b>Hasta Adi:</b>", styles["meta_label"]),
            Paragraph(session_data.get("patient_name", "-"), styles["meta_value"]),
            Paragraph("<b>Hasta ID:</b>", styles["meta_label"]),
            Paragraph(session_data.get("patient_id", "-"), styles["meta_value"]),
        ],
        [
            Paragraph("<b>Doktor:</b>", styles["meta_label"]),
            Paragraph(session_data.get("doctor_name", "-"), styles["meta_value"]),
            Paragraph("<b>Tarih:</b>", styles["meta_label"]),
            Paragraph(created, styles["meta_value"]),
        ],
        [
            Paragraph("<b>Ziyaret Tipi:</b>", styles["meta_label"]),
            Paragraph(
                visit_labels.get(session_data.get("visit_type", ""), session_data.get("visit_type", "-")),
                styles["meta_value"],
            ),
            Paragraph("<b>Rapor No:</b>", styles["meta_label"]),
            Paragraph(str(report_data.get("report_id", "-")), styles["meta_value"]),
        ],
    ]

    meta_table = Table(meta_data, colWidths=[3 * cm, 5.5 * cm, 3 * cm, 5.5 * cm])
    meta_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8f9fa")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#dee2e6")),
        ("LINEBELOW", (0, 0), (-1, -2), 0.25, colors.HexColor("#dee2e6")),
    ]))
    elements.append(meta_table)
    elements.append(Spacer(1, 4 * mm))

    # ---- Sections ----
    sections = report_data.get("sections", [])

    # Collect vitals separately
    vitals: list[tuple[str, str]] = []
    normal_sections: list[dict] = []

    for s in sections:
        key = s.get("key", "")
        if key in _SKIP_SECTIONS:
            continue
        if key in _VITAL_KEYS:
            val = s.get("content", "").strip()
            if val and val not in _EMPTY_MARKERS:
                vitals.append((_VITAL_LABELS.get(key, s.get("title", key)), val))
        else:
            normal_sections.append(s)

    # Vital signs table (compact)
    if vitals:
        elements.append(Paragraph("VITAL BULGULAR", styles["section_title"]))
        vital_rows = []
        # 4 vitals per row
        for i in range(0, len(vitals), 4):
            row = []
            for j in range(4):
                if i + j < len(vitals):
                    label, val = vitals[i + j]
                    row.extend([
                        Paragraph(f"<b>{label}</b>", styles["meta_label"]),
                        Paragraph(val, styles["meta_value"]),
                    ])
                else:
                    row.extend(["", ""])
            vital_rows.append(row)

        vt = Table(vital_rows, colWidths=[3.5 * cm, 1.5 * cm] * 4)
        vt.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#dee2e6")),
            ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#e9ecef")),
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8f9fa")),
        ]))
        elements.append(vt)
        elements.append(Spacer(1, 2 * mm))

    # Normal sections — each in a bordered box
    for s in normal_sections:
        title = s.get("title", "")
        content = s.get("content", "").strip()

        # Show "BELIRTILMEDI" for empty sections
        if not content or content in _EMPTY_MARKERS:
            display_content = "Belirtilmedi"
        else:
            # Format content: replace ---- with newlines
            lines = content.replace("----", "\n").split("\n")
            formatted_lines = []
            for line in lines:
                line = line.strip()
                if line and line not in _EMPTY_MARKERS:
                    line = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                    formatted_lines.append(line)
            display_content = "<br/>".join(formatted_lines) if formatted_lines else "Belirtilmedi"

        # Build a table with title header and content body
        section_table_data = [
            [Paragraph(title.upper(), styles["section_title"])],
            [Paragraph(display_content, styles["section_content"])],
        ]
        section_table = Table(section_table_data, colWidths=[17 * cm])
        section_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (0, 0), 3),
            ("BOTTOMPADDING", (0, 0), (0, 0), 1),
            ("TOPPADDING", (0, 1), (0, 1), 2),
            ("BOTTOMPADDING", (0, 1), (0, 1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#f0f4f8")),
            ("BACKGROUND", (0, 1), (0, 1), colors.white),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ("LINEBELOW", (0, 0), (0, 0), 0.25, colors.HexColor("#cbd5e1")),
        ]))
        elements.append(section_table)
        elements.append(Spacer(1, 2 * mm))

    # ---- ICD-10 Section (boxed) ----
    icd_section = next((s for s in sections if s.get("key") == "icd10_list"), None)
    icd_content = (icd_section.get("content", "").strip() if icd_section else "")
    if icd_content and icd_content not in _EMPTY_MARKERS:
        icd_lines = []
        for line in icd_content.split("\n"):
            line = line.strip()
            if line:
                line = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                icd_lines.append(f"• {line}")
        icd_text = "<br/>".join(icd_lines)
    else:
        icd_text = "Belirtilmedi"

    icd_table = Table(
        [[Paragraph("ICD-10 TANI KODLARI", styles["section_title"])],
         [Paragraph(icd_text, styles["section_content"])]],
        colWidths=[17 * cm],
    )
    icd_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (0, 0), 3), ("BOTTOMPADDING", (0, 0), (0, 0), 1),
        ("TOPPADDING", (0, 1), (0, 1), 2), ("BOTTOMPADDING", (0, 1), (0, 1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#eff6ff")),
        ("BACKGROUND", (0, 1), (0, 1), colors.white),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#93c5fd")),
        ("LINEBELOW", (0, 0), (0, 0), 0.25, colors.HexColor("#93c5fd")),
    ]))
    elements.append(icd_table)
    elements.append(Spacer(1, 2 * mm))

    # ---- SUT Tetkik Section (boxed) ----
    sut_section = next((s for s in sections if s.get("key") == "sut_tetkik_list"), None)
    sut_content = (sut_section.get("content", "").strip() if sut_section else "")
    if sut_content and sut_content not in _EMPTY_MARKERS:
        sut_lines = []
        for line in sut_content.split("\n"):
            line = line.strip()
            if line:
                line = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                sut_lines.append(f"• {line}")
        sut_text = "<br/>".join(sut_lines)
    else:
        sut_text = "Belirtilmedi"

    sut_table = Table(
        [[Paragraph("ISTENEN TETKIK / TAHLILLER", styles["section_title"])],
         [Paragraph(sut_text, styles["section_content"])]],
        colWidths=[17 * cm],
    )
    sut_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (0, 0), 3), ("BOTTOMPADDING", (0, 0), (0, 0), 1),
        ("TOPPADDING", (0, 1), (0, 1), 2), ("BOTTOMPADDING", (0, 1), (0, 1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#f0fdf4")),
        ("BACKGROUND", (0, 1), (0, 1), colors.white),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#86efac")),
        ("LINEBELOW", (0, 0), (0, 0), 0.25, colors.HexColor("#86efac")),
    ]))
    elements.append(sut_table)
    elements.append(Spacer(1, 2 * mm))

    # ---- Separator ----
    elements.append(Spacer(1, 6 * mm))
    elements.append(HRFlowable(
        width="100%", thickness=0.5, color=colors.HexColor("#dee2e6"),
        spaceAfter=4 * mm,
    ))

    # ---- Signature ----
    approved_at = report_data.get("approved_at", "")
    if isinstance(approved_at, datetime):
        approved_at = approved_at.strftime("%d.%m.%Y %H:%M")
    elif isinstance(approved_at, str) and approved_at and "T" in approved_at:
        try:
            approved_at = datetime.fromisoformat(approved_at.replace("Z", "+00:00")).strftime("%d.%m.%Y %H:%M")
        except ValueError:
            pass

    doctor_name = session_data.get("doctor_name", "")
    elements.append(Paragraph(f"Onay Tarihi: {approved_at or '-'}", styles["signature"]))
    elements.append(Spacer(1, 8 * mm))
    elements.append(Paragraph("_________________________", styles["signature"]))
    # Avoid "Dr. Dr." duplication
    dr_display = doctor_name if doctor_name.startswith("Dr.") else f"Dr. {doctor_name}"
    elements.append(Paragraph(dr_display, styles["signature_bold"]))
    elements.append(Paragraph("Imza / Kase", styles["signature"]))

    # ---- Footer ----
    elements.append(Spacer(1, 10 * mm))
    now = datetime.now().strftime("%d.%m.%Y %H:%M")
    elements.append(Paragraph(
        f"Bu rapor KlinikAsistan sistemi tarafindan {now} tarihinde olusturulmustur. "
        "Elektronik ortamda uretilmistir.",
        styles["footer"],
    ))

    # Build
    doc.build(elements)
    return buffer.getvalue()
