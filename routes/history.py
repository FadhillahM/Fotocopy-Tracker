from flask import Blueprint, render_template, request, jsonify
from models.print_job import PrintJob
from models.device import Device
from models import db
from datetime import datetime

bp = Blueprint("history", __name__)


@bp.route("/history")
def index():
    device = Device.query.filter_by(is_active=True).first()
    if not device:
        from flask import redirect, url_for
        return redirect(url_for("snmp.setup"))

    q        = request.args.get("q", "")
    status   = request.args.get("status", "")
    job_type = request.args.get("job_type", "")
    page     = int(request.args.get("page", 1))
    per_page = 15

    query = PrintJob.query.filter_by(device_id=device.id)
    if q:
        query = query.filter(
            (PrintJob.job_name.ilike(f"%{q}%")) |
            (PrintJob.username.ilike(f"%{q}%"))
        )
    if status:
        query = query.filter_by(status=status)
    if job_type:
        query = query.filter_by(job_type=job_type)

    total   = query.count()
    jobs    = (query.order_by(PrintJob.start_time.desc())
               .offset((page - 1) * per_page)
               .limit(per_page).all())

    return render_template("history.html",
        device=device, jobs=jobs,
        q=q, status=status, job_type=job_type,
        page=page, total=total, per_page=per_page,
        pages=max(1, -(-total // per_page)),
    )


@bp.route("/api/history/add", methods=["POST"])
def api_add():
    """Tambah job cetak secara manual."""
    device = Device.query.filter_by(is_active=True).first()
    if not device:
        return jsonify({"ok": False, "error": "Tidak ada device aktif"}), 400

    data = request.json
    try:
        start = datetime.strptime(data["start_time"], "%Y-%m-%dT%H:%M")
    except (KeyError, ValueError):
        return jsonify({"ok": False, "error": "Format waktu tidak valid"}), 400

    sheets = int(data.get("sheets", 0))
    copies = int(data.get("copies", 1))

    job_type = data.get("job_type", "print")
    if job_type not in ("print", "copy"):
        job_type = "print"

    job = PrintJob(
        device_id    = device.id,
        job_type     = job_type,
        job_name     = (data.get("job_name") or None) if job_type == "print" else None,
        username     = data.get("username", ""),
        start_time   = start,
        sheets       = sheets,
        copies       = copies,
        total_sheets = sheets * copies,
        paper_size   = data.get("paper_size", "A4"),
        status       = data.get("status", "OK"),
        source       = "manual",
    )
    db.session.add(job)
    db.session.commit()
    return jsonify({"ok": True, "job": job.to_dict()})


@bp.route("/api/history/export")
def api_export():
    """Export riwayat ke Excel, mengikuti filter (q/status/job_type) yang aktif."""
    from services.report_service import export_excel
    device = Device.query.filter_by(is_active=True).first()
    if not device:
        return jsonify({"ok": False}), 400

    q        = request.args.get("q", "")
    status   = request.args.get("status", "")
    job_type = request.args.get("job_type", "")

    query = PrintJob.query.filter_by(device_id=device.id)
    if q:
        query = query.filter(
            (PrintJob.job_name.ilike(f"%{q}%")) |
            (PrintJob.username.ilike(f"%{q}%"))
        )
    if status:
        query = query.filter_by(status=status)
    if job_type:
        query = query.filter_by(job_type=job_type)

    jobs = query.order_by(PrintJob.start_time.desc()).all()
    return export_excel(jobs, device)