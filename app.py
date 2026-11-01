from flask import Flask, redirect, url_for
from config import Config
from models import init_db, db
from models.device import Device


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Init database
    init_db(app)

    # Register routes (blueprint)
    from routes.dashboard import bp as dashboard_bp
    from routes.history   import bp as history_bp
    from routes.snmp      import bp as snmp_bp
    from routes.settings  import bp as settings_bp
    from routes.laporan    import bp as laporan_bp

    app.register_blueprint(dashboard_bp)
    app.register_blueprint(history_bp)
    app.register_blueprint(snmp_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(laporan_bp)

    # Halaman root: cek apakah sudah ada device tersimpan
    @app.route("/")
    def index():
        device = Device.query.filter_by(is_active=True).first()
        if device:
            return redirect(url_for("dashboard.index"))
        return redirect(url_for("snmp.setup"))

    # Start scheduler polling di background
    from services.scheduler import start_scheduler
    start_scheduler(app)

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(host=Config.HOST, port=Config.PORT, debug=Config.DEBUG)
