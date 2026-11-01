from datetime import datetime
from models import db


class SnmpSnapshot(db.Model):
    __tablename__ = "snmp_snapshots"

    id                 = db.Column(db.Integer, primary_key=True)
    device_id          = db.Column(db.Integer, db.ForeignKey("devices.id"), nullable=False)
    polled_at          = db.Column(db.DateTime, default=datetime.now, nullable=False)
    is_online          = db.Column(db.Boolean, default=False, nullable=False)
    printer_status     = db.Column(db.Text)       # idle | printing | warmup | error
    toner_level        = db.Column(db.Integer)    # 0–100%
    waste_toner_level  = db.Column(db.Integer)    # 0–100%
    tray_bypass        = db.Column(db.Integer)
    tray_1             = db.Column(db.Integer)
    tray_2             = db.Column(db.Integer)
    tray_3             = db.Column(db.Integer)
    tray_4             = db.Column(db.Integer)
    counter_lifetime   = db.Column(db.Integer)
    uptime_seconds     = db.Column(db.Integer)

    def to_dict(self):
        return {
            "id":                self.id,
            "device_id":         self.device_id,
            "polled_at":         self.polled_at.isoformat() if self.polled_at else None,
            "is_online":         self.is_online,
            "printer_status":    self.printer_status,
            "toner_level":       self.toner_level,
            "waste_toner_level": self.waste_toner_level,
            "tray_bypass":       self.tray_bypass,
            "tray_1":            self.tray_1,
            "tray_2":            self.tray_2,
            "tray_3":            self.tray_3,
            "tray_4":            self.tray_4,
            "counter_lifetime":  self.counter_lifetime,
            "uptime_seconds":    self.uptime_seconds,
        }
