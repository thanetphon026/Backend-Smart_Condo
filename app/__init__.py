from flask import Flask
from flask_cors import CORS
from .config import Config

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    
    # Custom JSON Provider for ObjectId and Datetime
    from .utils.json_provider import MongoJSONProvider
    app.json = MongoJSONProvider(app)
    
    CORS(app, resources={r"/api/*": {"origins": "*"}})

    from .utils.helpers import token_required

    # Health check endpoint for monitoring/cron-jobs
    @app.route('/healthz')
    def health_check():
        return {"status": "ok", "message": "Server is running"}, 200
    
    # Import Utils to ensure DB connection
    from .utils import db
    db.ensure_indexes()
    
    # Register Blueprints
    from .routes.webhook import webhook_bp
    from .routes.admin_auth import auth_bp
    from .routes.admin_dashboard import dashboard_bp
    from .routes.admin_parcels import parcels_bp
    from .routes.admin_users import users_bp
    from .routes.admin_logs import logs_bp
    from .routes.maintenance import maintenance_bp
    from .routes.web_chat import web_chat_bp
    
    app.register_blueprint(webhook_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(parcels_bp)
    app.register_blueprint(users_bp)
    app.register_blueprint(logs_bp)
    app.register_blueprint(maintenance_bp)
    app.register_blueprint(web_chat_bp)
    
    return app
