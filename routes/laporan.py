from flask import Blueprint, jsonify, request, redirect, url_for
from models.device import Device
from models.print_job import PrintJob
from models.setting import Setting
from models.expense import Expense
from models import db
from datetime import datetime, date

bp = Blueprint("laporan", __name__)


def _parse_date(s: str):
    try:
        return datetime.strptime(s, "%Y-%m-%d")
    except (ValueError, TypeError):
        return None


def _parse_date_only(s: str):
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _get_jobs(device_id, dari, sampai):
    dt_dari   = _parse_date(dari)   or datetime(2000, 1, 1)
    dt_sampai = (_parse_date(sampai) or datetime.now()).replace(
                    hour=23, minute=59, second=59)
    jobs = (PrintJob.query
            .filter(PrintJob.device_id == device_id,
                    PrintJob.start_time >= dt_dari,
                    PrintJob.start_time <= dt_sampai)
            .order_by(PrintJob.start_time.asc())
            .all())
    return jobs, dt_dari, dt_sampai


def _get_expenses(dari, sampai):
    d_dari   = _parse_date_only(dari)   or date(2000, 1, 1)
    d_sampai = _parse_date_only(sampai) or date.today()
    return (Expense.query
            .filter(Expense.tanggal >= d_dari,
                    Expense.tanggal <= d_sampai)
            .order_by(Expense.tanggal.asc(), Expense.id.asc())
            .all())


@bp.route("/api/laporan/tahun-list")
def api_laporan_tahun_list():
    """Kembalikan daftar tahun yang punya data print job, untuk dropdown filter tahun."""
    device = Device.query.filter_by(is_active=True).first()
    if not device:
        return jsonify({"ok": False, "error": "Tidak ada device aktif"}), 400

    from sqlalchemy import extract, distinct
    rows = (db.session.query(distinct(extract("year", PrintJob.start_time)))
            .filter(PrintJob.device_id == device.id)
            .all())
    tahun_list = sorted({int(r[0]) for r in rows if r[0] is not None}, reverse=True)

    current_year = datetime.now().year
    if current_year not in tahun_list:
        tahun_list.insert(0, current_year)
        tahun_list.sort(reverse=True)

    return jsonify({"ok": True, "tahun_list": tahun_list})


@bp.route("/api/laporan")
def api_laporan():
    """Kembalikan data laporan kas dalam JSON, untuk modal di dashboard."""
    device = Device.query.filter_by(is_active=True).first()
    if not device:
        return jsonify({"ok": False, "error": "Tidak ada device aktif"}), 400

    dari   = request.args.get("dari")
    sampai = request.args.get("sampai")
    jobs, dt_dari, dt_sampai = _get_jobs(device.id, dari, sampai)

    price          = int(Setting.get("price_per_sheet", "200"))
    total_lembar   = sum(j.total_sheets for j in jobs if j.status == "OK")
    total_biaya    = total_lembar * price
    total_job      = len(jobs)
    total_gagal    = sum(1 for j in jobs if j.status != "OK")

    # Rincian lembar per status (untuk breakdown OK / NG / STOP)
    total_ok_lembar   = sum(j.total_sheets for j in jobs if j.status == "OK")
    total_ng_lembar   = sum(j.total_sheets for j in jobs if j.status == "NG")
    total_stop_lembar = sum(j.total_sheets for j in jobs if j.status == "STOP")

    # Kertas yang terpakai tapi gagal (NG/STOP) tetap dianggap kerugian
    # material -- ikut dikonversi ke rupiah dan memotong saldo bersih.
    total_kerugian_lembar = total_ng_lembar + total_stop_lembar
    total_kerugian_rupiah = total_kerugian_lembar * price

    # Pengeluaran
    expenses       = _get_expenses(dari, sampai)
    total_pengeluaran = sum(e.jumlah for e in expenses)

    saldo_bersih = total_biaya - total_kerugian_rupiah - total_pengeluaran

    from services.report_service import _group_by_date
    groups = _group_by_date(jobs)

    rows = []
    for tgl, day_jobs in groups.items():
        day_lembar = 0
        day_biaya  = 0
        for j in day_jobs:
            biaya = j.total_sheets * price if j.status == "OK" else 0
            if j.status == "OK":
                day_lembar += j.total_sheets
                day_biaya  += biaya
            rows.append({
                "tanggal": tgl,
                "jam":     j.start_time.strftime("%H:%M") if j.start_time else "-",
                "nama":    j.job_name or "-",
                "user":    j.username or "-",
                "lembar":  j.total_sheets,
                "biaya":   biaya,
                "status":  j.status,
                "source":  j.source,
                "is_first_of_day": j == day_jobs[0],
            })
        rows.append({
            "is_subtotal": True,
            "tanggal": tgl,
            "lembar":  day_lembar,
            "biaya":   day_biaya,
        })

    return jsonify({
        "ok": True,
        "period_label": f"{dt_dari.strftime('%d %b %Y')} – {dt_sampai.strftime('%d %b %Y')}",
        "price": price,
        "total_lembar": total_lembar,
        "total_biaya":  total_biaya,
        "total_job":    total_job,
        "total_gagal":  total_gagal,
        "total_ok_lembar":       total_ok_lembar,
        "total_ng_lembar":       total_ng_lembar,
        "total_stop_lembar":     total_stop_lembar,
        "total_kerugian_lembar": total_kerugian_lembar,
        "total_kerugian_rupiah": total_kerugian_rupiah,
        "total_pengeluaran": total_pengeluaran,
        "saldo_bersih":  saldo_bersih,
        "rows": rows,
        "expenses": [e.to_dict() for e in expenses],
        "has_data": len(jobs) > 0,
    })


