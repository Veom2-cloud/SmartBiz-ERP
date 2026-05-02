from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager

db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = "auth.login"

def create_app():
    app = Flask(__name__)
    app.config.from_object('config.Config')
    
    db.init_app(app)
    login_manager.init_app(app)
    
    # Import and register blueprints
    from app.auth.routes import auth_bp
    from app.company.routes import company_bp
    
    app.register_blueprint(auth_bp)
    app.register_blueprint(company_bp)
    
    with app.app_context():
        db.create_all()
    
    return app
