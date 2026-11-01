from datetime import datetime
from models import db


class Setting(db.Model):
    __tablename__ = "settings"

    key        = db.Column(db.Text, primary_key=True)
    value      = db.Column(db.Text, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)

    @staticmethod
    def get(key: str, default=None):
        s = Setting.query.get(key)
        return s.value if s else default

    @staticmethod
    def set(key: str, value: str):
        s = Setting.query.get(key)
        if s:
            s.value = value
            s.updated_at = datetime.now()
        else:
            db.session.add(Setting(key=key, value=str(value)))
        db.session.commit()
