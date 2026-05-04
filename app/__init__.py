from flask import Flask, g, request
from flask_cors import CORS
from .config import Config
import time

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    
    # Custom JSON Provider for ObjectId and Datetime
    from .utils.json_provider import MongoJSONProvider
    app.json = MongoJSONProvider(app)
    
    CORS(app, resources={r"/api/*": {"origins": "*"}})

    @app.before_request
    def start_timer():
        g.start_time = time.perf_counter()

    @app.after_request
    def log_response_time(response):
        if hasattr(g, 'start_time'):
            duration = time.perf_counter() - g.start_time
            path = request.path
            method = request.method
            status = response.status_code
            print(f"⏱️  Response Time: {duration:.4f}s | {method} {path} | Status: {status}", flush=True)
        return response

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
    from .routes.admin_kb import admin_kb_bp
    
    app.register_blueprint(webhook_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(parcels_bp)
    app.register_blueprint(users_bp)
    app.register_blueprint(logs_bp)
    app.register_blueprint(maintenance_bp)
    app.register_blueprint(web_chat_bp)
    app.register_blueprint(admin_kb_bp)
    
    return app
