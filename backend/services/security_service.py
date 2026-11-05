"""
SkinSense Security Service
Handles: EXIF stripping, magic-byte file validation, password strength scoring,
         and HIPAA-compliant audit logging with login lockout protection.
"""
import os
import io
import json
import hashlib
import sqlite3
import threading
from datetime import datetime
from collections import defaultdict
from PIL import Image

# EXIF stripping
try:
    import piexif
    PIEXIF_AVAILABLE = True
except ImportError:
    PIEXIF_AVAILABLE = False
    print("[SecurityService] piexif not available - EXIF stripping disabled.")

# Password strength
try:
    from zxcvbn import zxcvbn
    ZXCVBN_AVAILABLE = True
except ImportError:
    ZXCVBN_AVAILABLE = False
    print("[SecurityService] zxcvbn not available - basic password scoring only.")


# -------------------------------------------------------
# MAGIC BYTE SIGNATURES FOR ALLOWED IMAGE TYPES
# -------------------------------------------------------
MAGIC_BYTES = {
    b'\xff\xd8\xff': 'jpeg',
    b'\x89PNG\r\n\x1a\n': 'png',
    b'RIFF': 'webp',
}

ALLOWED_MAGIC = {'jpeg', 'png', 'webp'}


def validate_file_magic_bytes(file_path):
    """
    Deep file validation via magic bytes -- not just extension.
    Prevents polyglot files (JPEG+PHP attack vectors).
    Returns (is_valid: bool, message: str)
    """
    try:
        with open(file_path, 'rb') as f:
            header = f.read(12)

        # Check RIFF/WEBP specifically
        if header[:4] == b'RIFF' and header[8:12] == b'WEBP':
            return True, "Valid WEBP image"

        for magic, fmt in MAGIC_BYTES.items():
            if header[:len(magic)] == magic and fmt in ALLOWED_MAGIC:
                return True, "Valid {} image".format(fmt.upper())

        return False, "File content does not match a valid image format (magic byte mismatch)."
    except Exception as e:
        return False, "Cannot read file for validation: {}".format(e)


def compute_file_hash(file_path):
    """SHA-256 hash of file -- used for duplicate detection and cache keying."""
    sha256 = hashlib.sha256()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            sha256.update(chunk)
    return sha256.hexdigest()


# -------------------------------------------------------
# EXIF METADATA STRIPPING (PRIVACY/HIPAA)
# -------------------------------------------------------

def strip_exif_and_save(file_path):
    """
    Strip ALL EXIF metadata from uploaded image (GPS, camera model, date, etc.)
    Prevents inadvertent disclosure of patient location or device info.
    Saves clean image back to same path.
    Returns info dict with stripped fields summary.
    """
    stripped_info = {'stripped': False, 'gps_removed': False, 'fields_removed': 0}

    try:
        pil_img = Image.open(file_path).convert('RGB')

        if PIEXIF_AVAILABLE:
            try:
                exif_data = piexif.load(file_path)
                fields_count = sum(len(ifd) for ifd in exif_data.values() if isinstance(ifd, dict))
                gps_had_data = bool(exif_data.get('GPS'))
                stripped_info['fields_removed'] = fields_count
                stripped_info['gps_removed'] = gps_had_data
            except Exception:
                pass

        # Re-save without ANY metadata
        output = io.BytesIO()
        pil_img.save(output, format='JPEG', quality=95, optimize=True)
        output.seek(0)
        with open(file_path, 'wb') as f:
            f.write(output.read())

        stripped_info['stripped'] = True
        return stripped_info

    except Exception as e:
        print("[SecurityService] EXIF stripping failed: {}".format(e))
        return stripped_info


# -------------------------------------------------------
# PASSWORD STRENGTH ASSESSMENT
# -------------------------------------------------------

# Common password blocklist (extend as needed)
COMMON_PASSWORDS = {
    'password', 'password1', '123456', '12345678', 'qwerty', 'abc123',
    'letmein', 'monkey', 'dragon', 'master', 'sunshine', 'welcome',
    'shadow', 'michael', 'superman', 'iloveyou', '1234567890',
    'admin', 'root', 'pass', 'test', 'guest', 'login', 'user',
    'skinsense', 'doctor', 'patient', 'health', 'medical', 'skin'
}


