from datetime import datetime
from models import db


class Device(db.Model):
    __tablename__ = "devices"

    id         = db.Column(db.Integer, primary_key=True)
    ip_address = db.Column(db.Text, unique=True, nullable=False)
    model      = db.Column(db.Text)
    hostname   = db.Column(db.Text)
    location   = db.Column(db.Text)
    is_active  = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False)

    print_jobs     = db.relationship("PrintJob",     backref="device", lazy=True)
    snmp_snapshots = db.relationship("SnmpSnapshot", backref="device", lazy=True)

    def to_dict(self):
        return {
            "id":         self.id,
            "ip_address": self.ip_address,
            "model":      self.model,
            "hostname":   self.hostname,
            "location":   self.location,
            "is_active":  self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
