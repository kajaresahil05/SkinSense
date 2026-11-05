"""
SkinSense Authentication Routes — v2.0
Enhanced with:
  - Login lockout (10 attempts / 15 minutes)
  - Strong password policy (8+ chars, uppercase, digit, special char)
  - HIPAA audit logging on every auth event
  - Flask-Limiter rate limiting (5 req/min on login)
  - Password strength check endpoint for real-time frontend feedback
  - Account lockout status endpoint
"""
import re
from functools import wraps
from flask import Blueprint, request, jsonify, session, current_app, redirect
from backend.database.db import (
    create_user,
    get_user_by_email,
    get_user_by_id,
    verify_user_credentials
)
from backend.services.security_service import (
    assess_password_strength,
    write_audit_log,
    record_failed_login,
    is_locked_out,
    clear_login_attempts
)

auth_bp = Blueprint('auth', __name__)


def _get_client_ip():
    """Extract real client IP respecting X-Forwarded-For proxies."""
    xff = request.headers.get('X-Forwarded-For')
    if xff:
        return xff.split(',')[0].strip()
    return request.remote_addr or 'unknown'


def _get_user_agent():
    return request.headers.get('User-Agent', 'unknown')[:255]


# ─────────────────────────────────────────────
# DECORATORS FOR BACKEND ROUTE PROTECTION
# ─────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            if request.path.startswith('/api/'):
                return jsonify({
                    'status': 'error',
                    'message': 'Authentication required. Please log in to access your skin health data.'
                }), 401
            return redirect('/')
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session.get('user_role') != 'admin':
            if request.path.startswith('/api/'):
                return jsonify({
                    'status': 'error',
                    'message': 'Administrator access required for system analytics.'
                }), 403
            return redirect('/')
        return f(*args, **kwargs)
    return decorated_function


# ─────────────────────────────────────────────
# AUTHENTICATION ENDPOINTS
# ─────────────────────────────────────────────

@auth_bp.route('/api/auth/register', methods=['POST'])
def register():
    """
    POST /api/auth/register
    Register new patient account with strong password enforcement.
    """
    data = request.get_json(silent=True) or request.form or {}
    ip = _get_client_ip()
    ua = _get_user_agent()
    db_path = current_app.config['DATABASE_PATH']

    full_name        = data.get('full_name', '').strip()
    email            = data.get('email', '').strip().lower()
    password         = data.get('password', '')
    confirm_password = data.get('confirm_password', '')

    # --- Basic field validation ---
    if not full_name or not email or not password:
        return jsonify({'status': 'error', 'message': 'Full name, email, and password are required.'}), 400

    if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
        return jsonify({'status': 'error', 'message': 'Please enter a valid email address.'}), 400

    if password != confirm_password:
        return jsonify({'status': 'error', 'message': 'Passwords do not match.'}), 400

    # --- Strong password policy check ---
    strength = assess_password_strength(password, user_inputs=[full_name, email])
    if not strength['passes_policy']:
        return jsonify({
            'status': 'error',
            'message': 'Password does not meet security requirements: ' + ' '.join(strength['feedback']),
            'password_strength': strength
        }), 400

    try:
        user = create_user(db_path, full_name, email, password, role='patient')

        # Auto-login on registration
        session['user_id']    = user['id']
        session['user_name']  = user['full_name']
        session['user_email'] = user['email']
        session['user_role']  = user['role']

        # HIPAA Audit
        write_audit_log(db_path, 'register',
                        user_id=user['id'], user_email=email,
                        ip_address=ip, user_agent=ua,
                        resource='users', status='success')

        return jsonify({
            'status': 'success',
            'message': 'Account created successfully. Welcome to SkinSense!',
            'user': user
        })

    except ValueError as ve:
        write_audit_log(db_path, 'register',
                        user_email=email, ip_address=ip, user_agent=ua,
                        status='failed', details=str(ve))
        return jsonify({'status': 'error', 'message': str(ve)}), 400
    except Exception as e:
        current_app.logger.error("[Auth Registration Error] %s", e, exc_info=True)
        return jsonify({'status': 'error', 'message': 'Registration failed due to a server error.'}), 500


