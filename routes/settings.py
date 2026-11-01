from flask import Blueprint, render_template, request, jsonify
from models.device import Device
from models.setting import Setting
from models.print_job import PrintJob
from models.snmp_snapshot import SnmpSnapshot
from models import db
from services.snmp_service import scan_device

bp = Blueprint("settings", __name__)


@bp.route("/settings")
def index():
    device = Device.query.filter_by(is_active=True).first()
    return render_template("settings.html",
        device=device,
        price=Setting.get("price_per_sheet", "200"),
        notif_paper=Setting.get("notif_paper_threshold", "400"),
        notif_toner=Setting.get("notif_toner_threshold", "20"),
    )


@bp.route("/api/settings/save", methods=["POST"])
def api_save():
    data = request.json
    allowed = ["price_per_sheet", "notif_paper_threshold", "notif_toner_threshold"]
    for key in allowed:
        if key in data:
            Setting.set(key, str(data[key]))
    return jsonify({"ok": True})


@bp.route("/api/settings/change-ip", methods=["POST"])
def api_change_ip():
    """Scan IP baru dan ganti device aktif jika ditemukan."""
    new_ip = request.json.get("ip", "").strip()
    if not new_ip:
        return jsonify({"ok": False, "error": "IP tidak boleh kosong"}), 400

    info = scan_device(new_ip)
    if not info:
        return jsonify({"ok": False, "error": f"{new_ip} tidak merespons SNMP"})

    # Update IP device aktif
    device = Device.query.filter_by(is_active=True).first()
    if device:
        device.ip_address = new_ip
        device.model      = info.get("model", device.model)
        device.hostname   = info.get("hostname", device.hostname)
        device.location   = info.get("location", device.location)
        db.session.commit()

    return jsonify({"ok": True, "device": info})


@bp.route("/api/settings/delete", methods=["POST"])
def api_delete():
    """Hapus data sesuai pilihan pengguna."""
    data          = request.json
    del_history   = data.get("history", False)
    del_device    = data.get("device", False)

    if del_history:
        PrintJob.query.delete()
        SnmpSnapshot.query.delete()

    if del_device:
        Device.query.delete()

    db.session.commit()
    return jsonify({"ok": True})
