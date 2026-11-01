from datetime import datetime
from models import db


class PrintJob(db.Model):
    __tablename__ = "print_jobs"

    id           = db.Column(db.Integer, primary_key=True)
    device_id    = db.Column(db.Integer, db.ForeignKey("devices.id"), nullable=False)
    job_number   = db.Column(db.Integer)
    job_type     = db.Column(db.Text, default="print", nullable=False)  # "print" | "copy"
    job_name     = db.Column(db.Text)
    username     = db.Column(db.Text)
    start_time   = db.Column(db.DateTime, nullable=False)
    end_time     = db.Column(db.DateTime)
    sheets       = db.Column(db.Integer, default=0, nullable=False)
    copies       = db.Column(db.Integer, default=1)
    total_sheets = db.Column(db.Integer, default=0, nullable=False)
    paper_size   = db.Column(db.Text, default="A4")
    status       = db.Column(db.Text, default="OK", nullable=False)
    source       = db.Column(db.Text, default="auto", nullable=False)  # "auto" | "manual"
    created_at   = db.Column(db.DateTime, default=datetime.now, nullable=False)

    def to_dict(self):
        return {
            "id":           self.id,
            "device_id":    self.device_id,
            "job_number":   self.job_number,
            "job_type":     self.job_type,
            "job_name":     self.job_name,
            "username":     self.username,
            "start_time":   self.start_time.strftime("%d/%m/%Y %H:%M") if self.start_time else None,
            "end_time":     self.end_time.strftime("%d/%m/%Y %H:%M") if self.end_time else None,
            "sheets":       self.sheets,
            "copies":       self.copies,
            "total_sheets": self.total_sheets,
            "paper_size":   self.paper_size,
            "status":       self.status,
            "source":       self.source,
        }
