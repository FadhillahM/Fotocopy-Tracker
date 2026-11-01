"""
Report service — ekspor laporan kas ke PDF (ReportLab) dan Excel (openpyxl).
Mendukung parameter expenses (list Expense) untuk laporan kas bersih.
"""
import io
from datetime import datetime
from flask import send_file, make_response


# ── Helpers ───────────────────────────────────────────────────────────────────

def _group_by_date(jobs: list) -> dict:
    """Kelompokkan jobs per tanggal, urutkan tanggal dari terlama ke terbaru."""
    groups = {}
    for j in jobs:
        key = j.start_time.strftime("%d/%m/%Y") if j.start_time else "Tanpa tanggal"
        groups.setdefault(key, []).append(j)
    return dict(sorted(groups.items(),
                       key=lambda x: datetime.strptime(x[0], "%d/%m/%Y")
                       if x[0] != "Tanpa tanggal" else datetime.min))


# ── Excel ─────────────────────────────────────────────────────────────────────

def export_excel_laporan(jobs: list, device, period_label: str, price: int,
                         date_from: str = None, date_to: str = None,
                         expenses: list = None):
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Laporan Kas"

    C_BLUE   = "2563EB"; C_BLUE_LT = "EFF6FF"; C_DBLUE = "1D4ED8"
    C_GREEN  = "16A34A"; C_GREEN_LT = "F0FDF4"
    C_RED    = "DC2626"; C_RED_LT   = "FEF2F2"
    C_GRAY   = "F8FAFC"; C_TOTAL   = "DBEAFE"
    C_WHITE  = "FFFFFF"; C_TEXT    = "1E293B"; C_MUTED = "64748B"
    C_ORANGE = "EA580C"; C_ORANGE_LT = "FFF7ED"

    def font(bold=False, color=C_TEXT, size=10, italic=False):
        return Font(name="Calibri", bold=bold, color=color, size=size, italic=italic)

    def fill(color):
        return PatternFill("solid", fgColor=color)

    def border(color="CBD5E1", style="thin"):
        s = Side(style=style, color=color)
        return Border(left=s, right=s, top=s, bottom=s)

    def align(h="left", v="center", wrap=False):
        return Alignment(horizontal=h, vertical=v, wrap_text=wrap)

    col_widths = [14, 8, 32, 14, 10, 16, 10]
    for i, w in enumerate(col_widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w

    row = 1

    # Header
    ws.row_dimensions[row].height = 32
    ws.merge_cells(f"A{row}:G{row}")
    c = ws[f"A{row}"]
    c.value = "LAPORAN KAS FOTOCOPY"; c.font = font(bold=True, color=C_WHITE, size=14)
    c.fill = fill(C_BLUE); c.alignment = align("center")
    row += 1

    ws.merge_cells(f"A{row}:G{row}")
    c = ws[f"A{row}"]
    c.value = f"{device.model or device.ip_address}  ·  Periode: {period_label}"
    c.font = font(italic=True, color=C_WHITE, size=10)
    c.fill = fill(C_BLUE); c.alignment = align("center")
    row += 1

    ws.merge_cells(f"A{row}:G{row}")
    c = ws[f"A{row}"]
    c.value = f"Dicetak: {datetime.now().strftime('%d/%m/%Y %H:%M')}  ·  Harga: Rp {price:,}/lembar"
    c.font = font(italic=True, color=C_MUTED, size=9)
    c.fill = fill(C_BLUE_LT); c.alignment = align("center")
    row += 2

    # ── Ringkasan ──────────────────────────────────────────────────────────
    total_lembar      = sum(j.total_sheets for j in jobs if j.status == "OK")
    total_biaya       = total_lembar * price
    total_job         = len(jobs)
    total_gagal       = sum(1 for j in jobs if j.status != "OK")
    total_ok_lembar   = sum(j.total_sheets for j in jobs if j.status == "OK")
    total_ng_lembar   = sum(j.total_sheets for j in jobs if j.status == "NG")
    total_stop_lembar = sum(j.total_sheets for j in jobs if j.status == "STOP")
    total_kerugian_lembar = total_ng_lembar + total_stop_lembar
    total_kerugian_rupiah = total_kerugian_lembar * price
    saldo_bersih     = total_biaya - total_kerugian_rupiah

    ws.merge_cells(f"A{row}:G{row}")
    c = ws[f"A{row}"]
    c.value = "RINGKASAN"; c.font = font(bold=True, color=C_BLUE, size=10)
    row += 1

    summary_rows = [
        ("Total OK",             f"{total_ok_lembar:,} lembar"),
        ("Total NG",             f"{total_ng_lembar:,} lembar"),
        ("Total STOP",           f"{total_stop_lembar:,} lembar"),
        ("Pendapatan (cetak)",   f"Rp {total_biaya:,}"),
        ("Total Kerugian (NG/STOP)", f"Rp {total_kerugian_rupiah:,}"),
        ("Saldo Bersih",         f"Rp {saldo_bersih:,}"),
    ]
    for label, val in summary_rows:
        is_saldo = label == "Saldo Bersih"
        is_neg   = label in ("Total NG", "Total STOP", "Total Kerugian (NG/STOP)")
        ws[f"A{row}"].value = label
        ws[f"A{row}"].font  = font(color=C_MUTED, size=9)
        ws[f"B{row}"].value = val
        if is_saldo:
            color_val = C_GREEN if saldo_bersih >= 0 else C_RED
        elif is_neg:
            color_val = C_RED
        else:
            color_val = C_DBLUE
        ws[f"B{row}"].font  = font(bold=True, color=color_val, size=10)
        ws[f"B{row}"].alignment = align("left")
        row += 1
    row += 1

    # ── Tabel Detail Cetak ─────────────────────────────────────────────────
    headers = ["Tanggal", "Jam", "Nama Job", "Pengguna", "Lembar", "Biaya", "Status"]
    ws.row_dimensions[row].height = 20
    for col, h in enumerate(headers, 1):
        c = ws.cell(row=row, column=col, value=h)
        c.font = font(bold=True, color=C_WHITE, size=10)
        c.fill = fill(C_BLUE)
        c.alignment = align("center" if col >= 5 else "left")
        c.border = border(C_WHITE)
    row += 1

    groups = _group_by_date(jobs)
    for tgl, day_jobs in groups.items():
        day_lembar = 0; day_biaya = 0; first_in_day = True
        for j in day_jobs:
            biaya = j.total_sheets * price if j.status == "OK" else 0
            day_lembar += j.total_sheets if j.status == "OK" else 0
            day_biaya  += biaya
            is_fail = j.status != "OK"
            row_bg  = C_RED_LT if is_fail else (C_GRAY if row % 2 == 0 else C_WHITE)
            ws.row_dimensions[row].height = 16

            vals = [tgl if first_in_day else "",
                    j.start_time.strftime("%H:%M") if j.start_time else "-",
                    (j.job_name or "-")[:40], j.username or "-",
                    j.total_sheets, f"Rp {biaya:,}" if biaya > 0 else "-", j.status]
            for col, val in enumerate(vals, 1):
                c = ws.cell(row=row, column=col, value=val)
                c.fill = fill(row_bg); c.border = border()
                c.font = font(color=C_RED if is_fail else C_TEXT, size=9,
                              bold=(col == 1 and first_in_day))
                c.alignment = align("center" if col in (2, 5, 6, 7) else "left")
            first_in_day = False; row += 1

        # Subtotal
        ws.row_dimensions[row].height = 17
        ws.merge_cells(f"A{row}:D{row}")
        c = ws[f"A{row}"]
        c.value = f"  Subtotal  {tgl}"; c.font = font(bold=True, color=C_BLUE, size=9)
        c.fill = fill(C_TOTAL); c.alignment = align()
        for col in range(1, 8):
            ws.cell(row=row, column=col).fill = fill(C_TOTAL)
            ws.cell(row=row, column=col).border = border(C_BLUE_LT)
        ws.cell(row=row, column=5).value = day_lembar
        ws.cell(row=row, column=5).font  = font(bold=True, color=C_BLUE, size=9)
        ws.cell(row=row, column=5).alignment = align("center")
        ws.cell(row=row, column=6).value = f"Rp {day_biaya:,}"
        ws.cell(row=row, column=6).font  = font(bold=True, color=C_BLUE, size=9)
        ws.cell(row=row, column=6).alignment = align("right")
        row += 1

    row += 1

    # Grand Total Cetak
    ws.row_dimensions[row].height = 22
    ws.merge_cells(f"A{row}:D{row}")
    for col in range(1, 8):
        ws.cell(row=row, column=col).fill = fill(C_DBLUE)
        ws.cell(row=row, column=col).border = border(C_DBLUE)
    c = ws[f"A{row}"]
    c.value = "  TOTAL PENDAPATAN CETAK"; c.font = font(bold=True, color=C_WHITE, size=11)
    c.fill = fill(C_DBLUE); c.alignment = align()
    ws.cell(row=row, column=5).value = total_lembar
    ws.cell(row=row, column=5).font  = font(bold=True, color=C_WHITE, size=11)
    ws.cell(row=row, column=5).alignment = align("center")
    ws.cell(row=row, column=6).value = f"Rp {total_biaya:,}"
    ws.cell(row=row, column=6).font  = font(bold=True, color=C_WHITE, size=11)
    ws.cell(row=row, column=6).alignment = align("right")
    row += 1

    # ── Saldo Bersih ────────────────────────────────────────────────────────
    saldo_color = C_GREEN if saldo_bersih >= 0 else C_RED
    ws.merge_cells(f"A{row}:C{row}")
    c = ws[f"A{row}"]
    c.value = "  SALDO BERSIH (Pendapatan − Total Kerugian NG/STOP)"
    c.font = font(bold=True, color=C_WHITE, size=11)
    c.fill = fill(saldo_color); c.alignment = align()
    ws.cell(row=row, column=4).value = f"Rp {saldo_bersih:,}"
    ws.cell(row=row, column=4).font  = font(bold=True, color=C_WHITE, size=11)
    ws.cell(row=row, column=4).fill  = fill(saldo_color)
    ws.cell(row=row, column=4).alignment = align("right")
    ws.row_dimensions[row].height = 24

    # Freeze
    for r in ws.iter_rows():
        if r[0].value == "Tanggal":
            ws.freeze_panes = ws.cell(row=r[0].row + 1, column=1)
            break

    output = io.BytesIO()
    wb.save(output); output.seek(0)

    fn = (f"laporan_{(device.hostname or 'mesin').replace(' ','_')}_"
          f"{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx")
    return send_file(output,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True, download_name=fn)


# ── Excel: Riwayat (raw job list, tanpa perhitungan kas) ───────────────────────

def export_excel(jobs: list, device):
    """Ekspor daftar riwayat job (halaman /history) ke Excel — tabel mentah,
    tidak menghitung biaya/saldo seperti export_excel_laporan."""
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Riwayat"

    C_BLUE  = "2563EB"; C_WHITE = "FFFFFF"; C_TEXT = "1E293B"
    C_GRAY  = "F8FAFC"; C_RED_LT = "FEF2F2"; C_RED = "DC2626"

    def font(bold=False, color=C_TEXT, size=10):
        return Font(name="Calibri", bold=bold, color=color, size=size)

    def fill(color):
        return PatternFill("solid", fgColor=color)

    def border(color="CBD5E1"):
        s = Side(style="thin", color=color)
        return Border(left=s, right=s, top=s, bottom=s)

    def align(h="left", v="center"):
        return Alignment(horizontal=h, vertical=v)

    headers = ["Tanggal", "Jam", "Tipe", "Nama Job", "Pengguna",
               "Lembar", "Copies", "Total Lembar", "Ukuran", "Status", "Sumber"]
    col_widths = [12, 8, 8, 32, 16, 8, 8, 12, 8, 10, 10]
    for i, w in enumerate(col_widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w

    row = 1
    ws.merge_cells(f"A{row}:K{row}")
    c = ws[f"A{row}"]
    c.value = f"RIWAYAT CETAK — {device.model or device.ip_address}"
    c.font = font(bold=True, color=C_WHITE, size=13)
    c.fill = fill(C_BLUE); c.alignment = align("center")
    ws.row_dimensions[row].height = 28
    row += 1

    ws.merge_cells(f"A{row}:K{row}")
    c = ws[f"A{row}"]
    c.value = f"Dicetak: {datetime.now().strftime('%d/%m/%Y %H:%M')}  ·  Total: {len(jobs)} job"
    c.font = font(color=C_TEXT, size=9); c.alignment = align("center")
    row += 2

    for col, h in enumerate(headers, 1):
        c = ws.cell(row=row, column=col, value=h)
        c.font = font(bold=True, color=C_WHITE, size=10)
        c.fill = fill(C_BLUE); c.border = border(C_WHITE)
        c.alignment = align("center")
    ws.row_dimensions[row].height = 20
    row += 1

    for j in jobs:
        is_fail = j.status != "OK"
        row_bg = C_RED_LT if is_fail else (C_GRAY if row % 2 == 0 else C_WHITE)
        vals = [
            j.start_time.strftime("%d/%m/%Y") if j.start_time else "-",
            j.start_time.strftime("%H:%M") if j.start_time else "-",
            "Print" if j.job_type == "print" else "Copy",
            j.job_name or "-", j.username or "-",
            j.sheets, j.copies, j.total_sheets,
            j.paper_size or "-", j.status,
            "Manual" if j.source == "manual" else "Auto",
        ]
        for col, val in enumerate(vals, 1):
            c = ws.cell(row=row, column=col, value=val)
            c.fill = fill(row_bg); c.border = border()
            c.font = font(color=C_RED if is_fail else C_TEXT, size=9)
            c.alignment = align("center" if col in (1, 2, 3, 6, 7, 8, 9, 10, 11) else "left")
        row += 1

    ws.freeze_panes = ws.cell(row=4, column=1)

    output = io.BytesIO()
    wb.save(output); output.seek(0)

    fn = (f"riwayat_{(device.hostname or 'mesin').replace(' ','_')}_"
          f"{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx")
    return send_file(output,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True, download_name=fn)


# ── PDF via ReportLab ─────────────────────────────────────────────────────────

def export_pdf_response(jobs: list, device, period_label: str,
                         price: int, filename: str, expenses: list = None):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import cm
    from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle,
                                    Paragraph, Spacer)
    from reportlab.lib.styles import ParagraphStyle

    expenses = expenses or []

    buffer = io.BytesIO()
    doc    = SimpleDocTemplate(buffer, pagesize=A4,
                               leftMargin=1.5*cm, rightMargin=1.5*cm,
                               topMargin=1.5*cm, bottomMargin=1.5*cm)
    story  = []

    BLUE   = colors.HexColor("#2563EB"); DBLUE = colors.HexColor("#1D4ED8")
    LBLUE  = colors.HexColor("#DBEAFE"); RED   = colors.HexColor("#DC2626")
    GREEN  = colors.HexColor("#16A34A"); GRAY  = colors.HexColor("#F8FAFC")
    MUTED  = colors.HexColor("#64748B"); ORANGE= colors.HexColor("#EA580C")
    ORANGE_LT = colors.HexColor("#FFF7ED")

    def P(text, size=9, bold=False, color=colors.black, align="LEFT"):
        style = ParagraphStyle("x", fontSize=size,
                               fontName="Helvetica-Bold" if bold else "Helvetica",
                               textColor=color,
                               alignment={"LEFT":0,"CENTER":1,"RIGHT":2}[align])
        return Paragraph(str(text), style)

    # Judul
    story.append(P("LAPORAN KAS FOTOCOPY", size=14, bold=True, color=BLUE, align="CENTER"))
    story.append(Spacer(1, 4))
    story.append(P(f"{device.model or device.ip_address}  ·  Periode: {period_label}",
                   size=9, color=MUTED, align="CENTER"))
    story.append(P(f"Dicetak: {datetime.now().strftime('%d/%m/%Y %H:%M')}  ·  Harga: Rp {price:,}/lembar",
                   size=8, color=MUTED, align="CENTER"))
    story.append(Spacer(1, 10))

    total_lembar      = sum(j.total_sheets for j in jobs if j.status == "OK")
    total_biaya       = total_lembar * price
    total_ok_lembar   = sum(j.total_sheets for j in jobs if j.status == "OK")
    total_ng_lembar   = sum(j.total_sheets for j in jobs if j.status == "NG")
    total_stop_lembar = sum(j.total_sheets for j in jobs if j.status == "STOP")
    total_kerugian_lembar = total_ng_lembar + total_stop_lembar
    total_kerugian_rupiah = total_kerugian_lembar * price
    saldo_bersih     = total_biaya - total_kerugian_rupiah
    saldo_color      = GREEN if saldo_bersih >= 0 else RED

    # Ringkasan lembar: OK / NG / STOP
    lembar_data = [
        ["Total OK", "Total NG", "Total STOP"],
        [f"{total_ok_lembar:,} lembar", f"{total_ng_lembar:,} lembar", f"{total_stop_lembar:,} lembar"],
    ]
    lembar_tbl = Table(lembar_data, colWidths=[5.5*cm, 5.5*cm, 5.5*cm])
    lembar_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), MUTED),
        ("TEXTCOLOR",  (0,0), (-1,0), colors.white),
        ("FONTNAME",   (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTNAME",   (0,1), (-1,1), "Helvetica-Bold"),
        ("FONTSIZE",   (0,0), (-1,-1), 9),
        ("FONTSIZE",   (0,1), (-1,1), 11),
        ("ALIGN",      (0,0), (-1,-1), "CENTER"),
        ("VALIGN",     (0,0), (-1,-1), "MIDDLE"),
        ("ROWHEIGHT",  (0,0), (-1,0), 16),
        ("ROWHEIGHT",  (0,1), (-1,1), 22),
        ("BACKGROUND", (0,1), (0,1), colors.HexColor("#F0FDF4")),
        ("TEXTCOLOR",  (0,1), (0,1), GREEN),
        ("BACKGROUND", (1,1), (1,1), colors.HexColor("#FEF2F2")),
        ("TEXTCOLOR",  (1,1), (1,1), RED),
        ("BACKGROUND", (2,1), (2,1), colors.HexColor("#FEF2F2")),
        ("TEXTCOLOR",  (2,1), (2,1), RED),
        ("GRID",       (0,0), (-1,-1), 0.3, colors.white),
    ]))
    story.append(lembar_tbl)
    story.append(Spacer(1, 6))

    # Ringkasan 3 kolom
    sum_data = [
        ["Pendapatan (cetak)", "Total Kerugian", "Saldo Bersih"],
        [f"Rp {total_biaya:,}", f"Rp {total_kerugian_rupiah:,}", f"Rp {saldo_bersih:,}"],
    ]
    sum_tbl = Table(sum_data, colWidths=[5.5*cm, 5.5*cm, 5.5*cm])
    sum_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), BLUE),
        ("TEXTCOLOR",  (0,0), (-1,0), colors.white),
        ("FONTNAME",   (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTNAME",   (0,1), (-1,1), "Helvetica-Bold"),
        ("FONTSIZE",   (0,0), (-1,-1), 9),
        ("FONTSIZE",   (0,1), (-1,1), 12),
        ("ALIGN",      (0,0), (-1,-1), "CENTER"),
        ("VALIGN",     (0,0), (-1,-1), "MIDDLE"),
        ("ROWHEIGHT",  (0,0), (-1,0), 18),
        ("ROWHEIGHT",  (0,1), (-1,1), 26),
        ("BACKGROUND", (0,1), (0,1), LBLUE),
        ("BACKGROUND", (1,1), (1,1), colors.HexColor("#FEF2F2")),
        ("TEXTCOLOR",  (1,1), (1,1), RED),
        ("BACKGROUND", (2,1), (2,1), colors.HexColor("#F0FDF4") if saldo_bersih >= 0 else colors.HexColor("#FEF2F2")),
        ("TEXTCOLOR",  (2,1), (2,1), saldo_color),
        ("GRID",       (0,0), (-1,-1), 0.3, colors.white),
    ]))
    story.append(sum_tbl)
    if total_kerugian_rupiah > 0:
        story.append(Spacer(1, 3))
        story.append(P(
            f"Kerugian kertas NG/STOP: {total_kerugian_lembar:,} lembar "
            f"(Rp {total_kerugian_rupiah:,}) — sudah dikurangkan dari Saldo Bersih.",
            size=8, color=RED, align="CENTER"))
    story.append(Spacer(1, 2))
    story.append(P("Saldo Bersih = Pendapatan (OK) − Total Kerugian NG/STOP",
                   size=7.5, color=MUTED, align="CENTER"))
    story.append(Spacer(1, 10))

    # Tabel detail cetak
    HDR   = ["Tanggal", "Jam", "Nama Job", "Pengguna", "Lembar", "Biaya", "Status"]
    COL_W = [2*cm, 1.4*cm, 5.5*cm, 2.8*cm, 1.5*cm, 2.5*cm, 1.5*cm]

    rows = [HDR]
    cmds = [
        ("BACKGROUND", (0,0), (-1,0), BLUE),
        ("TEXTCOLOR",  (0,0), (-1,0), colors.white),
        ("FONTNAME",   (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE",   (0,0), (-1,-1), 8),
        ("ALIGN",      (0,0), (-1,-1), "CENTER"),
        ("ALIGN",      (2,1), (3,-1), "LEFT"),
        ("VALIGN",     (0,0), (-1,-1), "MIDDLE"),
        ("ROWHEIGHT",  (0,0), (-1,-1), 16),
        ("GRID",       (0,0), (-1,-1), 0.25, colors.HexColor("#E2E8F0")),
    ]

    groups = _group_by_date(jobs)
    dr = 1
    for tgl, day_jobs in groups.items():
        day_lembar = 0; day_biaya = 0; first = True
        for j in day_jobs:
            biaya = j.total_sheets * price if j.status == "OK" else 0
            day_lembar += j.total_sheets if j.status == "OK" else 0
            day_biaya  += biaya
            is_fail = j.status != "OK"
            rows.append([tgl if first else "",
                         j.start_time.strftime("%H:%M") if j.start_time else "-",
                         (j.job_name or "-")[:35], j.username or "-",
                         str(j.total_sheets), f"Rp {biaya:,}" if biaya > 0 else "-",
                         j.status])
            if is_fail:
                cmds += [("TEXTCOLOR",  (0,dr),(-1,dr), RED),
                         ("BACKGROUND", (0,dr),(-1,dr), colors.HexColor("#FEF2F2"))]
            elif dr % 2 == 0:
                cmds.append(("BACKGROUND", (0,dr),(-1,dr), GRAY))
            cmds.append(("TEXTCOLOR", (6,dr),(6,dr), RED if is_fail else GREEN))
            first = False; dr += 1

        rows.append([f"Subtotal  {tgl}", "", "", "", str(day_lembar), f"Rp {day_biaya:,}", ""])
        cmds += [("BACKGROUND",(0,dr),(-1,dr), LBLUE),
                 ("TEXTCOLOR", (0,dr),(-1,dr), DBLUE),
                 ("FONTNAME",  (0,dr),(-1,dr), "Helvetica-Bold"),
                 ("SPAN",      (0,dr),(3,dr))]
        dr += 1

    rows.append(["TOTAL PENDAPATAN", "", "", "", str(total_lembar), f"Rp {total_biaya:,}", ""])
    cmds += [("BACKGROUND",(0,dr),(-1,dr), DBLUE),
             ("TEXTCOLOR", (0,dr),(-1,dr), colors.white),
             ("FONTNAME",  (0,dr),(-1,dr), "Helvetica-Bold"),
             ("FONTSIZE",  (0,dr),(-1,dr), 9),
             ("SPAN",      (0,dr),(3,dr)),
             ("ROWHEIGHT", (0,dr),(-1,dr), 20)]

    tbl = Table(rows, colWidths=COL_W, repeatRows=1)
    tbl.setStyle(TableStyle(cmds))
    story.append(tbl)
    story.append(Spacer(1, 14))

    # Saldo bersih
    saldo_data = [["SALDO BERSIH (Pendapatan − Total Kerugian NG/STOP)", f"Rp {saldo_bersih:,}"]]
    s_tbl = Table(saldo_data, colWidths=[12*cm, 4.7*cm])
    s_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0,0),(-1,0), saldo_color),
        ("TEXTCOLOR",  (0,0),(-1,0), colors.white),
        ("FONTNAME",   (0,0),(-1,0), "Helvetica-Bold"),
        ("FONTSIZE",   (0,0),(-1,0), 11),
        ("ALIGN",      (0,0),(0,0), "LEFT"),
        ("ALIGN",      (1,0),(1,0), "RIGHT"),
        ("VALIGN",     (0,0),(-1,0), "MIDDLE"),
        ("ROWHEIGHT",  (0,0),(-1,0), 24),
    ]))
    story.append(s_tbl)

    doc.build(story)
    buffer.seek(0)
    response = make_response(buffer.read())
    response.headers["Content-Type"]        = "application/pdf"
    response.headers["Content-Disposition"] = f"attachment; filename={filename}"
    return response