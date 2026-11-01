from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

_scheduler = BackgroundScheduler()


def start_scheduler(app):
    with app.app_context():
        from models.setting import Setting
        interval = int(Setting.get("polling_interval", "60"))

    _scheduler.add_job(
        func=lambda: _poll(app),
        trigger=IntervalTrigger(seconds=interval),
        id="polling_job",
        replace_existing=True,
    )
    if not _scheduler.running:
        _scheduler.start()
        print(f"[scheduler] Polling dimulai setiap {interval} detik")


def _poll(app):
    with app.app_context():
        from models.device import Device
        from models.snmp_snapshot import SnmpSnapshot
        from models.print_job import PrintJob
        from models import db
        from services.snmp_service import poll_snmp, _is_valid_ip
        from services.csv_service import fetch_copy_history, fetch_print_history, is_duplicate
        from datetime import datetime, timedelta
        from sqlalchemy import text
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert

        devices = Device.query.filter_by(is_active=True).all()
        if not devices:
            return

        for device in devices:
            ip = device.ip_address

            if not _is_valid_ip(ip):
                continue

            # 1. Poll SNMP
            try:
                snap = poll_snmp(ip)
                db.session.add(SnmpSnapshot(device_id=device.id, **snap))
            except Exception as e:
                print(f"[scheduler] SNMP gagal {ip}: {e}")
                db.session.add(SnmpSnapshot(
                    device_id=device.id,
                    is_online=False,
                    polled_at=datetime.now(),
                ))

            # 2. Scraping: Copy Job + Print Job
            #
            # PENTING: jangan batasi query pengecekan duplikat dengan cutoff
            # tanggal pendek (dulu 30 hari). Buffer log di mesin Canon bisa
            # saja masih menampilkan job lama (>30 hari), dan kalau job itu
            # sudah "lewat" dari jendela cutoff di query existing, job yang
            # sama akan dianggap "baru" lagi di setiap siklus polling ->
            # numpuk terus setiap 60 detik. Cek ke SEMUA histori device ini.
            existing = [j.to_dict() for j in PrintJob.query.filter(
                PrintJob.device_id == device.id,
            ).all()]

            new_count = 0
            for fetch_fn in [fetch_copy_history, fetch_print_history]:
                try:
                    jobs = fetch_fn(ip)
                    for job in jobs:
                        # is_duplicate() dipakai cuma sebagai filter cepat di
                        # sisi Python supaya tidak bolak-balik ke database.
                        # Yang benar-benar menentukan aman/tidaknya adalah
                        # index UNIQUE di database (lihat models/__init__.py)
                        # lewat ON CONFLICT DO NOTHING di bawah ini -- jadi
                        # walau ada kasus is_duplicate() meleset, baris
                        # dobel tetap TIDAK akan pernah tersimpan.
                        if is_duplicate(job, existing):
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
                except Exception as e:
                    print(f"[scheduler] {fetch_fn.__name__} gagal untuk {ip}: {e}")

            if new_count:
                print(f"[scheduler] {new_count} job baru dari {ip}")

            # 3. Hapus snapshot lama >7 hari
            old_cutoff = datetime.now() - timedelta(days=7)
            SnmpSnapshot.query.filter(
                SnmpSnapshot.device_id == device.id,
                SnmpSnapshot.polled_at < old_cutoff,
            ).delete()

        db.session.commit()