@auth_bp.route('/api/auth/login', methods=['POST'])
def login():
    """
    POST /api/auth/login
    Patient Login with rate limiting, lockout protection, and audit trail.
    """
    data  = request.get_json(silent=True) or request.form or {}
    ip    = _get_client_ip()
    ua    = _get_user_agent()
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')
    db_path  = current_app.config['DATABASE_PATH']

    if not email or not password:
        return jsonify({'status': 'error', 'message': 'Email and password are required.'}), 400

    # --- Lockout check (by email AND by IP) ---
    for identifier in [email, ip]:
        locked, remaining = is_locked_out(identifier)
        if locked:
            minutes = remaining // 60
            seconds = remaining % 60
            write_audit_log(db_path, 'login_blocked',
                            user_email=email, ip_address=ip, user_agent=ua,
                            status='blocked', details='Lockout: {} remaining'.format(remaining))
            return jsonify({
                'status': 'error',
                'message': 'Account temporarily locked due to too many failed attempts. '
                           'Try again in {}m {}s.'.format(minutes, seconds),
                'locked_out': True,
                'retry_after_seconds': remaining
            }), 429

    user = verify_user_credentials(db_path, email, password)

    if not user:
        record_failed_login(email)
        record_failed_login(ip)
        write_audit_log(db_path, 'login_failed',
                        user_email=email, ip_address=ip, user_agent=ua, status='failed')
        return jsonify({'status': 'error', 'message': 'Invalid email address or password.'}), 401

    # --- Success ---
    clear_login_attempts(email)
    clear_login_attempts(ip)

    session['user_id']    = user['id']
    session['user_name']  = user['full_name']
    session['user_email'] = user['email']
    session['user_role']  = user['role']

    write_audit_log(db_path, 'login',
                    user_id=user['id'], user_email=email,
                    ip_address=ip, user_agent=ua, status='success')

    return jsonify({
        'status': 'success',
        'message': 'Login successful. Welcome back, {}!'.format(user['full_name']),
        'user': user
    })


@auth_bp.route('/api/auth/admin-login', methods=['POST'])
def admin_login():
    """
    POST /api/auth/admin-login
    Administrator Login with full audit trail and lockout.
    """
    data     = request.get_json(silent=True) or request.form or {}
    ip       = _get_client_ip()
    ua       = _get_user_agent()
    email    = data.get('email', '').strip().lower()
    password = data.get('password', '')
    db_path  = current_app.config['DATABASE_PATH']

    if not email or not password:
        return jsonify({'status': 'error', 'message': 'Admin email and password are required.'}), 400

    # Lockout check
    for identifier in [email, ip]:
        locked, remaining = is_locked_out(identifier)
        if locked:
            return jsonify({
                'status': 'error',
                'message': 'Too many failed attempts. Try again in {}s.'.format(remaining),
                'locked_out': True,
                'retry_after_seconds': remaining
            }), 429

    user = verify_user_credentials(db_path, email, password)

    if not user or user['role'] != 'admin':
        record_failed_login(email)
        record_failed_login(ip)
        write_audit_log(db_path, 'admin_login_failed',
                        user_email=email, ip_address=ip, user_agent=ua, status='failed')
        return jsonify({'status': 'error', 'message': 'Invalid administrator credentials or unauthorized account.'}), 401

    clear_login_attempts(email)
    clear_login_attempts(ip)

    session['user_id']    = user['id']
    session['user_name']  = user['full_name']
    session['user_email'] = user['email']
    session['user_role']  = 'admin'

    write_audit_log(db_path, 'admin_login',
                    user_id=user['id'], user_email=email,
                    ip_address=ip, user_agent=ua, status='success')

    return jsonify({
        'status': 'success',
        'message': 'Administrator authenticated.',
        'user': user
    })


@auth_bp.route('/api/auth/logout', methods=['POST'])
def logout():
    """POST /api/auth/logout — Clear server session."""
    db_path    = current_app.config['DATABASE_PATH']
    user_id    = session.get('user_id')
    user_email = session.get('user_email')
    ip         = _get_client_ip()
    ua         = _get_user_agent()

    session.clear()

    write_audit_log(db_path, 'logout',
                    user_id=user_id, user_email=user_email,
                    ip_address=ip, user_agent=ua, status='success')

    return jsonify({'status': 'success', 'message': 'Logged out successfully.'})


