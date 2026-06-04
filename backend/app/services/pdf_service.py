from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# ── Palette ──────────────────────────────────────────────────────────────────

_BLUE = colors.HexColor("#2563EB")
_BLUE_DARK = colors.HexColor("#1E40AF")
_BLUE_LIGHT = colors.HexColor("#EFF6FF")
_GREEN = colors.HexColor("#16A34A")
_GREEN_LIGHT = colors.HexColor("#F0FDF4")
_RED = colors.HexColor("#DC2626")
_RED_LIGHT = colors.HexColor("#FEF2F2")
_AMBER_LIGHT = colors.HexColor("#FFFBEB")
_SLATE_900 = colors.HexColor("#0F172A")
_SLATE_700 = colors.HexColor("#334155")
_SLATE_400 = colors.HexColor("#94A3B8")
_SLATE_200 = colors.HexColor("#E2E8F0")
_SLATE_50 = colors.HexColor("#F8FAFC")
_WHITE = colors.white


# ── Public API ────────────────────────────────────────────────────────────────

def gerar_relatorio_pdf(sessao: Any, stats: dict, itens: list[dict]) -> bytes:
    """Return PDF bytes for the full inventory report."""
    buf = BytesIO()

    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        rightMargin=15 * mm,
        leftMargin=15 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
        title=f"Inventário {sessao.codigo}",
        author="Inventário QR",
    )

    story: list[Any] = []

    # ── Styles ────────────────────────────────────────────────────────────────
    _ss = getSampleStyleSheet()

    def _style(name: str, **kw) -> ParagraphStyle:
        return ParagraphStyle(name, parent=_ss["Normal"], **kw)

    s_app = _style("App", fontSize=10, textColor=_BLUE, fontName="Helvetica-Bold")
    s_title = _style("Title", fontSize=18, textColor=_SLATE_900, fontName="Helvetica-Bold", spaceAfter=1 * mm)
    s_meta = _style("Meta", fontSize=8, textColor=_SLATE_400, fontName="Helvetica", spaceAfter=1 * mm)
    s_section = _style(
        "Section",
        fontSize=8,
        textColor=_SLATE_400,
        fontName="Helvetica-Bold",
        spaceBefore=4 * mm,
        spaceAfter=2 * mm,
        letterSpacing=0.8,
    )
    s_footer = _style("Footer", fontSize=7, textColor=_SLATE_400, alignment=TA_CENTER)

    # ── Header block ─────────────────────────────────────────────────────────
    story.append(Paragraph("INVENTÁRIO QR", s_app))
    story.append(Paragraph(sessao.nome, s_title))

    status_label = {"ativa": "Ativa", "concluida": "Concluída", "cancelada": "Cancelada"}
    story.append(Paragraph(
        f"Código: <b>{sessao.codigo}</b>"
        f" &nbsp;·&nbsp; Status: <b>{status_label.get(str(sessao.status.value if hasattr(sessao.status, 'value') else sessao.status), sessao.status)}</b>"
        f" &nbsp;·&nbsp; Iniciada: <b>{_fmt(sessao.data_inicio)}</b>",
        s_meta,
    ))
    story.append(Spacer(1, 3 * mm))
    story.append(HRFlowable(width="100%", thickness=2, color=_BLUE, spaceAfter=4 * mm))

    # ── Stats summary ─────────────────────────────────────────────────────────
    story.append(Paragraph("RESUMO", s_section))

    col_w = 36 * mm
    stats_data = [
        ["Total", "Conferidos", "Pendentes", "Divergências", "Progresso"],
        [
            str(stats.get("total", 0)),
            str(stats.get("conferidos", 0)),
            str(stats.get("pendentes", 0)),
            str(stats.get("divergencias", 0)),
            f"{stats.get('percentual', 0):.1f}%",
        ],
    ]
    stats_table = Table(stats_data, colWidths=[col_w] * 5)
    stats_table.setStyle(TableStyle([
        # header row
        ("BACKGROUND", (0, 0), (-1, 0), _BLUE),
        ("TEXTCOLOR", (0, 0), (-1, 0), _WHITE),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 8),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, 0), 4),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 4),
        # value row
        ("BACKGROUND", (0, 1), (-1, 1), _SLATE_50),
        ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 1), (-1, 1), 16),
        ("ALIGN", (0, 1), (-1, 1), "CENTER"),
        ("TEXTCOLOR", (1, 1), (1, 1), _GREEN),
        ("TEXTCOLOR", (3, 1), (3, 1), _RED),
        ("TOPPADDING", (0, 1), (-1, 1), 5),
        ("BOTTOMPADDING", (0, 1), (-1, 1), 5),
        # border
        ("BOX", (0, 0), (-1, -1), 0.5, _SLATE_200),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, _SLATE_200),
    ]))
    story.append(stats_table)

    # ── Items table ───────────────────────────────────────────────────────────
    story.append(Paragraph(f"ITENS DO INVENTÁRIO — {len(itens)} registros", s_section))

    # Estilos para células da tabela de itens
    s_cell = _style("Cell", fontSize=7.5, textColor=_SLATE_700, leading=10)
    s_cell_bold = _style("CellBold", fontSize=7.5, textColor=_SLATE_700, fontName="Helvetica-Bold", leading=10)
    s_cell_code = _style("CellCode", fontSize=7, textColor=colors.HexColor("#1E40AF"), fontName="Helvetica-Bold", leading=10)
    s_cell_ok = _style("CellOk", fontSize=7.5, textColor=_GREEN, fontName="Helvetica-Bold", leading=10, alignment=TA_CENTER)
    s_cell_div = _style("CellDiv", fontSize=7.5, textColor=_RED, fontName="Helvetica-Bold", leading=10, alignment=TA_CENTER)
    s_cell_pend = _style("CellPend", fontSize=7.5, textColor=colors.HexColor("#D97706"), fontName="Helvetica-Bold", leading=10, alignment=TA_CENTER)
    s_hdr = _style("Hdr", fontSize=8, textColor=_WHITE, fontName="Helvetica-Bold", leading=10, alignment=TA_CENTER)

    # Widths: total 180 mm (page content = 210 - 30 margins)
    col_widths = [22 * mm, 58 * mm, 14 * mm, 20 * mm, 16 * mm, 22 * mm, 28 * mm]

    HDR = [
        Paragraph("Código", s_hdr),
        Paragraph("Produto", s_hdr),
        Paragraph("Base", s_hdr),
        Paragraph("Contado", s_hdr),
        Paragraph("Dif.", s_hdr),
        Paragraph("Status", s_hdr),
        Paragraph("Operador", s_hdr),
    ]
    rows: list[list] = [HDR]
    for item in itens:
        diff = item.get("diferenca")
        status = str(item.get("status", ""))
        diff_str = "—" if diff is None else (f"+{diff}" if diff > 0 else str(diff))
        if status == "Divergente":
            status_par = Paragraph(status, s_cell_div)
        elif status == "Pendente":
            status_par = Paragraph(status, s_cell_pend)
        else:
            status_par = Paragraph(status, s_cell_ok)
        rows.append([
            Paragraph(str(item.get("codigo", "")), s_cell_code),
            Paragraph(str(item.get("produto", "")), s_cell),  # wrap automático em nomes longos
            Paragraph(str(item.get("quantidade_base", "")), s_cell_bold),
            Paragraph("—" if item.get("quantidade_encontrada") is None else str(item["quantidade_encontrada"]), s_cell_bold),
            Paragraph(diff_str, s_cell_bold),
            status_par,
            Paragraph(str(item.get("operador") or "—"), s_cell),
        ])

    items_table = Table(rows, colWidths=col_widths, repeatRows=1)

    cmds = [
        # header
        ("BACKGROUND", (0, 0), (-1, 0), _BLUE),
        ("TOPPADDING", (0, 0), (-1, 0), 5),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 5),
        ("LEFTPADDING", (0, 0), (-1, 0), 4),
        ("RIGHTPADDING", (0, 0), (-1, 0), 4),
        # body
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 1), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 3),
        ("LEFTPADDING", (0, 1), (-1, -1), 4),
        ("RIGHTPADDING", (0, 1), (-1, -1), 4),
        # borders
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, _SLATE_200),
    ]

    # Alternating rows + status background colors
    for i, item in enumerate(itens):
        r = i + 1
        status = item.get("status", "")
        if status == "Divergente":
            cmds.append(("BACKGROUND", (0, r), (-1, r), _RED_LIGHT))
        elif status == "Pendente":
            cmds.append(("BACKGROUND", (0, r), (-1, r), _AMBER_LIGHT))
        elif i % 2 == 1:
            cmds.append(("BACKGROUND", (0, r), (-1, r), _SLATE_50))

    items_table.setStyle(TableStyle(cmds))
    story.append(items_table)
    story.append(Spacer(1, 6 * mm))

    # ── Legend ────────────────────────────────────────────────────────────────
    legend_data = [["■ OK", "■ Divergente", "■ Pendente"]]
    legend_table = Table(legend_data, colWidths=[40 * mm, 40 * mm, 40 * mm])
    legend_table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("TEXTCOLOR", (0, 0), (0, 0), _GREEN),
        ("TEXTCOLOR", (1, 0), (1, 0), _RED),
        ("TEXTCOLOR", (2, 0), (2, 0), colors.HexColor("#D97706")),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(legend_table)

    # ── Footer ────────────────────────────────────────────────────────────────
    story.append(Spacer(1, 6 * mm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=_SLATE_200, spaceAfter=3 * mm))
    now = datetime.now(timezone.utc).strftime("%d/%m/%Y às %H:%M UTC")
    story.append(Paragraph(f"Relatório gerado em {now} · Inventário QR", s_footer))

    doc.build(story)
    return buf.getvalue()


