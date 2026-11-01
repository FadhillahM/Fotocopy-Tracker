from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


def init_db(app):
    """Inisialisasi database dan buat semua tabel jika belum ada."""
    db.init_app(app)
    with app.app_context():
        from models.device import Device
        from models.print_job import PrintJob
        from models.snmp_snapshot import SnmpSnapshot
        from models.setting import Setting
        from models.expense import Expense
        db.create_all()
        _migrate_schema()
        _seed_default_settings()


def _migrate_schema():
    """
    Migrasi ringan untuk kolom baru yang ditambahkan belakangan,
    supaya database lama (fotocopy.db yang sudah berisi data) tidak perlu dihapus.
    """
    from sqlalchemy import text

    with db.engine.connect() as conn:
        cols = [row[1] for row in conn.execute(text("PRAGMA table_info(print_jobs)"))]

        if "job_type" not in cols:
            print("[migrate] Menambahkan kolom job_type ke tabel print_jobs...")
            conn.execute(text(
                "ALTER TABLE print_jobs ADD COLUMN job_type TEXT NOT NULL DEFAULT 'print'"
            ))
            # Backfill terbaik-yang-bisa untuk data lama: job scraping copy
            # dulu selalu diberi nama "Local Copy" atau "Copy - <device>".
            conn.execute(text(
                "UPDATE print_jobs SET job_type = 'copy' "
                "WHERE job_name = 'Local Copy' OR job_name LIKE 'Copy - %' "
                "OR job_name LIKE 'Copy #%'"
            ))
            # Copy job tidak punya nama dokumen asli, kosongkan supaya
            # ditampilkan "-" di web (konsisten dengan job baru).
            conn.execute(text(
                "UPDATE print_jobs SET job_name = NULL WHERE job_type = 'copy'"
            ))
            conn.commit()
            print("[migrate] Kolom job_type ditambahkan & data lama ditandai.")

        # Kolom tray_3 sempat hilang dari model sehingga SnmpSnapshot(**snap)
        # SELALU gagal (TypeError) dan device selalu tersimpan is_online=False.
        snmp_cols = [row[1] for row in conn.execute(text("PRAGMA table_info(snmp_snapshots)"))]
        if "tray_3" not in snmp_cols:
            print("[migrate] Menambahkan kolom tray_3 ke tabel snmp_snapshots...")
            conn.execute(text("ALTER TABLE snmp_snapshots ADD COLUMN tray_3 INTEGER"))
            conn.commit()

        # ── Anti-duplikat permanen ──────────────────────────────────────────
        # Selalu dijalankan (bukan cuma sekali saat migrasi kolom) supaya
        # kalau ada duplikat numpuk lagi dari sumber manapun, otomatis
        # kebersihkan sendiri tiap kali aplikasi start. Hanya menyasar baris
        # source='auto' & job_number terisi, supaya entri input manual
        # (job_number kosong) tidak ikut kehapus.
        before = conn.execute(text("SELECT COUNT(*) FROM print_jobs")).scalar()
        conn.execute(text("""
            DELETE FROM print_jobs
            WHERE source = 'auto' AND job_number IS NOT NULL
            AND id NOT IN (
                SELECT MIN(id) FROM print_jobs
                WHERE source = 'auto' AND job_number IS NOT NULL
                GROUP BY device_id, job_number, job_type, start_time
            )
        """))
        conn.commit()
        after = conn.execute(text("SELECT COUNT(*) FROM print_jobs")).scalar()
        if before != after:
            print(f"[migrate] Bersih-bersih duplikat print_jobs: {before} -> {after} baris "
                  f"({before - after} duplikat dihapus).")

        # Pengaman utama: index UNIQUE di level database. Selama ini dedup
        # cuma dicek manual di kode Python (is_duplicate) yang ternyata masih
        # bisa meleset (mis. pembulatan waktu). Dengan index ini, SQLite
        # sendiri yang menolak baris duplikat -> job dobel jadi mustahil
        # tersimpan, apa pun bug di logika Python-nya.
        conn.execute(text("""
            CREATE UNIQUE INDEX IF NOT EXISTS ux_print_jobs_dedup
            ON print_jobs(device_id, job_number, job_type, start_time)
            WHERE source = 'auto' AND job_number IS NOT NULL
        """))
        conn.commit()


def _seed_default_settings():
    """Isi setting default jika belum ada."""
    from models.setting import Setting
    defaults = {
        "price_per_sheet":        "200",
        "notif_paper_threshold":  "400",
        "notif_toner_threshold":  "20",
        "polling_interval":       "60",
    }
    for key, value in defaults.items():
        if not Setting.query.get(key):
            db.session.add(Setting(key=key, value=value))
    db.session.commit()
