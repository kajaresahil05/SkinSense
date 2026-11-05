"""
SkinSense — Intelligent Dermatological Assessment System
Main Application Factory — v2.0
Enhanced with: Flask-Limiter, Flask-Talisman security headers,
               new blueprint registrations (review, tracking, report),
               HIPAA audit log initialization, CORS locking, and
               production-safe configuration.
"""
import os
from flask import Flask, jsonify, send_from_directory, session
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from config import Config
from backend.database.db import init_db
from backend.services.model_service import ModelService
from backend.services.fuzzy_service import FuzzySeverityEngine
from backend.services.xai_service import XAIService
from backend.services.conversation_service import ConversationService
from backend.services.assessment_service import AssessmentService
from backend.services.image_validation_service import ImageSuitabilityValidator
from backend.services.security_service import init_audit_log

# Blueprints
from backend.routes.auth import auth_bp, login_required
from backend.routes.prediction import prediction_bp
from backend.routes.chatbot import chatbot_bp
from backend.routes.assessments import assessments_bp
from backend.routes.analytics import analytics_bp
from backend.routes.xai import xai_bp
from backend.routes.review import review_bp
from backend.routes.tracking import tracking_bp
from backend.routes.report import report_bp
try:
    from backend.routes.admin import admin_bp
except ImportError:
    admin_bp = None
try:
    from backend.routes.conditions import conditions_bp
except ImportError:
    conditions_bp = None

# ─────────────────────────────────────────────────
# Global Rate Limiter (in-memory storage)
# ─────────────────────────────────────────────────
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "60 per hour"],
    storage_uri="memory://",
)

import numpy as np
from flask.json.provider import DefaultJSONProvider

class CustomJSONProvider(DefaultJSONProvider):
    """JSON provider that automatically converts NumPy data types for Flask responses."""
    def default(self, o):
        if isinstance(o, (np.bool_, bool)):
            return bool(o)
        if isinstance(o, np.integer):
            return int(o)
        if isinstance(o, np.floating):
            return float(o)
        if isinstance(o, np.ndarray):
            return o.tolist()
        return super().default(o)


