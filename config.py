import os
import secrets
from dotenv import load_dotenv

# Load environment variables from .env if present
load_dotenv()

class Config:
    # ── Core Security ──
    SECRET_KEY = os.environ.get('SECRET_KEY') or secrets.token_hex(32)
    if not os.environ.get('SECRET_KEY'):
        import warnings
        warnings.warn(
            "[SkinSense] SECRET_KEY not set in environment! "
            "A random key was generated — sessions will not persist across restarts. "
            "Set SECRET_KEY in your .env file for production.",
            RuntimeWarning, stacklevel=2
        )

    # ── Session Cookie Security (HIPAA / OWASP) ──
    SESSION_COOKIE_HTTPONLY  = True          # Prevent JS access to session cookie
    SESSION_COOKIE_SAMESITE  = 'Lax'        # CSRF protection (Lax = safe for forms)
    SESSION_COOKIE_SECURE    = os.environ.get('FLASK_ENV') == 'production'  # HTTPS in prod
    SESSION_COOKIE_NAME      = '__Secure-skinsense-session' if os.environ.get('FLASK_ENV') == 'production' else 'skinsense-session'
    PERMANENT_SESSION_LIFETIME = 3600 * 8   # 8 hours (28800 seconds)

    # ── Paths ──
    BASE_DIR          = os.path.abspath(os.path.dirname(__file__))
    DATABASE_PATH     = os.path.join(BASE_DIR, 'backend', 'database', 'skinsense.db')
    UPLOAD_FOLDER     = os.path.join(BASE_DIR, 'uploads')
    MODEL_PATH        = os.path.join(BASE_DIR, 'Dataset2', 'skinsense_dataset2_mobilenetv2.keras')
    MODEL_CLASS_NAMES_PATH = os.path.join(BASE_DIR, 'Dataset2', 'skinsense_dataset2_class_names.json')
    CLASS_LABELS_PATH = os.path.join(BASE_DIR, 'models', 'class_labels.json')
    EVALUATION_METRICS_PATH = os.path.join(BASE_DIR, 'Dataset2', 'evaluation_metrics.json')

    # ── Upload Limits ──
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024   # 16 MB
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}

    # ── External APIs ──
    GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')

    # ── Application ──
    DEBUG = os.environ.get('FLASK_ENV', 'development') != 'production'
    TESTING = False
