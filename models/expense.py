from datetime import datetime
from models import db


class Expense(db.Model):
    __tablename__ = "expenses"

    id          = db.Column(db.Integer, primary_key=True)
    tanggal     = db.Column(db.Date, nullable=False, default=datetime.now().date)
    keterangan  = db.Column(db.Text, nullable=False)
    jumlah      = db.Column(db.Integer, nullable=False)  # dalam rupiah
    catatan     = db.Column(db.Text, nullable=True)
    created_at  = db.Column(db.DateTime, default=datetime.now, nullable=False)

    def to_dict(self):
        return {
            "id":         self.id,
            "tanggal":    self.tanggal.strftime("%Y-%m-%d") if self.tanggal else None,
            "keterangan": self.keterangan,
            "jumlah":     self.jumlah,
            "catatan":    self.catatan or "",
        }