# ── QR Label Sheet ────────────────────────────────────────────────────────────

# Color palette
_C_NAVY   = (0.118, 0.227, 0.373)   # #1E3A5F — accent bar + code text
_C_DARK   = (0.059, 0.090, 0.157)   # #0F172A — product name
_C_CHIP   = (0.937, 0.953, 0.969)   # #EFF3F8 — code chip background
_C_BORDER = (0.796, 0.835, 0.882)   # #CBD5E1 — label border / divider
_C_MUTED  = (0.576, 0.639, 0.714)   # #93A3B4 — brand mark

# Grid: 2 columns × 7 rows = 14 labels per A4 page
_COLS, _ROWS = 2, 7
_MARGIN_X  = 12 * mm
_MARGIN_Y  = 15 * mm
_GAP_X     = 6  * mm
_GAP_Y     = 4  * mm


def _wrap(canvas_obj, text: str, font: str, size: float, max_w: float) -> list[str]:
    """Word-wrap text to fit within max_w points."""
    words = text.split()
    lines: list[str] = []
    cur = ""
    for w in words:
        test = (cur + " " + w).strip()
        if canvas_obj.stringWidth(test, font, size) <= max_w:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def gerar_etiquetas_pdf(itens: list[dict], nome_sessao: str = "") -> bytes:
    """
    Printable A4 label sheet — 2 columns × 7 rows = 14 labels per page.

    Each label layout (left → right):
      ▐ accent bar │ QR code │ divider │ product name + code chip
    """
    import qrcode as qrcode_lib

    PAGE_W, PAGE_H = A4
    avail_w = PAGE_W - 2 * _MARGIN_X
    avail_h = PAGE_H - 2 * _MARGIN_Y
    LW = (avail_w - (_COLS - 1) * _GAP_X) / _COLS   # label width
    LH = (avail_h - (_ROWS - 1) * _GAP_Y) / _ROWS   # label height

    ACCENT  = 3   * mm    # accent bar width
    PAD     = 2.5 * mm    # inner padding
    QR_SZ   = LH  - 2 * PAD   # QR fills label height minus top/bottom pad
    DIV_X   = ACCENT + PAD + QR_SZ + PAD   # x offset of vertical divider
    TX      = DIV_X + PAD     # text area start x (relative to label origin)
    TW      = LW - TX - PAD   # text area width

    per_page = _COLS * _ROWS
    buf = BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=A4)
    c.setTitle(f"Etiquetas — {nome_sessao}" if nome_sessao else "Etiquetas QR")

    for idx, item in enumerate(itens):
        pos = idx % per_page
        if pos == 0 and idx > 0:
            c.showPage()

        col = pos % _COLS
        row = pos // _COLS

        # Absolute bottom-left corner of this label
        lx = _MARGIN_X + col * (LW + _GAP_X)
        ly = PAGE_H - _MARGIN_Y - (row + 1) * LH - row * _GAP_Y

        # ── 1. White background + border ─────────────────────────────────
        c.setFillColorRGB(1, 1, 1)
        c.setStrokeColorRGB(*_C_BORDER)
        c.setLineWidth(0.5)
        c.rect(lx, ly, LW, LH, fill=1, stroke=1)

        # ── 2. Left accent bar (navy) ─────────────────────────────────────
        c.setFillColorRGB(*_C_NAVY)
        c.rect(lx, ly, ACCENT, LH, fill=1, stroke=0)

        # ── 3. QR code ───────────────────────────────────────────────────
        codigo = str(item.get("codigo", "")).strip()
        try:
            qr = qrcode_lib.QRCode(
                version=None,
                error_correction=qrcode_lib.constants.ERROR_CORRECT_M,
                box_size=12,
                border=1,
            )
            qr.add_data(codigo)
            qr.make(fit=True)
            qr_img = qr.make_image(fill_color="black", back_color="white")
            qr_buf = BytesIO()
            qr_img.save(qr_buf, format="PNG")
            qr_buf.seek(0)
            c.drawImage(
                ImageReader(qr_buf),
                lx + ACCENT + PAD,
                ly + PAD,
                width=QR_SZ, height=QR_SZ,
                mask="auto",
            )
        except Exception:
            pass

        # ── 4. Vertical divider ───────────────────────────────────────────
        c.setStrokeColorRGB(*_C_BORDER)
        c.setLineWidth(0.4)
        c.line(lx + DIV_X, ly + PAD, lx + DIV_X, ly + LH - PAD)

        # ── 5. Product name (bold, wraps 2 lines) ─────────────────────────
        produto = str(item.get("produto", "")).strip()
        name_lines = _wrap(c, produto, "Helvetica-Bold", 8, TW)[:2]

        # Vertical layout: name block + small gap + code chip
        LINE_H     = 10.5  # pts per name line
        CHIP_H     = 11    # pts — height of code chip box
        CHIP_PAD_V = 2     # vertical padding inside chip
        GAP_NC     = 4     # gap between name block and code chip

        total_block_h = len(name_lines) * LINE_H + GAP_NC + CHIP_H
        block_top = ly + LH / 2 + total_block_h / 2   # centred vertically

        # Draw name lines
        c.setFont("Helvetica-Bold", 8)
        c.setFillColorRGB(*_C_DARK)
        for i, line in enumerate(name_lines):
            c.drawString(lx + TX, block_top - (i + 1) * LINE_H, line)

        # ── 6. Code chip ─────────────────────────────────────────────────
        chip_y = block_top - len(name_lines) * LINE_H - GAP_NC - CHIP_H
        chip_label = codigo if len(codigo) <= 24 else codigo[:22] + "…"
        chip_text_w = c.stringWidth(chip_label, "Helvetica-Bold", 7.5)
        chip_w = min(chip_text_w + 10, TW)

        c.setFillColorRGB(*_C_CHIP)
        c.setStrokeColorRGB(*_C_BORDER)
        c.setLineWidth(0.4)
        c.roundRect(lx + TX, chip_y, chip_w, CHIP_H, 2, fill=1, stroke=1)

        c.setFont("Helvetica-Bold", 7.5)
        c.setFillColorRGB(*_C_NAVY)
        c.drawString(lx + TX + 5, chip_y + CHIP_PAD_V + 1, chip_label)

        # ── 7. Brand mark (bottom-right, very subtle) ─────────────────────
        c.setFont("Helvetica", 4.5)
        c.setFillColorRGB(*_C_MUTED)
        c.drawRightString(lx + LW - PAD, ly + 2.5, "Inventário QR")

    c.save()
    return buf.getvalue()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fmt(dt: Any) -> str:
    if dt is None:
        return "—"
    if isinstance(dt, datetime):
        return dt.strftime("%d/%m/%Y %H:%M")
    try:
        d = datetime.fromisoformat(str(dt).replace("Z", "+00:00"))
        return d.strftime("%d/%m/%Y %H:%M")
    except Exception:
        return str(dt)
