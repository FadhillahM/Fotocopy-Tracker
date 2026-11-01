from flask import Blueprint, render_template, request, jsonify, redirect, url_for
from models.device import Device
from models.snmp_snapshot import SnmpSnapshot
from models import db
from services.snmp_service import scan_device
from datetime import datetime

bp = Blueprint("snmp", __name__)


@bp.route("/setup")
def setup():
    return render_template("setup.html")


@bp.route("/api/scan", methods=["POST"])
def api_scan():
    ip = (request.json or {}).get("ip", "").strip()
    if not ip:
        return jsonify({"ok": False, "error": "IP tidak boleh kosong"}), 400
    info = scan_device(ip)
    if info:
        return jsonify({"ok": True, "device": info})
    return jsonify({"ok": False, "error": f"{ip} tidak merespons SNMP"})


@bp.route("/api/scan-network", methods=["POST"])
def api_scan_network():
    """
    Scan seluruh subnet secara paralel.
    Body: { "subnet": "192.168.100" }  atau  { "subnet": "192.168.100.5" }
    Bisa juga tanpa body – akan pakai subnet dari IP device tersimpan.
    """
    from services.snmp_service import scan_network

    data   = request.json or {}
    subnet = data.get("subnet", "").strip()

    # Jika tidak dikirim, pakai subnet device yang tersimpan
    if not subnet:
        device = Device.query.filter_by(is_active=True).first()
        if device and device.ip_address:
            parts  = device.ip_address.split(".")
            subnet = ".".join(parts[:3]) if len(parts) == 4 else ""

    if not subnet:
        return jsonify({"ok": False, "error": "Subnet tidak diketahui. Kirim { subnet: '192.168.x.x' }"}), 400

    found = scan_network(subnet)
    return jsonify({"ok": True, "subnet": subnet, "devices": found, "count": len(found)})


@bp.route("/api/device/save", methods=["POST"])
def api_save_device():
    data = request.json or {}
    ip   = data.get("ip_address", "").strip()
    if not ip:
        return jsonify({"ok": False, "error": "IP diperlukan"}), 400

    Device.query.update({"is_active": False})

    device = Device.query.filter_by(ip_address=ip).first()
    if device:
        device.is_active = True
        device.model     = data.get("model")
        device.hostname  = data.get("hostname")
        device.location  = data.get("location")
    else:
        device = Device(
            ip_address=ip,
            model=data.get("model"),
            hostname=data.get("hostname"),
            location=data.get("location"),
            is_active=True,
        )
        db.session.add(device)
    db.session.commit()
    return jsonify({"ok": True, "device_id": device.id})


@bp.route("/api/import-csv", methods=["POST"])
def api_import_csv():
    """Import file CSV riwayat cetak dari upload."""
    from services.csv_service import parse_csv_content, is_duplicate
    from models.print_job import PrintJob
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert
    from sqlalchemy import text

    file = request.files.get("file")
    if not file:
        return jsonify({"ok": False, "error": "File tidak ditemukan"}), 400

    name = request.form.get("name", "Mesin CSV").strip() or "Mesin CSV"
    ip   = request.form.get("ip",   "0.0.0.0").strip()  or "0.0.0.0"

    try:
        content = file.read().decode("utf-8", errors="replace")
    except Exception as e:
        return jsonify({"ok": False, "error": f"Gagal membaca file: {e}"}), 400

    if not content.strip():
        return jsonify({"ok": False, "error": "File kosong"}), 400

    # Pastikan ada device aktif — buat jika belum ada
    device = Device.query.filter_by(is_active=True).first()
    if not device:
        # Cek apakah IP ini sudah pernah tersimpan
        device = Device.query.filter_by(ip_address=ip).first()
        if device:
            device.is_active = True
        else:
            device = Device(
                ip_address=ip,
                model=name,
                hostname=name,
                location=None,
                is_active=True,
            )
            db.session.add(device)
        db.session.flush()  # Dapatkan ID tanpa commit dulu

    # Parse CSV
    jobs = parse_csv_content(content)
    if not jobs:
        db.session.rollback()
        return jsonify({"ok": False, "error": "Tidak ada data yang bisa dibaca dari CSV. Pastikan format file benar."}), 400

    # Cek duplikat berdasarkan data yang sudah ada
    from datetime import timedelta
    cutoff   = datetime.now() - timedelta(days=365 * 5)  # 5 tahun ke belakang
    existing = [j.to_dict() for j in
                PrintJob.query.filter(
                    PrintJob.device_id == device.id,
                    PrintJob.start_time >= cutoff,
                ).all()]

    new_count  = 0
    skip_count = 0
    for job in jobs:
        if is_duplicate(job, existing):
            skip_count += 1
            continue
        stmt = sqlite_insert(PrintJob).values(
            device_id=device.id, source="auto", **job
        ).on_conflict_do_nothing(
            index_elements=["device_id", "job_number", "job_type", "start_time"],
            index_where=text("source = 'auto' AND job_number IS NOT NULL"),
        )
        result = db.session.execute(stmt)
        if result.rowcount:
            new_count += 1
        else:
            skip_count += 1

    db.session.commit()
    print(f"[import-csv] {new_count} job baru, {skip_count} duplikat dilewati untuk device {device.id}")
    return jsonify({
        "ok":      True,
        "imported": new_count,
        "skipped":  skip_count,
        "device_id": device.id,
    })


@bp.route("/snmp")
def index():
    device = Device.query.filter_by(is_active=True).first()
    if not device:
        return render_template("setup.html")
    snap = (SnmpSnapshot.query
            .filter_by(device_id=device.id)
            .order_by(SnmpSnapshot.polled_at.desc())
            .first())
    logs = (SnmpSnapshot.query
            .filter_by(device_id=device.id)
            .order_by(SnmpSnapshot.polled_at.desc())
            .limit(20).all())
    return render_template("snmp.html", device=device, snap=snap, logs=logs)


@bp.route("/api/snmp/latest")
def api_snmp_latest():
    device = Device.query.filter_by(is_active=True).first()
    if not device:
        return jsonify({"ok": False}), 404
    snap = (SnmpSnapshot.query
            .filter_by(device_id=device.id)
            .order_by(SnmpSnapshot.polled_at.desc())
            .first())
    return jsonify({"ok": True, "snap": snap.to_dict() if snap else None})


@bp.route("/api/scan-ulang", methods=["POST"])
def api_scan_ulang():
    device = Device.query.filter_by(is_active=True).first()
    if not device:
        return jsonify({"ok": False, "error": "Tidak ada device tersimpan"})
    info = scan_device(device.ip_address)
    if info:
        return jsonify({"ok": True, "ip": device.ip_address, "model": info.get("model")})
    return jsonify({"ok": False, "error": f"{device.ip_address} tidak merespons SNMP"})
