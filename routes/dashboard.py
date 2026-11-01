from flask import Blueprint, render_template, request, redirect, url_for
from models.device import Device
from models.print_job import PrintJob
from models.snmp_snapshot import SnmpSnapshot
from models.setting import Setting
from datetime import datetime, timedelta
import calendar

bp = Blueprint("dashboard", __name__)

PERIOD_LABELS = {
    "hari":   "Hari ini",
    "minggu": "Minggu ini",
    "bulan":  "Bulan ini",
    "tahun":  "Tahun ini",
    "semua":  "Semua data",
}


def _date_range(period: str):
    now   = datetime.now()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "minggu":
        start = today - timedelta(days=today.weekday())
    elif period == "bulan":
        start = today.replace(day=1)
    elif period == "tahun":
        start = today.replace(month=1, day=1)
    elif period == "semua":
        return None, now   # None = tidak ada batas bawah
    else:
        start = today
    return start, now


def _chart_data_semua(device_id: int) -> dict:
    """Grafik per bulan untuk mode Semua data."""
    jobs = PrintJob.query.filter_by(device_id=device_id).all()
    if not jobs:
        return {"labels": [], "data": [], "today_idx": -1, "yest_idx": -1}

    # Tentukan rentang bulan
    dates      = [j.start_time for j in jobs if j.start_time]
    min_date   = min(dates)
    max_date   = max(dates)

    # Bangun label bulan
    bulan_id   = ["Jan","Feb","Mar","Apr","Mei","Jun",
                  "Jul","Agu","Sep","Okt","Nov","Des"]
    labels, data = [], []
    cur = min_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end = max_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    while cur <= end:
        next_cur = (cur.replace(day=28) + timedelta(days=4)).replace(day=1)
        count    = sum(j.total_sheets for j in jobs
                       if j.start_time and cur <= j.start_time < next_cur)
        labels.append(f"{bulan_id[cur.month-1]} {str(cur.year)[2:]}")
        data.append(count)
        cur = next_cur

    return {
        "labels":    labels,
        "data":      data,
        "today_idx": len(labels) - 1,
        "yest_idx":  max(0, len(labels) - 2),
        "min_date":  min_date.strftime("%B %Y"),
        "max_date":  max_date.strftime("%B %Y"),
    }


def _chart_data_tahun(device_id: int, start: datetime, now: datetime) -> dict:
    """Grafik per bulan (Jan–Des) untuk mode Tahun ini."""
    jobs = (PrintJob.query
            .filter(PrintJob.device_id == device_id,
                    PrintJob.start_time >= start,
                    PrintJob.start_time <= now)
            .all())

    bulan_id = ["Jan","Feb","Mar","Apr","Mei","Jun",
                "Jul","Agu","Sep","Okt","Nov","Des"]
    labels, data = [], []
    cur = start
    for m in range(1, 13):
        cur = start.replace(month=m)
        next_cur = (cur.replace(day=28) + timedelta(days=4)).replace(day=1)
        count = sum(j.total_sheets for j in jobs
                    if j.start_time and cur <= j.start_time < next_cur)
        labels.append(bulan_id[m - 1])
        data.append(count)

    today_idx = now.month - 1
    return {"labels": labels, "data": data,
            "today_idx": today_idx, "yest_idx": max(0, today_idx - 1)}


def _chart_data_period(device_id: int, period: str,
                        start: datetime, now: datetime) -> dict:
    """Grafik untuk periode hari/minggu/bulan."""
    cutoff = start - timedelta(days=1)
    jobs   = (PrintJob.query
               .filter(PrintJob.device_id == device_id,
                       PrintJob.start_time >= cutoff)
               .all())

    if period == "hari":
        yesterday = start - timedelta(days=1)
        s_today   = sum(j.total_sheets for j in jobs if j.start_time >= start)
        s_yest    = sum(j.total_sheets for j in jobs
                        if yesterday <= j.start_time < start)
        return {"labels": ["Kemarin", "Hari ini"],
                "data":   [s_yest, s_today],
                "today_idx": 1, "yest_idx": 0}

    elif period == "minggu":
        day_names = ["Sen","Sel","Rab","Kam","Jum","Sab","Min"]
        today_idx = now.weekday()
        labels, data = [], []
        for i in range(7):
            d     = start + timedelta(days=i)
            count = sum(j.total_sheets for j in jobs
                        if j.start_time.date() == d.date())
            labels.append(day_names[i])
            data.append(count)
        return {"labels": labels, "data": data,
                "today_idx": today_idx, "yest_idx": max(0, today_idx - 1)}

    else:  # bulan
        days = calendar.monthrange(start.year, start.month)[1]
        today_idx = now.day - 1
        labels, data = [], []
        for d in range(1, days + 1):
            dt    = start.replace(day=d)
            count = sum(j.total_sheets for j in jobs
                        if j.start_time.date() == dt.date())
            labels.append(str(d))
            data.append(count)
        return {"labels": labels, "data": data,
                "today_idx": today_idx, "yest_idx": max(0, today_idx - 1)}