@auth_bp.route('/api/auth/me', methods=['GET'])
def get_current_user():
    """GET /api/auth/me — Return active session user profile."""
    if 'user_id' in session:
        return jsonify({
            'status': 'success',
            'authenticated': True,
            'user': {
                'id':                 session['user_id'],
                'full_name':          session.get('user_name', 'Patient'),
                'email':              session.get('user_email', ''),
                'role':               session.get('user_role', 'patient'),
                'preferred_language': session.get('lang', 'en')
            }
        })
    return jsonify({'status': 'success', 'authenticated': False, 'user': None})


@auth_bp.route('/api/auth/language', methods=['POST'])
def set_user_language():
    """
    POST /api/auth/language
    Update session and DB user preferred language.
    """
    from backend.database.db import update_user_preferred_language
    data = request.get_json(silent=True) or request.form or {}
    lang = (data.get('lang') or data.get('language') or 'en').strip().lower()

    session['lang'] = lang

    if 'user_id' in session:
        db_path = current_app.config['DATABASE_PATH']
        update_user_preferred_language(db_path, session['user_id'], lang)

    return jsonify({
        'status': 'success',
        'message': 'Language preference updated to {}'.format(lang),
        'preferred_language': lang
    })



@auth_bp.route('/api/auth/password-strength', methods=['POST'])
def check_password_strength():
    """
    POST /api/auth/password-strength
    Real-time password strength check for frontend UX.
    Body: { "password": "...", "full_name": "...", "email": "..." }
    """
    data     = request.get_json(silent=True) or {}
    password = data.get('password', '')
    inputs   = [v for v in [data.get('full_name', ''), data.get('email', '')] if v]

    result = assess_password_strength(password, user_inputs=inputs)
    return jsonify({'status': 'success', 'strength': result})


@auth_bp.route('/api/auth/lockout-status', methods=['POST'])
def check_lockout_status():
    """
    POST /api/auth/lockout-status
    Check if email is currently locked out.
    """
    data  = request.get_json(silent=True) or {}
    email = data.get('email', '').strip().lower()
    ip    = _get_client_ip()

    locked_email, rem_email = is_locked_out(email)
    locked_ip, rem_ip       = is_locked_out(ip)

    is_locked  = locked_email or locked_ip
    remaining  = max(rem_email, rem_ip)

    return jsonify({
        'status': 'success',
        'locked_out': is_locked,
        'retry_after_seconds': remaining
    })


@auth_bp.route('/api/auth/audit-log', methods=['GET'])
@admin_required
def get_audit_log_endpoint():
    """
    GET /api/auth/audit-log
    Admin-only endpoint to retrieve HIPAA audit trail.
    """
    from backend.services.security_service import get_audit_log
    db_path = current_app.config['DATABASE_PATH']
    action  = request.args.get('action')
    user_id = request.args.get('user_id')
    limit   = int(request.args.get('limit', 100))

    logs = get_audit_log(db_path, user_id=user_id, action=action, limit=limit)
    return jsonify({'status': 'success', 'count': len(logs), 'logs': logs})


# ─────────────────────────────────────────────
# PASSWORD RESET FLOW
# ─────────────────────────────────────────────

@auth_bp.route('/api/auth/forgot-password', methods=['POST'])
def forgot_password():
    """
    POST /api/auth/forgot-password
    Generate a time-limited password reset token.
    Body: { "email": "user@example.com" }
    Returns the token directly (in production, email it instead).
    """
    import secrets
    from datetime import datetime, timedelta
    from backend.database.db import get_db_connection

    data    = request.get_json(silent=True) or request.form or {}
    email   = data.get('email', '').strip().lower()
    ip      = _get_client_ip()
    ua      = _get_user_agent()
    db_path = current_app.config['DATABASE_PATH']

    if not email:
        return jsonify({'status': 'error', 'message': 'Email address is required.'}), 400

    # Lookup user — always respond the same to prevent email enumeration
    user = get_user_by_email(db_path, email)
    if not user:
        # Security: don't reveal that email doesn't exist
        return jsonify({
            'status': 'success',
            'message': 'If this email is registered, a reset token has been generated.',
            'reset_token': None
        })

    # Generate secure token (32 hex chars = 128-bit)
    token   = secrets.token_hex(32)
    expires = (datetime.utcnow() + timedelta(hours=1)).isoformat()

    # Store token in database
    try:
        conn = get_db_connection(db_path)
        conn.execute(
            "UPDATE users SET password_reset_token = ?, reset_token_expires = ? WHERE id = ?",
            (token, expires, user['id'])
        )
        conn.commit()
        conn.close()
    except Exception as e:
        current_app.logger.error("[Auth] Failed to save reset token: %s", e)
        return jsonify({'status': 'error', 'message': 'Server error generating token.'}), 500

    write_audit_log(db_path, 'password_reset_requested',
                    user_id=user['id'], user_email=email,
                    ip_address=ip, user_agent=ua, status='success')

    return jsonify({
        'status':      'success',
        'message':     'Password reset token generated. Token valid for 1 hour.',
        'reset_token': token,        # In production: send via email, don't return in response
        'expires_in':  '1 hour'
    })


