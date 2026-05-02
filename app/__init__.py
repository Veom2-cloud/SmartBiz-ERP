from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate 
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
    from app.company.routes import company_bp,sales_bp,purchase_bp
    
    app.register_blueprint(auth_bp)
    app.register_blueprint(company_bp)
    

    app.register_blueprint(sales_bp)
    app.register_blueprint(purchase_bp)
    
    
    
    from app.company.routes import backup_bp
    app.register_blueprint(backup_bp)
    
    migrate = Migrate(app, db)
    with app.app_context():
        db.create_all()
    
    return app


##http://127.0.0.1:5000/backup/purchases
##http://127.0.0.1:5000/backup/sales