@bp.route("/dashboard")
def index():
    device = Device.query.filter_by(is_active=True).first()
    if not device:
        return redirect(url_for("snmp.setup"))

    period     = request.args.get("period", "hari")
    start, end = _date_range(period)

    # ── Ambil jobs sesuai periode ─────────────────────────────────────────
    if period == "semua":
        jobs = PrintJob.query.filter_by(device_id=device.id).all()
    else:
        jobs = (PrintJob.query
                .filter(PrintJob.device_id == device.id,
                        PrintJob.start_time >= start,
                        PrintJob.start_time <= end)
                .all())

    # ── Statistik ─────────────────────────────────────────────────────────
    total_sheets = sum(j.total_sheets for j in jobs)
    total_jobs   = len(jobs)
    failed_jobs  = sum(1 for j in jobs if j.status != "OK")
    has_data     = total_jobs > 0

    # Diff dengan periode sebelumnya (hanya untuk hari/minggu/bulan)
    diff_sheets      = 0
    sheets_yesterday = 0
    if period not in ("semua", "tahun") and start:
        yesterday      = start - timedelta(days=1)
        jobs_yesterday = (PrintJob.query
                          .filter(PrintJob.device_id == device.id,
                                  PrintJob.start_time >= yesterday,
                                  PrintJob.start_time < start)
                          .all())
        sheets_yesterday = sum(j.total_sheets for j in jobs_yesterday)
        diff_sheets      = total_sheets - sheets_yesterday

    # ── Grafik ────────────────────────────────────────────────────────────
    if period == "semua":
        chart_data = _chart_data_semua(device.id)
    elif period == "tahun":
        chart_data = _chart_data_tahun(device.id, start, end)
    else:
        chart_data = _chart_data_period(device.id, period, start, end)

    has_chart_data = any(v > 0 for v in chart_data["data"])

    # Info rentang data untuk mode semua
    semua_info = None
    if period == "semua" and has_data:
        semua_info = {
            "min": chart_data.get("min_date", ""),
            "max": chart_data.get("max_date", ""),
        }

    # ── 5 job terbaru ─────────────────────────────────────────────────────
    latest_jobs = (PrintJob.query
                   .filter_by(device_id=device.id)
                   .order_by(PrintJob.start_time.desc())
                   .limit(5).all())

    # ── SNMP (opsional) ───────────────────────────────────────────────────
    snap = (SnmpSnapshot.query
            .filter_by(device_id=device.id)
            .order_by(SnmpSnapshot.polled_at.desc())
            .first())

    price          = int(Setting.get("price_per_sheet", "200"))
    estimated_cost = total_sheets * price

    from services.notif_service import check_notifications
    notifs = check_notifications(device.id)

    # Total semua data di DB (untuk bedakan 'belum ada data' vs 'tidak ada di periode ini')
    total_all_time = PrintJob.query.filter_by(device_id=device.id).count()

    return render_template("dashboard.html",
        device=device,
        period=period,
        period_label=PERIOD_LABELS.get(period, "Hari ini"),
        total_sheets=total_sheets,
        total_jobs=total_jobs,
        failed_jobs=failed_jobs,
        sheets_yesterday=sheets_yesterday,
        diff_sheets=diff_sheets,
        latest_jobs=latest_jobs,
        chart_data=chart_data,
        has_chart_data=has_chart_data,
        has_data=has_data,
        semua_info=semua_info,
        snap=snap,
        price=price,
        estimated_cost=estimated_cost,
        notifs=notifs,
        total_all_time=total_all_time,
    )


@bp.route("/dashboard/export-pdf")
def export_pdf():
    from services.report_service import export_pdf_response
    from datetime import datetime as dt

    device = Device.query.filter_by(is_active=True).first()
    if not device:
        return redirect(url_for("snmp.setup"))

    period     = request.args.get("period", "hari")
    start, end = _date_range(period)

    if period == "semua":
        jobs = (PrintJob.query
                .filter_by(device_id=device.id)
                .order_by(PrintJob.start_time.desc())
                .all())
    else:
        jobs = (PrintJob.query
                .filter(PrintJob.device_id == device.id,
                        PrintJob.start_time >= start,
                        PrintJob.start_time <= end)
                .order_by(PrintJob.start_time.desc())
                .all())

    price    = int(Setting.get("price_per_sheet", "200"))
    filename = f"laporan_{dt.now().strftime('%Y%m%d_%H%M')}.pdf"
    return export_pdf_response(
        jobs=jobs, device=device,
        period_label=PERIOD_LABELS.get(period, period),
        price=price, filename=filename,
    )