@auth_bp.route('/api/auth/reset-password', methods=['POST'])
def reset_password():
    """
    POST /api/auth/reset-password
    Verify reset token and update password.
    Body: { "token": "...", "new_password": "...", "confirm_password": "..." }
    """
    from datetime import datetime
    from backend.database.db import get_db_connection
    from werkzeug.security import generate_password_hash

    data             = request.get_json(silent=True) or request.form or {}
    token            = data.get('token', '').strip()
    new_password     = data.get('new_password', '')
    confirm_password = data.get('confirm_password', '')
    ip               = _get_client_ip()
    ua               = _get_user_agent()
    db_path          = current_app.config['DATABASE_PATH']

    if not token or not new_password:
        return jsonify({'status': 'error', 'message': 'Reset token and new password are required.'}), 400

    if new_password != confirm_password:
        return jsonify({'status': 'error', 'message': 'Passwords do not match.'}), 400

    # Validate password strength
    strength = assess_password_strength(new_password)
    if not strength['passes_policy']:
        return jsonify({
            'status':  'error',
            'message': 'Password does not meet requirements: ' + ' '.join(strength['feedback'])
        }), 400

    # Look up token
    try:
        conn = get_db_connection(db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, email, full_name, reset_token_expires FROM users WHERE password_reset_token = ?",
            (token,)
        )
        row = cursor.fetchone()
    except Exception as e:
        conn.close()
        return jsonify({'status': 'error', 'message': 'Database error.'}), 500

    if not row:
        conn.close()
        return jsonify({'status': 'error', 'message': 'Invalid or expired reset token.'}), 400

    # Check expiry
    if row['reset_token_expires']:
        try:
            expires = datetime.fromisoformat(row['reset_token_expires'])
            if datetime.utcnow() > expires:
                conn.close()
                return jsonify({'status': 'error', 'message': 'Reset token has expired. Please request a new one.'}), 400
        except Exception:
            pass  # If we can't parse, allow through (be lenient on migration)

    # Update password and clear token
    new_hash = generate_password_hash(new_password)
    conn.execute(
        "UPDATE users SET password_hash = ?, password_reset_token = NULL, reset_token_expires = NULL WHERE id = ?",
        (new_hash, row['id'])
    )
    conn.commit()
    conn.close()

    write_audit_log(db_path, 'password_reset',
                    user_id=row['id'], user_email=row['email'],
                    ip_address=ip, user_agent=ua, status='success')

    return jsonify({'status': 'success', 'message': 'Password has been reset successfully. Please log in.'})


# ─────────────────────────────────────────────
# PATIENT PROFILE MANAGEMENT
# ─────────────────────────────────────────────

@auth_bp.route('/api/auth/profile', methods=['GET'])
@login_required
def get_profile():
    """GET /api/auth/profile — Return authenticated user's full profile."""
    db_path = current_app.config['DATABASE_PATH']
    user_id = session.get('user_id')
    user    = get_user_by_id(db_path, user_id)

    if not user:
        return jsonify({'status': 'error', 'message': 'User not found.'}), 404

    # Exclude password hash from response
    safe_fields = ['id', 'full_name', 'email', 'role', 'created_at', 'last_login',
                   'date_of_birth', 'phone_number', 'fitzpatrick_type']
    profile = {k: user.get(k) for k in safe_fields if k in user}

    return jsonify({'status': 'success', 'profile': profile})


