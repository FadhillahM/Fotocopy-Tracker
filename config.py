import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

class Config:
    SECRET_KEY = "fotocopy-tracker-secret-2026"
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{os.path.join(BASE_DIR, 'fotocopy.db')}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Interval polling SNMP & CSV (detik) — bisa diubah dari halaman pengaturan
    POLLING_INTERVAL = 60

    # Jalankan di semua interface agar bisa diakses dari laptop lain (presentasi)
    HOST = "0.0.0.0"
    PORT = 5000
    DEBUG = False
