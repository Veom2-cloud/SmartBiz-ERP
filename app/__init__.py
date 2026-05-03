from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate

db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = "auth.login"


def create_app(test_config=None):
    app = Flask(__name__)

    app.config.from_object("config.Config")

    # Override config during tests
    if test_config:
        app.config.update(test_config)

    db.init_app(app)
    login_manager.init_app(app)
    Migrate(app, db)

    from app.auth.routes import auth_bp
    from app.company.routes import company_bp, sales_bp, purchase_bp, backup_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(company_bp)
    app.register_blueprint(sales_bp)
    app.register_blueprint(purchase_bp)
    app.register_blueprint(backup_bp)

    with app.app_context():
        db.create_all()

    return app