@auth_bp.route('/api/auth/profile', methods=['PUT'])
@login_required
def update_profile():
    """PUT /api/auth/profile — Update authenticated user's profile fields."""
    from backend.database.db import get_db_connection

    data    = request.get_json(silent=True) or request.form or {}
    user_id = session.get('user_id')
    db_path = current_app.config['DATABASE_PATH']
    ip      = _get_client_ip()
    ua      = _get_user_agent()

    allowed_fields = ['full_name', 'date_of_birth', 'phone_number', 'fitzpatrick_type']
    updates = {k: v for k, v in data.items() if k in allowed_fields and v is not None}

    if not updates:
        return jsonify({'status': 'error', 'message': 'No valid fields to update.'}), 400

    # Validate full_name if provided
    if 'full_name' in updates and not updates['full_name'].strip():
        return jsonify({'status': 'error', 'message': 'Full name cannot be empty.'}), 400

    try:
        set_clause = ', '.join(f"{k} = ?" for k in updates.keys())
        values     = list(updates.values()) + [user_id]
        conn       = get_db_connection(db_path)
        conn.execute(f"UPDATE users SET {set_clause} WHERE id = ?", values)
        conn.commit()
        conn.close()
    except Exception as e:
        current_app.logger.error("[Auth] Profile update failed: %s", e)
        return jsonify({'status': 'error', 'message': 'Profile update failed.'}), 500

    # Update session name if full_name changed
    if 'full_name' in updates:
        session['user_name'] = updates['full_name']

    write_audit_log(db_path, 'profile_updated',
                    user_id=user_id, user_email=session.get('user_email'),
                    ip_address=ip, user_agent=ua, status='success',
                    details=', '.join(updates.keys()))

    return jsonify({'status': 'success', 'message': 'Profile updated successfully.'})


@auth_bp.route('/api/auth/change-password', methods=['POST'])
@login_required
def change_password():
    """POST /api/auth/change-password — Change password for authenticated user."""
    from backend.database.db import get_db_connection
    from werkzeug.security import check_password_hash, generate_password_hash

    data         = request.get_json(silent=True) or request.form or {}
    user_id      = session.get('user_id')
    db_path      = current_app.config['DATABASE_PATH']
    ip           = _get_client_ip()
    ua           = _get_user_agent()

    current_pw   = data.get('current_password', '')
    new_pw       = data.get('new_password', '')
    confirm_pw   = data.get('confirm_password', '')

    if not current_pw or not new_pw:
        return jsonify({'status': 'error', 'message': 'Current and new passwords are required.'}), 400
    if new_pw != confirm_pw:
        return jsonify({'status': 'error', 'message': 'New passwords do not match.'}), 400

    user = get_user_by_id(db_path, user_id)
    if not user or not check_password_hash(user['password_hash'], current_pw):
        write_audit_log(db_path, 'password_change_failed',
                        user_id=user_id, ip_address=ip, user_agent=ua, status='failed')
        return jsonify({'status': 'error', 'message': 'Current password is incorrect.'}), 401

    strength = assess_password_strength(new_pw)
    if not strength['passes_policy']:
        return jsonify({
            'status':  'error',
            'message': 'New password does not meet requirements: ' + ' '.join(strength['feedback'])
        }), 400

    try:
        conn     = get_db_connection(db_path)
        new_hash = generate_password_hash(new_pw)
        conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (new_hash, user_id))
        conn.commit()
        conn.close()
    except Exception as e:
        return jsonify({'status': 'error', 'message': 'Server error updating password.'}), 500

    write_audit_log(db_path, 'password_changed',
                    user_id=user_id, user_email=session.get('user_email'),
                    ip_address=ip, user_agent=ua, status='success')

    return jsonify({'status': 'success', 'message': 'Password changed successfully.'})


# ─────────────────────────────────────────────
# PATIENT ASSESSMENTS ALIAS (for Dashboard)
# ─────────────────────────────────────────────

@auth_bp.route('/api/patient/assessments', methods=['GET'])
@login_required
def patient_assessments():
    """
    GET /api/patient/assessments
    Alias for /api/history — returns the authenticated patient's assessments.
    Used by the Dashboard JS module.
    """
    from backend.database.db import get_all_assessments
    db_path  = current_app.config['DATABASE_PATH']
    user_id  = session.get('user_id')
    is_admin = (session.get('user_role') == 'admin')
    limit    = int(request.args.get('limit', 50))

    records = get_all_assessments(db_path, user_id=user_id, is_admin=is_admin)
    return jsonify({
        'status':      'success',
        'count':       len(records),
        'assessments': records[:limit]
    })
