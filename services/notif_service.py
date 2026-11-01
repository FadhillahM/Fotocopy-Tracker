from models.setting import Setting
from models.snmp_snapshot import SnmpSnapshot
from models.print_job import PrintJob
from models.device import Device
from datetime import datetime, timedelta


def check_notifications(device_id: int) -> list[dict]:
    """
    Cek semua kondisi notifikasi.
    Kembalikan list notifikasi yang aktif (jika ada).
    Setiap item: {"type": str, "level": "warning"|"danger", "message": str}
    """
    notifs = []

    snap = (SnmpSnapshot.query
            .filter_by(device_id=device_id)
            .order_by(SnmpSnapshot.polled_at.desc())
            .first())

    if not snap or not snap.is_online:
        return notifs

    # 1. Cek toner
    toner_threshold = int(Setting.get("notif_toner_threshold", "20"))
    if snap.toner_level is not None and snap.toner_level <= toner_threshold:
        notifs.append({
            "type":    "toner",
            "level":   "danger" if snap.toner_level <= 10 else "warning",
            "message": f"Level toner tersisa {snap.toner_level}% — segera ganti atau isi toner.",
        })

    # 2. Cek kertas (berbasis pemakaian hari ini)
    paper_threshold = int(Setting.get("notif_paper_threshold", "400"))
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    used_today = (PrintJob.query
                  .filter(PrintJob.device_id == device_id,
                          PrintJob.start_time >= today,
                          PrintJob.status == "OK")
                  .with_entities(__import__("sqlalchemy").func.sum(PrintJob.total_sheets))
                  .scalar() or 0)

    if used_today >= paper_threshold:
        notifs.append({
            "type":    "paper",
            "level":   "warning",
            "message": f"Telah menggunakan {used_today} lembar hari ini — segera isi ulang kertas.",
        })

    # 3. Cek waste toner
    if snap.waste_toner_level is not None and snap.waste_toner_level >= 80:
        notifs.append({
            "type":    "waste",
            "level":   "warning",
            "message": f"Waste toner {snap.waste_toner_level}% — segera kosongkan.",
        })

    return notifs