# ── CRUD Pengeluaran ────────────────────────────────────────────────────────

@bp.route("/api/pengeluaran", methods=["GET"])
def api_pengeluaran_list():
    dari   = request.args.get("dari")
    sampai = request.args.get("sampai")
    items  = _get_expenses(dari, sampai)
    total  = sum(e.jumlah for e in items)
    return jsonify({"ok": True, "items": [e.to_dict() for e in items], "total": total})


@bp.route("/api/pengeluaran", methods=["POST"])
def api_pengeluaran_add():
    data       = request.json or {}
    keterangan = (data.get("keterangan") or "").strip()
    jumlah_raw = data.get("jumlah", 0)
    tanggal_s  = data.get("tanggal") or date.today().isoformat()

    if not keterangan:
        return jsonify({"ok": False, "error": "Keterangan tidak boleh kosong"}), 400
    try:
        jumlah = int(jumlah_raw)
        if jumlah <= 0:
            raise ValueError
    except (ValueError, TypeError):
        return jsonify({"ok": False, "error": "Jumlah harus angka positif"}), 400

    tgl = _parse_date_only(tanggal_s) or date.today()
    e   = Expense(tanggal=tgl, keterangan=keterangan, jumlah=jumlah,
                  catatan=data.get("catatan", ""))
    db.session.add(e)
    db.session.commit()
    return jsonify({"ok": True, "item": e.to_dict()})


@bp.route("/api/pengeluaran/<int:eid>", methods=["PUT"])
def api_pengeluaran_update(eid):
    e = Expense.query.get_or_404(eid)
    data       = request.json or {}
    keterangan = (data.get("keterangan") or "").strip()
    jumlah_raw = data.get("jumlah", 0)
    tanggal_s  = data.get("tanggal") or date.today().isoformat()

    if not keterangan:
        return jsonify({"ok": False, "error": "Keterangan tidak boleh kosong"}), 400
    try:
        jumlah = int(jumlah_raw)
        if jumlah <= 0:
            raise ValueError
    except (ValueError, TypeError):
        return jsonify({"ok": False, "error": "Jumlah harus angka positif"}), 400

    e.keterangan = keterangan
    e.jumlah     = jumlah
    e.catatan    = data.get("catatan", "")
    e.tanggal    = _parse_date_only(tanggal_s) or e.tanggal
    db.session.commit()
    return jsonify({"ok": True, "item": e.to_dict()})


@bp.route("/api/pengeluaran/<int:eid>", methods=["DELETE"])
def api_pengeluaran_delete(eid):
    e = Expense.query.get_or_404(eid)
    db.session.delete(e)
    db.session.commit()
    return jsonify({"ok": True})


@bp.route("/laporan/export-excel")
def export_excel():
    device = Device.query.filter_by(is_active=True).first()
    if not device:
        return redirect(url_for("snmp.setup"))

    dari   = request.args.get("dari")
    sampai = request.args.get("sampai")
    jobs, dt_dari, dt_sampai = _get_jobs(device.id, dari, sampai)

    price        = int(Setting.get("price_per_sheet", "200"))
    period_label = f"{dt_dari.strftime('%d %b %Y')} – {dt_sampai.strftime('%d %b %Y')}"
    expenses     = _get_expenses(dari, sampai)

    from services.report_service import export_excel_laporan
    return export_excel_laporan(jobs, device, period_label, price, expenses=expenses)


@bp.route("/laporan/export-pdf")
def export_pdf():
    device = Device.query.filter_by(is_active=True).first()
    if not device:
        return redirect(url_for("snmp.setup"))

    dari   = request.args.get("dari")
    sampai = request.args.get("sampai")
    jobs, dt_dari, dt_sampai = _get_jobs(device.id, dari, sampai)

    price        = int(Setting.get("price_per_sheet", "200"))
    period_label = f"{dt_dari.strftime('%d %b %Y')} – {dt_sampai.strftime('%d %b %Y')}"
    filename     = f"laporan_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
    expenses     = _get_expenses(dari, sampai)

    from services.report_service import export_pdf_response
    return export_pdf_response(jobs, device, period_label, price, filename,
                               expenses=expenses)