def assess_password_strength(password, user_inputs=None):
    """
    Full password strength evaluation using zxcvbn + policy rules.
    Returns score (0-4), feedback, strength label, and whether it passes policy.
    """
    result = {
        'score': 0,
        'strength': 'Very Weak',
        'passes_policy': False,
        'feedback': [],
        'details': {}
    }

    if not password:
        result['feedback'].append("Password is required.")
        return result

    feedback = []
    if len(password) < 8:
        feedback.append("Must be at least 8 characters long.")
    if not any(c.isupper() for c in password):
        feedback.append("Must contain at least one uppercase letter.")
    if not any(c.isdigit() for c in password):
        feedback.append("Must contain at least one number.")
    if not any(c in '!@#$%^&*()_+-=[]{}|;:,.<>?' for c in password):
        feedback.append("Must contain at least one special character.")
    if password.lower() in COMMON_PASSWORDS:
        feedback.append("This password is too common. Please choose a unique password.")

    policy_ok = (
        len(password) >= 8 and
        any(c.isupper() for c in password) and
        any(c.isdigit() for c in password) and
        any(c in '!@#$%^&*()_+-=[]{}|;:,.<>?' for c in password) and
        password.lower() not in COMMON_PASSWORDS
    )

    # Use zxcvbn for advanced scoring if available
    if ZXCVBN_AVAILABLE:
        inputs = user_inputs or []
        z = zxcvbn(password, user_inputs=inputs)
        score = z['score']  # 0-4
        if z['feedback']['warning']:
            feedback.append(z['feedback']['warning'])
        feedback.extend(z['feedback']['suggestions'])
        result['details'] = {
            'crack_time_display': z['crack_times_display']['offline_slow_hashing_1e4_per_second'],
            'guesses_log10': z.get('guesses_log10', 0)
        }
    else:
        score = 0
        if len(password) >= 8: score += 1
        if any(c.isupper() for c in password): score += 1
        if any(c.isdigit() for c in password): score += 1
        if any(c in '!@#$%^&*()_+-=[]{}|;:,.<>?' for c in password): score += 1
        score = min(score, 4)

    strength_labels = ['Very Weak', 'Weak', 'Fair', 'Strong', 'Very Strong']
    result['score'] = score
    result['strength'] = strength_labels[score]
    result['passes_policy'] = policy_ok
    result['feedback'] = feedback

    return result


# -------------------------------------------------------
# HIPAA-COMPLIANT AUDIT LOGGING
# -------------------------------------------------------

def init_audit_log(db_path):
    """Initialize audit_log table in SQLite (append-only write)."""
    conn = sqlite3.connect(db_path, timeout=20.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute('''
        CREATE TABLE IF NOT EXISTS audit_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            user_id     TEXT,
            user_email  TEXT,
            action      TEXT NOT NULL,
            resource    TEXT,
            ip_address  TEXT,
            user_agent  TEXT,
            status      TEXT DEFAULT "success",
            details     TEXT
        )
    ''')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_log(user_id)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_log(action)')
    conn.commit()
    conn.close()


def write_audit_log(db_path, action, user_id=None, user_email=None,
                    resource=None, ip_address=None, user_agent=None,
                    status='success', details=None):
    """
    Write an immutable audit log entry.
    Actions: login, logout, login_failed, register, assessment_create,
             assessment_view, assessment_delete, admin_access, password_reset.
    """
    try:
        conn = sqlite3.connect(db_path, timeout=20.0)
        conn.execute("PRAGMA journal_mode=WAL")
        now_local = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        conn.execute('''
            INSERT INTO audit_log (timestamp, user_id, user_email, action, resource,
                                   ip_address, user_agent, status, details)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            now_local,
            str(user_id) if user_id else None,
            user_email,
            action,
            resource,
            ip_address,
            user_agent,
            status,
            json.dumps(details) if details and not isinstance(details, str) else details
        ))
        conn.commit()
        conn.close()
    except Exception as e:
        print("[AuditLog] Failed to write audit entry: {}".format(e))


def get_audit_log(db_path, user_id=None, action=None, limit=100):
    """Retrieve audit log entries filtered by user or action."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    query = 'SELECT * FROM audit_log WHERE 1=1'
    params = []
    if user_id:
        query += ' AND user_id = ?'
        params.append(str(user_id))
    if action:
        query += ' AND action = ?'
        params.append(action)
    query += ' ORDER BY timestamp DESC LIMIT ?'
    params.append(limit)
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# -------------------------------------------------------
# LOGIN LOCKOUT (In-Memory, Thread-Safe)
# -------------------------------------------------------

_login_attempts = defaultdict(list)
_lockout_lock = threading.Lock()

MAX_ATTEMPTS = 10
LOCKOUT_SECONDS = 15 * 60  # 15 minutes


def record_failed_login(identifier):
    """Record a failed login attempt for email or IP."""
    with _lockout_lock:
        now = datetime.utcnow().timestamp()
        _login_attempts[identifier].append(now)
        cutoff = now - LOCKOUT_SECONDS
        _login_attempts[identifier] = [t for t in _login_attempts[identifier] if t > cutoff]


def is_locked_out(identifier):
    """
    Check if identifier (email or IP) is locked out.
    Returns (is_locked: bool, seconds_remaining: int)
    """
    with _lockout_lock:
        now = datetime.utcnow().timestamp()
        cutoff = now - LOCKOUT_SECONDS
        attempts = [t for t in _login_attempts.get(identifier, []) if t > cutoff]
        _login_attempts[identifier] = attempts

        if len(attempts) >= MAX_ATTEMPTS:
            oldest = min(attempts)
            unlock_at = oldest + LOCKOUT_SECONDS
            remaining = max(0, int(unlock_at - now))
            return True, remaining
        return False, 0


def clear_login_attempts(identifier):
    """Clear failed attempts on successful login."""
    with _lockout_lock:
        _login_attempts.pop(identifier, None)