def create_app():
    app = Flask(__name__, static_folder='frontend', template_folder='frontend')
    app.json_provider_class = CustomJSONProvider
    app.json = CustomJSONProvider(app)
    app.config.from_object(Config)

    # ── CORS: Lock to specific origin in production ──
    allowed_origins = os.environ.get('ALLOWED_ORIGINS', 'http://127.0.0.1:5000,http://localhost:5000')
    origins_list = [o.strip() for o in allowed_origins.split(',')]
    CORS(app, origins=origins_list, supports_credentials=True)

    # ── Rate Limiter ──
    limiter.init_app(app)

    # Apply strict limits to sensitive auth endpoints
    limiter.limit("5 per minute; 20 per hour")(auth_bp)

    # ── Flask-Talisman Security Headers ──
    is_production = os.environ.get('FLASK_ENV', 'development') == 'production'
    if is_production:
        try:
            from flask_talisman import Talisman
            Talisman(app,
                     force_https=True,
                     strict_transport_security=True,
                     strict_transport_security_max_age=31536000,
                     content_security_policy={
                         'default-src': "'self'",
                         'script-src':  ["'self'", "'unsafe-inline'", "cdn.jsdelivr.net", "cdnjs.cloudflare.com"],
                         'style-src':   ["'self'", "'unsafe-inline'", "cdn.jsdelivr.net", "fonts.googleapis.com"],
                         'img-src':     ["'self'", "data:", "blob:"],
                         'font-src':    ["'self'", "fonts.gstatic.com"],
                         'connect-src': "'self'",
                     })
            print("[App] Flask-Talisman security headers active (production mode).")
        except ImportError:
            print("[App] Flask-Talisman not installed — security headers skipped.")

    # ── Directories ──
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(os.path.dirname(app.config['DATABASE_PATH']), exist_ok=True)

    # ── Database Initialization ──
    init_db(app.config['DATABASE_PATH'])

    # ── Audit Log Table ──
    init_audit_log(app.config['DATABASE_PATH'])

    # ── Core ML, XAI & Reasoning Services ──
    model_service = ModelService(
        model_path=app.config['MODEL_PATH'],
        class_names_path=app.config['MODEL_CLASS_NAMES_PATH'],
        class_labels_path=app.config['CLASS_LABELS_PATH']
    )
    fuzzy_engine = FuzzySeverityEngine()
    xai_service = XAIService(
        model_service=model_service,
        fuzzy_engine=fuzzy_engine,
        upload_folder=app.config['UPLOAD_FOLDER']
    )
    conversation_service = ConversationService(
        model_service=model_service,
        fuzzy_engine=fuzzy_engine,
        db_path=app.config['DATABASE_PATH'],
        gemini_api_key=app.config.get('GEMINI_API_KEY')
    )
    model_service.image_validator = ImageSuitabilityValidator(conversation_service.client)
    assessment_service = AssessmentService(
        model_service=model_service,
        fuzzy_engine=fuzzy_engine,
        db_path=app.config['DATABASE_PATH'],
        xai_service=xai_service,
        gemini_client=conversation_service.client
    )

    # ── Bind Services to App Config ──
    app.config['MODEL_SERVICE']        = model_service
    app.config['FUZZY_ENGINE']         = fuzzy_engine
    app.config['XAI_SERVICE']          = xai_service
    app.config['CONVERSATION_SERVICE'] = conversation_service
    app.config['ASSESSMENT_SERVICE']   = assessment_service

    # ── Register Blueprints ──
    app.register_blueprint(auth_bp)
    app.register_blueprint(prediction_bp)
    app.register_blueprint(chatbot_bp)
    app.register_blueprint(assessments_bp)
    app.register_blueprint(analytics_bp)
    app.register_blueprint(xai_bp)
    app.register_blueprint(review_bp)
    app.register_blueprint(tracking_bp)
    app.register_blueprint(report_bp)
    if admin_bp:
        app.register_blueprint(admin_bp)
    if conditions_bp:
        app.register_blueprint(conditions_bp)

    # ── Health Check Endpoint ──
    @app.route('/api/health', methods=['GET'])
    def health_check():
        model_ok = model_service.is_loaded
        fuzzy_ok = fuzzy_engine is not None
        xai_ok   = xai_service.gradcam_engine is not None

        if model_ok and fuzzy_ok and xai_ok:
            status_str = "Dataset2 Keras MobileNetV2, Fuzzy & Grad-CAM XAI Active"
        elif model_ok:
            status_str = "Partial Degradation — XAI unavailable"
        else:
            status_str = "Systems Offline"

        return jsonify({
            'status':              'healthy' if (model_ok and fuzzy_ok) else 'degraded',
            'system_status_text':  status_str,
            'model_available':     model_ok,
            'model_name':          model_service.MODEL_NAME,
            'fuzzy_engine_available': fuzzy_ok,
            'xai_available':       xai_ok,
            'device':              str(model_service.device),
            'database':            'Connected',
            'features': {
                'mc_dropout':          False,
                'tta':                 False,
                'exif_stripping':      True,
                'magic_byte_check':    True,
                'audit_logging':       True,
                'login_lockout':       True,
                'pdf_reports':         True,
                'review_queue':        True,
                'lesion_tracking':     True,
                'rate_limiting':       True,
            },
            'authenticated':       'user_id' in session,
            'version':             '2.0.0'
        })

    # ── Serve Uploaded Files (Login Protected) ──
    @app.route('/uploads/<path:filename>')
    @login_required
    def uploaded_file(filename):
        return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

    # ── Serve Frontend SPA ──
    @app.route('/')
    def index():
        return send_from_directory('frontend', 'index.html')

    @app.route('/<any(css,js):folder>/<path:filename>')
    @limiter.exempt
    def frontend_asset(folder, filename):
        return app.send_static_file(f'{folder}/{filename}')

    @app.route('/<path:path>')
    def serve_static(path):
        if os.path.exists(os.path.join('frontend', path)):
            return send_from_directory('frontend', path)
        return send_from_directory('frontend', 'index.html')

    return app


if __name__ == '__main__':
    app = create_app()
    print("=" * 60)
    print(" SkinSense v2.0 — Intelligent Dermatological Assessment")
    print(" Running on http://127.0.0.1:5000")
    print(" Features: Dataset2 MobileNetV2 | EXIF Strip | Audit Logs")
    print("           Review Queue | Lesion Tracking | PDF Reports")
    print("=" * 60)
    # Never use debug=True in production
    debug_mode = os.environ.get('FLASK_ENV', 'development') == 'development'
    app.run(host='127.0.0.1', port=5000, debug=debug_mode)
