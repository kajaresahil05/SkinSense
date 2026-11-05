import sqlite3
import json
import os
import uuid
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

def get_db_connection(db_path):
    """Establish connection to SQLite database."""
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=20.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")  # Better concurrent read performance
    conn.execute("PRAGMA foreign_keys=ON")   # Enforce FK constraints
    return conn


def _migrate_column(cursor, table, column, definition):
    """Safely add a column if it doesn't exist."""
    cursor.execute("PRAGMA table_info({})".format(table))
    existing = [col['name'] for col in cursor.fetchall()]
    if column not in existing:
        try:
            cursor.execute("ALTER TABLE {} ADD COLUMN {} {}".format(table, column, definition))
            print("[DB Migration] Added column {}.{}".format(table, column))
        except Exception as e:
            print("[DB Migration] Warning adding {}.{}: {}".format(table, column, e))


def init_db(db_path):
    """Initialize database tables using schema.sql and perform schema migrations."""
    schema_path = os.path.join(os.path.dirname(__file__), 'schema.sql')
    if not os.path.exists(schema_path):
        raise FileNotFoundError("Schema file not found at: {}".format(schema_path))

    conn = get_db_connection(db_path)
    with open(schema_path, 'r', encoding='utf-8') as f:
        schema_sql = f.read()

    conn.executescript(schema_sql)
    cursor = conn.cursor()

    # ── Migrate assessments table ──
    for col, defn in [
        ('user_id',           'INTEGER'),
        ('image_hash',        'TEXT'),
        ('body_region',       'TEXT'),
        ('model_uncertainty', 'REAL'),
        ('model_id',          'TEXT'),
        ('uncertainty_std',   'REAL'),
        ('shap_explanation_json', 'TEXT'),
        ('review_status',     "TEXT DEFAULT 'pending'"),
        ('dermatologist_id',  'INTEGER'),
        ('dermatologist_notes', 'TEXT'),
        ('dermatologist_diagnosis', 'TEXT'),
        ('is_escalated',      'INTEGER DEFAULT 0'),
        ('escalation_reason', 'TEXT'),
        ('pdf_filename',      'TEXT'),
    ]:
        _migrate_column(cursor, 'assessments', col, defn)

    _migrate_column(cursor, 'assessments', 'review_queue_dismissed', 'INTEGER NOT NULL DEFAULT 0')
    _migrate_column(cursor, 'review_queue', 'verdict_category', 'TEXT')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_review_queue_assessment ON review_queue(assessment_id)')
    cursor.execute('''
        CREATE VIEW IF NOT EXISTS active_review_queue AS
        SELECT rq.*
        FROM review_queue rq
        JOIN assessments a ON a.id = rq.assessment_id
        WHERE a.review_queue_dismissed = 0 AND rq.id = (
            SELECT candidate.id FROM review_queue candidate
            WHERE candidate.assessment_id = rq.assessment_id
            ORDER BY CASE
                WHEN NULLIF(TRIM(candidate.derm_verdict), '') IS NOT NULL THEN 0
                WHEN candidate.status IN ('completed', 'rejected') THEN 1
                WHEN candidate.status = 'in_review' THEN 2
                ELSE 3
            END, COALESCE(candidate.completed_at, candidate.created_at) DESC, candidate.id DESC
            LIMIT 1
        )
    ''')

    # ── Migrate conversation_messages table ──
    _migrate_column(cursor, 'conversation_messages', 'user_id', 'INTEGER')

    # ── Migrate users table ──
    for col, defn in [
        ('fitzpatrick_type',       'INTEGER'),
        ('date_of_birth',          'DATE'),
        ('phone_number',           'TEXT'),
        ('is_active',              'INTEGER DEFAULT 1'),
        ('last_login',             'TIMESTAMP'),
        ('password_reset_token',   'TEXT'),
        ('reset_token_expires',    'TEXT'),
        ('preferred_language',     "TEXT DEFAULT 'en'"),
    ]:
        _migrate_column(cursor, 'users', col, defn)


    # ── Seed/Update Default Administrator User ──
    try:
        admin_email = "admin@skinsense.org"
        admin_pass = "Admin@SkinSense2026!"
        admin_pass_hash = generate_password_hash(admin_pass)
        cursor.execute("SELECT id FROM users WHERE LOWER(email) = ?", (admin_email,))
        row = cursor.fetchone()
        if not row:
            cursor.execute("""
                INSERT INTO users (full_name, email, password_hash, role)
                VALUES (?, ?, ?, ?)
            """, ("System Administrator", admin_email, admin_pass_hash, "admin"))
            print("[DB] Default Administrator seeded: admin@skinsense.org")
        else:
            cursor.execute("""
                UPDATE users SET password_hash = ?, role = 'admin' WHERE id = ?
            """, (admin_pass_hash, row['id']))
            print("[DB] Administrator password updated: admin@skinsense.org")
    except Exception as e:
        print("[DB] Note seeding admin: {}".format(e))

    conn.commit()
    conn.close()

    # ── Seed Medical Knowledge Base ──
    seed_medical_knowledge_base(db_path)


# ────────────────────────────────────────────────
# USER AUTHENTICATION
# ────────────────────────────────────────────────

def create_user(db_path, full_name, email, password, role='patient'):
    """Create a new user account with hashed password."""
    email_clean = email.strip().lower()
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM users WHERE LOWER(email) = ?", (email_clean,))
    if cursor.fetchone():
        conn.close()
        raise ValueError("An account with this email address already exists.")

    pass_hash = generate_password_hash(password)
    cursor.execute("""
        INSERT INTO users (full_name, email, password_hash, role)
        VALUES (?, ?, ?, ?)
    """, (full_name.strip(), email_clean, pass_hash, role))

    new_user_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return {'id': new_user_id, 'full_name': full_name.strip(), 'email': email_clean, 'role': role}


def get_user_by_email(db_path, email):
    """Retrieve user record by email address."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE LOWER(email) = ?", (email.strip().lower(),))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_by_id(db_path, user_id):
    """Retrieve user record by user ID."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def verify_user_credentials(db_path, email, password):
    """Verify email and password credentials with fallback for admin variants."""
    user = get_user_by_email(db_path, email)
    if not user:
        return None

    is_valid = check_password_hash(user['password_hash'], password)

    # Fallback for admin if password variant (with or without exclamation mark) is passed
    if not is_valid and user['email'].lower() == 'admin@skinsense.org':
        if password in ('Admin@SkinSense2026!', 'Admin@SkinSense2026'):
            is_valid = True
            try:
                conn = get_db_connection(db_path)
                conn.execute("UPDATE users SET password_hash = ? WHERE id = ?",
                             (generate_password_hash(password), user['id']))
                conn.commit()
                conn.close()
            except Exception:
                pass

    if is_valid:
        try:
            conn = get_db_connection(db_path)
            conn.execute("UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?", (user['id'],))
            conn.commit()
            conn.close()
        except Exception:
            pass
        return {
            'id': user['id'],
            'full_name': user['full_name'],
            'email': user['email'],
            'role': user['role'],
            'preferred_language': user.get('preferred_language', 'en')
        }
    return None


def update_user_preferred_language(db_path, user_id, lang):
    """Update preferred_language for user profile in DB."""
    if not user_id or not lang:
        return False
    try:
        conn = get_db_connection(db_path)
        conn.execute("UPDATE users SET preferred_language = ? WHERE id = ?", (lang.lower().strip(), user_id))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print("[DB] Error updating preferred_language: {}".format(e))
        return False


def delete_user_by_id(db_path, user_id):
    """Delete a user account and cascade delete their data. Cannot delete admin accounts."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT id, role, full_name, email FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return False, "User not found."
    user = dict(row)
    if user['role'] == 'admin':
        conn.close()
        return False, "Cannot delete administrator accounts."

    cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    return (affected > 0), "User {} deleted successfully.".format(user['full_name'])



# ────────────────────────────────────────────────
# ASSESSMENT CRUD
# ────────────────────────────────────────────────

def save_assessment(db_path, data, user_id=None):
    """Save a full assessment record with all v2.0 fields."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    fuzzy_exp_json = json.dumps(data.get('fuzzy_explanation', {})) if data.get('fuzzy_explanation') else None
    shap_json      = json.dumps(data.get('shap_explanation', {})) if data.get('shap_explanation') else None

    now_local = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    cursor.execute('''
        INSERT INTO assessments (
            id, user_id, image_filename, image_hash, body_region,
            predicted_class, predicted_name, model_score,
            model_uncertainty, uncertainty_std,
            top_predictions_json, quality_status, patient_name, patient_age,
            itching, pain, redness, duration_days, fever_level, burning_level,
            severity_score, severity_category, contributing_factors_json, clinical_summary,
            heatmap_filename, overlay_filename, explanation_method,
            fuzzy_explanation_json, shap_explanation_json,
            is_escalated, escalation_reason, created_at, model_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        data['id'],
        user_id or data.get('user_id'),
        data.get('image_filename', ''),
        data.get('image_hash'),
        data.get('body_region', ''),
        data.get('predicted_class', 'unknown'),
        data.get('predicted_name', 'Unclassified Condition'),
        data.get('model_score', 0.0),
        data.get('model_uncertainty'),
        data.get('uncertainty_std'),
        json.dumps(data.get('top_predictions', data.get('top_3_predictions', []))),
        data.get('quality_status', 'Optimal quality'),
        data.get('patient_name', 'Anonymous'),
        data.get('patient_age', 0),
        data.get('itching', 0),
        data.get('pain', 0),
        data.get('redness', 0),
        data.get('duration_days', 0),
        data.get('fever_level', 0),
        data.get('burning_level', 0),
        data.get('severity_score', 0.0),
        data.get('severity_category', 'Mild'),
        json.dumps(data.get('contributing_factors', [])),
        data.get('clinical_summary', ''),
        data.get('heatmap_filename'),
        data.get('overlay_filename'),
        data.get('explanation_method', 'Grad-CAM + MC Dropout + TTA'),
        fuzzy_exp_json,
        shap_json,
        1 if data.get('escalated_to_review') else 0,
        data.get('escalation_reason'),
        data.get('created_at') or now_local,
        data.get('model_id')
    ))
    conn.commit()
    conn.close()

    # Automatically add scan to review_queue so patient activity is immediately reflected in admin
    try:
        pred_class = (data.get('predicted_class') or '').lower()
        sev_cat    = data.get('severity_category', 'Mild')
        model_score = data.get('model_score', 0.0)

        priority = 'normal'
        reasons = []

        if pred_class == 'mel' and model_score >= 0.40:
            priority = 'urgent'
            reasons.append('Potential Melanoma flagged')
        elif pred_class in ('bcc', 'akiec', 'scc') and model_score >= 0.50:
            priority = 'high'
            reasons.append(f'Potential malignancy ({pred_class.upper()}) flagged')
        elif sev_cat == 'High':
            priority = 'high'
            reasons.append('High severity score')

        queue_reason = ' | '.join(reasons) if reasons else 'Patient skin scan submitted for clinical review'

        save_review_queue_item(db_path, {
            'assessment_id': data['id'],
            'patient_id': user_id or data.get('user_id'),
            'priority': priority,
            'queue_reason': queue_reason
        })
    except Exception as e:
        pass

    return data['id']


def get_assessment_by_id(db_path, assessment_id, user_id=None, is_admin=False):
    """Retrieve single assessment by ID, enforcing user ownership unless admin."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    if is_admin or not user_id:
        cursor.execute('SELECT * FROM assessments WHERE id = ?', (assessment_id,))
    else:
        cursor.execute('SELECT * FROM assessments WHERE id = ? AND user_id = ?', (assessment_id, user_id))

    row = cursor.fetchone()
    conn.close()
    if not row:
        return None

    item = dict(row)
    item['top_predictions']      = json.loads(item['top_predictions_json']) if item.get('top_predictions_json') else []
    item['contributing_factors'] = json.loads(item['contributing_factors_json']) if item.get('contributing_factors_json') else []
    item['fuzzy_explanation']    = json.loads(item['fuzzy_explanation_json']) if item.get('fuzzy_explanation_json') else None
    item['shap_explanation']     = json.loads(item['shap_explanation_json']) if item.get('shap_explanation_json') else None
    return item


def _clean_date_param(val):
    """Sanitize and parse date parameter string into YYYY-MM-DD format."""
    if not val:
        return None
    val_str = str(val).strip()
    if not val_str or val_str.lower() in ('null', 'undefined', 'none', ''):
        return None
    if 'T' in val_str:
        val_str = val_str.split('T')[0]
    elif ' ' in val_str:
        val_str = val_str.split(' ')[0]
    try:
        dt = datetime.strptime(val_str, '%Y-%m-%d')
        return dt.strftime('%Y-%m-%d')
    except ValueError:
        try:
            dt = datetime.fromisoformat(str(val).replace('Z', '+00:00'))
            return dt.strftime('%Y-%m-%d')
        except Exception:
            return None


def get_all_assessments(db_path, search_query=None, class_filter=None, user_id=None, is_admin=False, date_from=None, date_to=None):
    """Retrieve assessments filtered by user_id, search_query, class_filter, and date range unless admin."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    query = 'SELECT * FROM assessments WHERE 1=1'
    params = []

    if user_id and not is_admin:
        query += ' AND user_id = ?'
        params.append(user_id)

    if search_query and search_query.strip():
        query += ' AND (id LIKE ? OR patient_name LIKE ? OR predicted_name LIKE ?)'
        pattern = '%{}%'.format(search_query.strip())
        params.extend([pattern, pattern, pattern])

    if class_filter and class_filter.lower() != 'all':
        query += ' AND predicted_class = ?'
        params.append(class_filter)

    clean_from = _clean_date_param(date_from)
    if clean_from:
        query += ' AND (DATE(created_at) >= DATE(?) OR substr(created_at, 1, 10) >= ?)'
        params.extend([clean_from, clean_from])

    clean_to = _clean_date_param(date_to)
    if clean_to:
        query += ' AND (DATE(created_at) <= DATE(?) OR substr(created_at, 1, 10) <= ?)'
        params.extend([clean_to, clean_to])

    query += ' ORDER BY created_at DESC'
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    result = []
    for r in rows:
        item = dict(r)
        item['top_predictions']      = json.loads(item['top_predictions_json']) if item.get('top_predictions_json') else []
        item['contributing_factors'] = json.loads(item['contributing_factors_json']) if item.get('contributing_factors_json') else []
        item['fuzzy_explanation']    = json.loads(item['fuzzy_explanation_json']) if item.get('fuzzy_explanation_json') else None
        result.append(item)
    return result


def delete_assessment_by_id(db_path, assessment_id, user_id=None, is_admin=False):
    """Delete an assessment by ID enforcing user ownership."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    if is_admin or not user_id:
        cursor.execute('DELETE FROM assessments WHERE id = ?', (assessment_id,))
    else:
        cursor.execute('DELETE FROM assessments WHERE id = ? AND user_id = ?', (assessment_id, user_id))

    affected = cursor.rowcount
    conn.commit()
    conn.close()
    return affected > 0


# ────────────────────────────────────────────────
# CONVERSATION / CHAT
# ────────────────────────────────────────────────

def save_chat_message(db_path, conversation_id, role, content, assessment_id=None, image_attached=None, user_id=None):
    """Save a chat message associated with a user."""
    conn = get_db_connection(db_path)
    conn.execute('''
        INSERT INTO conversation_messages (user_id, conversation_id, assessment_id, role, content, image_attached)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (user_id, conversation_id, assessment_id, role, content, image_attached))
    conn.commit()
    conn.close()


def get_chat_history(db_path, conversation_id, user_id=None, is_admin=False):
    """Retrieve chat history enforcing user ownership."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    if is_admin or not user_id:
        cursor.execute('''
            SELECT * FROM conversation_messages WHERE conversation_id = ?
            ORDER BY timestamp ASC
        ''', (conversation_id,))
    else:
        cursor.execute('''
            SELECT * FROM conversation_messages WHERE conversation_id = ? AND user_id = ?
            ORDER BY timestamp ASC
        ''', (conversation_id, user_id))

    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ────────────────────────────────────────────────
# ANALYTICS
# ────────────────────────────────────────────────

def get_model_prediction_distribution(db_path, model_service):
    """Count assessments attributed to the active checkpoint by its current labels."""
    if model_service is None:
        return []

    conn = get_db_connection(db_path)
    counts = dict(conn.execute(
        'SELECT predicted_class, COUNT(*) FROM assessments WHERE model_id = ? GROUP BY predicted_class',
        (model_service.MODEL_ID,)
    ).fetchall())
    conn.close()
    classes = [
        {'code': code, 'name': model_service.class_labels[code]['name'], 'count': counts.get(code, 0)}
        for code in model_service.config['classes']
    ]
    if 'unclassified' in counts:
        classes.append({'code': 'unclassified', 'name': 'Inconclusive', 'count': counts['unclassified']})
    return classes


def get_live_prediction_distribution(db_path):
    """Calculate live class distribution from stored assessments."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT predicted_class, predicted_name, COUNT(*) as count
        FROM assessments GROUP BY predicted_class, predicted_name
    ''')
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ────────────────────────────────────────────────
# DERMATOLOGIST REVIEW QUEUE
# ────────────────────────────────────────────────

def save_review_queue_item(db_path, data):
    """Add an assessment to the dermatologist review queue."""
    conn = get_db_connection(db_path)
    try:
        with conn:
            conn.execute('BEGIN IMMEDIATE')
            assessment = conn.execute('''
                SELECT user_id, review_queue_dismissed FROM assessments WHERE id = ?
            ''', (data['assessment_id'],)).fetchone()
            if not assessment or assessment['review_queue_dismissed'] or not assessment['user_id']:
                return False

            existing = conn.execute('''
                SELECT id, priority, status FROM active_review_queue WHERE assessment_id = ?
            ''', (data['assessment_id'],)).fetchone()
            priority = data.get('priority', 'normal')
            reason = data.get('queue_reason', '')
            if existing:
                ranks = {'low': 0, 'normal': 1, 'high': 2, 'urgent': 3}
                if existing['status'] == 'pending' and ranks[priority] >= ranks[existing['priority']]:
                    conn.execute('UPDATE review_queue SET priority = ?, queue_reason = ? WHERE id = ?',
                                 (priority, reason, existing['id']))
            else:
                conn.execute('''
                    INSERT INTO review_queue (assessment_id, patient_id, priority, queue_reason, created_at)
                    VALUES (?, ?, ?, ?, ?)
                ''', (data['assessment_id'], assessment['user_id'], priority, reason,
                      data.get('created_at') or datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
            return True
    finally:
        conn.close()


def sync_all_assessments_to_review_queue(db_path):
    """Backfill older owned assessments that have never entered the queue."""
    conn = get_db_connection(db_path)
    try:
        with conn:
            conn.execute('''
                INSERT INTO review_queue (assessment_id, patient_id, priority, queue_reason, created_at)
                SELECT a.id, a.user_id,
                    CASE
                        WHEN a.predicted_class = 'mel' AND a.model_score >= 0.40 THEN 'urgent'
                        WHEN a.predicted_class IN ('bcc', 'akiec', 'scc') AND a.model_score >= 0.50 THEN 'high'
                        WHEN a.severity_category = 'High' THEN 'high'
                        ELSE 'normal'
                    END,
                    CASE
                        WHEN a.predicted_class = 'mel' AND a.model_score >= 0.40 THEN 'Potential Melanoma flagged'
                        WHEN a.predicted_class IN ('bcc', 'akiec', 'scc') AND a.model_score >= 0.50
                            THEN 'Potential malignancy (' || UPPER(a.predicted_class) || ') flagged'
                        WHEN a.severity_category = 'High' THEN 'High severity score'
                        ELSE 'Patient skin scan submitted'
                    END,
                    COALESCE(a.created_at, CURRENT_TIMESTAMP)
                FROM assessments a
                JOIN users u ON u.id = a.user_id
                WHERE a.review_queue_dismissed = 0
                  AND NOT EXISTS (SELECT 1 FROM review_queue rq WHERE rq.assessment_id = a.id)
            ''')
    finally:
        conn.close()


def get_review_queue(db_path, status=None, priority=None, patient_id=None, limit=500):
    """Get review cases in priority order for existing callers."""
    return get_review_queue_page(db_path, status, priority, patient_id, limit)['items']


def get_review_queue_page(db_path, status=None, priority=None, patient_id=None,
                          limit=50, offset=0, search=None, newest_first=False):
    """Return a filtered page and counts without hiding newer reports."""
    sync_all_assessments_to_review_queue(db_path)
    source = '''
        FROM active_review_queue rq
        JOIN assessments a ON rq.assessment_id = a.id
        WHERE 1=1
    '''
    params = []
    if status:
        source += ' AND rq.status = ?'
        params.append(status)
    if priority:
        source += ' AND rq.priority = ?'
        params.append(priority)
    if patient_id:
        source += ' AND rq.patient_id = ?'
        params.append(patient_id)
    if search:
        source += ''' AND (
            INSTR(LOWER(COALESCE(a.patient_name, '')), ?) > 0
            OR INSTR(LOWER(COALESCE(a.predicted_name, '')), ?) > 0
            OR INSTR(LOWER(rq.assessment_id), ?) > 0
            OR INSTR(CAST(rq.id AS TEXT), ?) > 0
        )'''
        params.extend([search.strip().lower()] * 4)

    query = '''
        SELECT rq.*, a.predicted_name, a.predicted_class, a.model_score, a.model_id,
               a.severity_category, a.severity_score, a.patient_name, a.patient_age,
               a.heatmap_filename, a.created_at as assessment_date
    ''' + source
    if newest_first:
        query += ' ORDER BY datetime(a.created_at) DESC, rq.id DESC'
    else:
        query += ''' ORDER BY CASE rq.priority
            WHEN 'urgent' THEN 1 WHEN 'high' THEN 2 WHEN 'normal' THEN 3 ELSE 4 END,
            datetime(a.created_at) ASC, rq.id ASC'''
    query += ' LIMIT ? OFFSET ?'

    conn = get_db_connection(db_path)
    try:
        total = conn.execute('SELECT COUNT(*) ' + source, params).fetchone()[0]
        pending = conn.execute("SELECT COUNT(*) FROM active_review_queue WHERE status = 'pending'").fetchone()[0]
        rows = conn.execute(query, [*params, limit, offset]).fetchall()
        return {'items': [dict(row) for row in rows], 'total_count': total, 'pending_count': pending}
    finally:
        conn.close()


def get_review_item_by_id(db_path, queue_id):
    """Get a single review queue item with full assessment data."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT rq.*, a.* FROM active_review_queue rq
        JOIN assessments a ON rq.assessment_id = a.id
        WHERE rq.id = ?
    ''', (queue_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    item = dict(row)
    item['top_predictions'] = json.loads(item['top_predictions_json']) if item.get('top_predictions_json') else []
    return item


def update_review_verdict(db_path, queue_id, data):
    """Submit a dermatologist verdict on a review queue item."""
    status_map = {'completed': 'reviewed', 'rejected': 'closed', 'in_review': 'escalated', 'pending': 'pending'}
    status = data.get('status', 'completed')
    now_local = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    conn = get_db_connection(db_path)
    try:
        with conn:
            conn.execute('BEGIN IMMEDIATE')
            row = conn.execute('''
                SELECT id, assessment_id FROM active_review_queue WHERE id = ? OR assessment_id = ?
            ''', (queue_id, queue_id)).fetchone()
            if not row:
                return False

            derm_id = data.get('assigned_derm_id')
            if not conn.execute('SELECT 1 FROM users WHERE id = ?', (derm_id,)).fetchone():
                derm_id = None
            verdict = data.get('derm_verdict', '')
            notes = data.get('derm_notes', '')
            conn.execute('''
                UPDATE review_queue SET status = ?, derm_verdict = ?, derm_notes = ?,
                    assigned_derm_id = ?, completed_at = ?, verdict_category = ?
                WHERE id = ?
            ''', (status, verdict, notes, derm_id, now_local if status in ('completed', 'rejected') else None,
                  data.get('verdict_category'), row['id']))
            conn.execute('''
                UPDATE assessments SET review_status = ?, dermatologist_id = ?,
                    dermatologist_notes = ?, dermatologist_diagnosis = ?
                WHERE id = ?
            ''', (status_map[status], derm_id, notes, verdict, row['assessment_id']))
            return True
    finally:
        conn.close()


# ────────────────────────────────────────────────
# LONGITUDINAL LESION TRACKING
# ────────────────────────────────────────────────

def create_lesion_track(db_path, user_id, track_name, body_region='', notes=''):
    """Create a new lesion monitoring track for a user."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO lesion_tracks (user_id, track_name, body_region, notes)
        VALUES (?, ?, ?, ?)
    ''', (user_id, track_name, body_region, notes))
    track_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return {'id': track_id, 'track_name': track_name, 'body_region': body_region, 'notes': notes}


def get_lesion_tracks_for_user(db_path, user_id):
    """Get all active lesion tracks for a user."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT lt.*, COUNT(DISTINCT a.id) as assessment_count
        FROM lesion_tracks lt
        LEFT JOIN lesion_track_assessments lta ON lt.id = lta.track_id
        LEFT JOIN assessments a ON a.id = lta.assessment_id AND a.user_id = lt.user_id
        WHERE lt.user_id = ? AND lt.is_active = 1
        GROUP BY lt.id
        ORDER BY lt.last_updated DESC
    ''', (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_lesion_track_by_id(db_path, track_id, user_id=None):
    """Get a single lesion track, enforcing ownership."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    if user_id:
        cursor.execute('SELECT * FROM lesion_tracks WHERE id = ? AND user_id = ? AND is_active = 1', (track_id, user_id))
    else:
        cursor.execute('SELECT * FROM lesion_tracks WHERE id = ?', (track_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def add_assessment_to_track(db_path, track_id, assessment_id, user_id, change_notes=''):
    """Link a patient's own assessment to their active track once."""
    conn = get_db_connection(db_path)
    try:
        with conn:
            conn.execute('BEGIN IMMEDIATE')
            owned = conn.execute('''
                SELECT 1 FROM lesion_tracks lt
                JOIN assessments a ON a.user_id = lt.user_id
                WHERE lt.id = ? AND lt.user_id = ? AND lt.is_active = 1 AND a.id = ?
            ''', (track_id, user_id, assessment_id)).fetchone()
            if not owned:
                return False

            linked = conn.execute(
                'SELECT 1 FROM lesion_track_assessments WHERE track_id = ? AND assessment_id = ?',
                (track_id, assessment_id)
            ).fetchone()
            if linked:
                return True

            conn.execute('''
                INSERT INTO lesion_track_assessments (track_id, assessment_id, order_index, change_notes)
                SELECT ?, ?, COALESCE(MAX(order_index), 0) + 1, ?
                FROM lesion_track_assessments WHERE track_id = ?
            ''', (track_id, assessment_id, change_notes, track_id))
            conn.execute('UPDATE lesion_tracks SET last_updated = CURRENT_TIMESTAMP WHERE id = ?', (track_id,))
            return True
    finally:
        conn.close()


def get_track_assessments(db_path, track_id):
    """Get all assessments linked to a lesion track in chronological order."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT a.*, lta.order_index, lta.change_notes, lta.created_at as linked_at
        FROM lesion_track_assessments lta
        JOIN lesion_tracks lt ON lt.id = lta.track_id
        JOIN assessments a ON a.id = lta.assessment_id AND a.user_id = lt.user_id
        WHERE lta.track_id = ?
        GROUP BY a.id
        ORDER BY datetime(a.created_at) ASC, MIN(lta.order_index) ASC
    ''', (track_id,))
    rows = cursor.fetchall()
    conn.close()
    result = []
    for r in rows:
        item = dict(r)
        item['top_predictions'] = json.loads(item['top_predictions_json']) if item.get('top_predictions_json') else []
        result.append(item)
    return result


def delete_lesion_track(db_path, track_id, user_id):
    """Soft-delete a lesion track (sets is_active=0)."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute('UPDATE lesion_tracks SET is_active = 0 WHERE id = ? AND user_id = ?', (track_id, user_id))
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    return affected > 0


# ────────────────────────────────────────────────
# MEDICAL KNOWLEDGE BASE & HOME CARE
# ────────────────────────────────────────────────

SEED_KNOWLEDGE_BASE = [
    {
        "condition_code": "nv",
        "condition_name": "Melanocytic Nevi (Common Mole)",
        "category": "Benign",
        "risk_level": "Low",
        "prevalence": "Very common (10-40 moles per adult)",
        "description": "Common benign proliferation of pigment-producing melanocyte cells. Generally harmless skin spots.",
        "common_symptoms": ["Uniform brown or black color", "Smooth well-defined border", "Round or oval shape", "Stable appearance over years"],
        "supportive_care": [
            "Keep the skin gently clean with mild, fragrance-free soap.",
            "Apply broad-spectrum sunscreen (SPF 30+) to prevent sun-induced cellular damage.",
            "Moisturize skin daily to maintain the protective skin barrier."
        ],
        "preventive_measures": [
            "Perform monthly self-skin examinations using the ABCDE rule.",
            "Avoid excessive UV exposure during peak hours (10 AM - 4 PM).",
            "Wear protective clothing, broad-brimmed hats, and UV-blocking sunglasses."
        ],
        "things_to_avoid": [
            "Do NOT scratch, pick, or cut at moles.",
            "Do NOT apply harsh chemical home remedies (lemon juice, vinegar, garlic, or bleach).",
            "Do NOT attempt home mole removal using unverified internet kits.",
            "Do NOT use unauthorized prescription creams without medical advice."
        ],
        "when_to_see_doctor": [
            "A mole changes in size, shape, or color.",
            "New moles appear after age 30.",
            "You have more than 50 moles or a personal/family history of skin cancer."
        ],
        "urgent_warning_signs": [
            "ABCDE warning signs (Asymmetry, Border irregularity, Color variation, Diameter > 6mm, Evolving).",
            "Spontaneous bleeding, oozing, or ulceration of a mole."
        ],
        "medical_treatment_info": "Supportive care does NOT treat or remove moles. Medical removal requires clinical excision or shave biopsy by a board-certified dermatologist.",
        "references": [
            {"source": "American Academy of Dermatology (AAD)", "title": "Moles: Overview and Self-Examination", "url": "https://www.aad.org/public/diseases/a-z/moles-overview"},
            {"source": "Skin Cancer Foundation", "title": "Do You Know Your Moles?", "url": "https://www.skincancer.org/skin-cancer-information/moles/"}
        ],
        "translations": {
            "hi": {
                "condition_name": "मेलेनोसाइटिक नेवी (सामान्य तिल)",
                "description": "त्वचा में पिगमेंट बनाने वाली कोशिकाओं का सामान्य हानिरहित उभार।",
                "supportive_care": ["त्वचा को माइल्ड सोप से साफ रखें।", "धूप से बचाव के लिए SPF 30+ सनस्क्रीन लगाएं।", "त्वचा को नियमित रूप से मॉइस्चराइज़ करें।"],
                "things_to_avoid": ["तिल को खरोंचें या काटें नहीं।", "नींबू, सिरका या ब्लीच जैसे घरेलू रसायनों का इस्तेमाल न करें।"]
            },
            "mr": {
                "condition_name": "मेलेनोसायटिक नेव्ही (साधारण तीळ)",
                "description": "त्वचेवरील रंगपेशींची सर्वसामान्य व बिनधोक वाढ.",
                "supportive_care": ["त्वचा सौम्य साबणाने स्वच्छ ठेवा.", "सूर्यप्रकाशापासून संरक्षणासाठी SPF 30+ सनस्क्रीन वापरा.", "त्वचा नेहमी मॉइश्चराइज ठेवा."],
                "things_to_avoid": ["तिळाला खाजवू किंवा काढण्याचा प्रयत्न करू नका.", "लिंबू, व्हिनेगर किंवा ब्लीच वापरू नका."]
            }
        },
        "version": "1.0",
        "last_reviewed": "2026-10-01",
        "status": "approved"
    },
    {
        "condition_code": "mel",
        "condition_name": "Melanoma",
        "category": "Malignant",
        "risk_level": "High",
        "prevalence": "1 in 38 lifetime risk",
        "description": "Serious form of skin cancer arising in melanocyte cells. Highly treatable when caught early.",
        "common_symptoms": ["Asymmetric shape", "Irregular or scalloped borders", "Varied colors (black, brown, red, blue)", "Evolving size, shape, or texture"],
        "supportive_care": [
            "Keep the affected skin clean, dry, and protected from friction.",
            "Protect the lesion from sun exposure with physical shade and loose protective clothing.",
            "Maintain general skin hydration with fragrance-free emollients on non-ulcerated skin."
        ],
        "preventive_measures": [
            "Strict daily UV protection (SPF 30+ broad-spectrum sunscreen).",
            "Avoid tanning beds and intense sun exposure.",
            "Perform monthly full-body skin checks."
        ],
        "things_to_avoid": [
            "Do NOT delay seeking urgent professional medical evaluation.",
            "Do NOT apply household remedies (essential oils, baking soda, toothpaste, or acids).",
            "Do NOT scratch, squeeze, or attempt to cut or pick the lesion.",
            "Do NOT rely on home care as a cure or alternative to clinical treatment."
        ],
        "when_to_see_doctor": [
            "URGENT: Any mole or skin spot showing ABCDE changes requires immediate dermatologist evaluation.",
            "Any new rapidly growing spot on sun-exposed or non-exposed skin."
        ],
        "urgent_warning_signs": [
            "Rapid expansion, color change, bleeding, or ulceration.",
            "Hard swollen lymph nodes near the affected area."
        ],
        "medical_treatment_info": "Supportive home care cannot treat melanoma. Medical treatment requires surgical excision, sentinel lymph node biopsy, immunotherapy, or targeted therapy.",
        "references": [
            {"source": "National Cancer Institute (NCI)", "title": "Melanoma Treatment & Patient Guidance", "url": "https://www.cancer.gov/types/skin/patient/melanoma-treatment-pdq"},
            {"source": "American Cancer Society (ACS)", "title": "Melanoma Early Detection", "url": "https://www.cancer.org/cancer/melanoma-skin-cancer.html"}
        ],
        "translations": {
            "hi": {
                "condition_name": "मेलेनोमा (त्वचा कैंसर)",
                "description": "त्वचा की पिगमेंट कोशिकाओं का गंभीर रूप, जिसका तुरंत इलाज आवश्यक है।",
                "supportive_care": ["प्रभावित क्षेत्र को साफ और सूखा रखें।", "त्वचा को धूप से बचाएं।"],
                "things_to_avoid": ["डॉक्टर को दिखाने में बिल्कुल देरी न करें।", "किसी भी घरेलू नुस्खे पर निर्भर न रहें।"]
            },
            "mr": {
                "condition_name": "मेलानोमा (त्वचेचा कर्करोग)",
                "description": "त्वचेचा गंभीर आजार, ज्यावर तातडीने वैद्यकीय उपचारांची गरज असते.",
                "supportive_care": ["त्वचा स्वच्छ आणि कोरडी ठेवा.", "उन्हापासून बचाव करा."],
                "things_to_avoid": ["डॉक्टरांचा सल्ला घेण्यास उशीर करू नका.", "घरगुती उपायांवर अवलंबून राहू नका."]
            }
        },
        "version": "1.0",
        "last_reviewed": "2026-10-01",
        "status": "approved"
    },
    {
        "condition_code": "bcc",
        "condition_name": "Basal Cell Carcinoma",
        "category": "Malignant",
        "risk_level": "High",
        "prevalence": "Most common skin cancer (3.6M cases/yr)",
        "description": "Common non-melanoma skin cancer arising in basal cells. Rarely spreads to organs but can cause local tissue damage.",
        "common_symptoms": ["Pearly or waxy bump with visible tiny blood vessels", "Bleeding sore that heals and returns", "Flat scar-like firm patch"],
        "supportive_care": [
            "Clean the area gently with warm water and mild soap.",
            "Protect the lesion from sun exposure with wide-brimmed hats and SPF 30+ sunscreen.",
            "Apply a clean sterile dressing if minor oozing occurs while waiting for your appointment."
        ],
        "preventive_measures": [
            "Use broad-spectrum sunscreen daily.",
            "Reapply sunscreen every 2 hours outdoors.",
            "Schedule annual professional skin checks."
        ],
        "things_to_avoid": [
            "Do NOT pick, scratch, or try to pop the pearly lesion.",
            "Do NOT apply caustic substances (lemon juice, vinegar, or harsh ointments).",
            "Do NOT ignore non-healing sores on sun-damaged skin."
        ],
        "when_to_see_doctor": [
            "Schedule a medical evaluation with a board-certified dermatologist for sores that do not heal within 3 to 4 weeks.",
            "Consult a dermatologist if pearly bumps or scaly patches bleed repeatedly."
        ],
        "urgent_warning_signs": [
            "Rapid expansion, severe pain, or signs of secondary skin infection (pus, warmth, severe redness)."
        ],
        "medical_treatment_info": "Supportive care does NOT cure BCC. Clinical treatments include Mohs micrographic surgery, excisions, or topical prescription therapies.",
        "references": [
            {"source": "Skin Cancer Foundation", "title": "Basal Cell Carcinoma Overview", "url": "https://www.skincancer.org/skin-cancer-information/basal-cell-carcinoma/"}
        ],
        "translations": {
            "hi": {
                "condition_name": "बेसल सेल कार्सिनोमा",
                "description": "त्वचा का सबसे सामान्य कैंसर जो धीरे-धीरे बढ़ता है।",
                "supportive_care": ["त्वचा को साफ रखें और धूप से बचाएं।"],
                "things_to_avoid": ["घाव को खरोंचें नहीं।", "घरेलू नुस्खे न आजमाएं।"]
            },
            "mr": {
                "condition_name": "बेसल सेल कार्सिनोमा",
                "description": "त्वचेचा अत्यंत सामान्य कर्करोग प्रकार.",
                "supportive_care": ["त्वचा स्वच्छ ठेवा व उन्हापासून जपा."],
                "things_to_avoid": ["खरुज काढण्याचा प्रयत्न करू नका."]
            }
        },
        "version": "1.0",
        "last_reviewed": "2026-10-01",
        "status": "approved"
    },
    {
        "condition_code": "akiec",
        "condition_name": "Actinic Keratosis / Intraepithelial Carcinoma",
        "category": "Pre-cancerous",
        "risk_level": "Moderate",
        "prevalence": "Affects 58M Americans",
        "description": "Pre-cancerous rough, scaly patch caused by cumulative UV radiation. Can progress to squamous cell carcinoma if untreated.",
        "common_symptoms": ["Rough dry scaly patch", "Sandpaper-like skin texture", "Mild itching or tenderness"],
        "supportive_care": [
            "Keep skin hydrated with thick fragrance-free moisturizers or plain petroleum jelly.",
            "Clean gently with mild non-soap cleansers.",
            "Protect sun-damaged skin with broad-spectrum SPF 50+ sunscreen."
        ],
        "preventive_measures": [
            "Wear protective sun clothing and broad-brimmed hats outdoors.",
            "Avoid mid-day sun exposure.",
            "Examine sun-damaged skin monthly for new rough spots."
        ],
        "things_to_avoid": [
            "Do NOT scrub rough spots aggressively with loofahs or harsh scrubs.",
            "Do NOT apply acids, vinegar, or unapproved peeling chemical agents.",
            "Do NOT pick off crusty patches."
        ],
        "when_to_see_doctor": [
            "Schedule a medical evaluation with a board-certified dermatologist for rough scaly patches that persist or grow thicker.",
            "Consult a physician if patches become tender, inflamed, or bleed."
        ],
        "urgent_warning_signs": [
            "Rapid thickening, raised firm red nodule, or ulceration (possible progression to SCC)."
        ],
        "medical_treatment_info": "Home care supports the skin barrier. Clinical treatments include cryotherapy (liquid nitrogen), prescription topical 5-FU/imiquimod creams, or photodynamic therapy.",
        "references": [
            {"source": "American Academy of Dermatology", "title": "Actinic Keratosis Care Guide", "url": "https://www.aad.org/public/diseases/a-z/actinic-keratosis-overview"}
        ],
        "translations": {
            "hi": {
                "condition_name": "एक्टिनिक केराटोसिस (प्री-कैंसर पैच)",
                "description": "धूप के कारण होने वाला खुरदुरा पैच जो आगे चलकर कैंसर बन सकता है।",
                "supportive_care": ["त्वचा को मॉइस्चराइज़ रखें और SPF 50+ सनस्क्रीन लगाएं।"],
                "things_to_avoid": ["खुरदुरी त्वचा को ज़ोर से न रगड़ें।"]
            },
            "mr": {
                "condition_name": "ॲक्टिनिक केराटोसीस",
                "description": "उन्हामुळे होणारा खरबरीत डाग.",
                "supportive_care": ["त्वचेला मॉइश्चरायझर लावा व उन्हापासून वाचवा."],
                "things_to_avoid": ["त्वचा जोरात घासणे टाळा."]
            }
        },
        "version": "1.0",
        "last_reviewed": "2026-10-01",
        "status": "approved"
    },
    {
        "condition_code": "bkl",
        "condition_name": "Benign Keratosis-like Lesions",
        "category": "Benign",
        "risk_level": "Low",
        "prevalence": "Very common in adults > 50",
        "description": "Non-cancerous growths including seborrheic keratoses (waxy stuck-on spots) and solar lentigines (age spots). Harmless.",
        "common_symptoms": ["Waxy or stuck-on appearance", "Tan, brown, or black color", "Sharply defined borders"],
        "supportive_care": [
            "Clean skin gently with mild body wash.",
            "Apply moisturizers to soften rough waxy buildup.",
            "Wear sunscreen to prevent additional solar lentigines (sun spots)."
        ],
        "preventive_measures": [
            "Daily sun protection with broad-spectrum SPF 30+.",
            "Avoid mechanical irritation from tight clothing or jewelry straps."
        ],
        "things_to_avoid": [
            "Do NOT pick, scratch, or try to scrape off stuck-on spots.",
            "Do NOT apply wart removers, acids, or bleach to benign skin spots.",
            "Do NOT use home cryo kits without professional guidance."
        ],
        "when_to_see_doctor": [
            "Spot bleeds unexpectedly or becomes painful due to friction.",
            "Spot changes rapidly or looks atypical compared to surrounding spots."
        ],
        "urgent_warning_signs": [
            "Rapid onset of multiple dark irregular spots (Leser-Trélat sign) or spontaneous bleeding."
        ],
        "medical_treatment_info": "Supportive home care maintains skin comfort. Cosmetic removal, if desired, is performed clinically via cryotherapy, shave excision, or laser therapy.",
        "references": [
            {"source": "Mayo Clinic", "title": "Seborrheic Keratosis Symptoms & Care", "url": "https://www.mayoclinic.org/diseases-conditions/seborrheic-keratosis/symptoms-causes/syc-20353878"}
        ],
        "translations": {
            "hi": {
                "condition_name": "सौम्य केराटोसिस (उम्र के धब्बे)",
                "description": "उम्र के साथ त्वचा पर होने वाले सामान्य हानिरहित धब्बे।",
                "supportive_care": ["त्वचा को मॉइस्चराइज़ करें और साफ रखें।"],
                "things_to_avoid": ["धब्बों को खुरचने की कोशिश न करें।"]
            },
            "mr": {
                "condition_name": "बिनाइन केराटोसीस",
                "description": "वयानुसार येणारे बिनधोक डाग.",
                "supportive_care": ["त्वचा स्वच्छ आणि ओलसर ठेवा."],
                "things_to_avoid": ["डाग कोरडण्याचा प्रयत्न करू नका."]
            }
        },
        "version": "1.0",
        "last_reviewed": "2026-10-01",
        "status": "approved"
    },
    {
        "condition_code": "df",
        "condition_name": "Dermatofibroma",
        "category": "Benign",
        "risk_level": "Low",
        "prevalence": "Common (frequent in women)",
        "description": "Benign firm skin nodule composed of fibrous tissue, often occurring on lower legs following minor injury or insect bite.",
        "common_symptoms": ["Firm reddish-brown dome-shaped bump", "Dimple sign (depresses inward when pinched)", "Usually asymptomatic"],
        "supportive_care": [
            "Keep the skin area clean and moisturized.",
            "Protect leg skin from minor cuts or insect bites.",
            "Avoid tight socks or straps that press directly against the bump."
        ],
        "preventive_measures": [
            "Use bug spray to prevent insect bites on legs.",
            "Avoid scratching minor leg wounds."
        ],
        "things_to_avoid": [
            "Do NOT attempt to cut out or squeeze the firm nodule.",
            "Do NOT apply irritating chemical remedies or acids.",
            "Do NOT scratch or rub the bump constantly."
        ],
        "when_to_see_doctor": [
            "The nodule grows rapidly, bleeds, or becomes painful.",
            "You are unsure if the nodule is a dermatofibroma."
        ],
        "urgent_warning_signs": [
            "Rapid enlargement, open ulceration, or severe local infection signs."
        ],
        "medical_treatment_info": "Supportive care ensures skin comfort. Clinical removal requires surgical excision if tender or cosmetically desired.",
        "references": [
            {"source": "DermNet NZ", "title": "Dermatofibroma Clinical Feature & Management", "url": "https://dermnetnz.org/topics/dermatofibroma"}
        ],
        "translations": {
            "hi": {
                "condition_name": "डर्माटोफाइब्रोमा (सख्त गांठ)",
                "description": "त्वचा के नीचे फाइबर ऊतकों की छोटी हानिरहित सख्त गांठ।",
                "supportive_care": ["त्वचा को साफ रखें और खरोंच से बचाएं।"],
                "things_to_avoid": ["गांठ को दबाएं या काटने की कोशिश न करें।"]
            },
            "mr": {
                "condition_name": "डर्माटोफायब्रोमा",
                "description": "त्वचेखालील लहान कडक गाठ.",
                "supportive_care": ["त्वचा स्वच्छ ठेवा."],
                "things_to_avoid": ["गाठ दाबण्याचा प्रयत्न करू नका."]
            }
        },
        "version": "1.0",
        "last_reviewed": "2026-10-01",
        "status": "approved"
    },
    {
        "condition_code": "vasc",
        "condition_name": "Vascular Lesions",
        "category": "Vascular",
        "risk_level": "Moderate",
        "prevalence": "Common (Cherry angiomas in 75%+ adults > 30)",
        "description": "Benign proliferations of blood vessels (cherry angiomas, angiokeratomas, pyogenic granulomas).",
        "common_symptoms": ["Bright red or purple dome papule", "Easily bleeds if bumped (pyogenic granuloma)", "Smooth surface"],
        "supportive_care": [
            "Keep the area clean and protect from accidental bumps or scratches.",
            "If minor bleeding occurs from a bump, apply firm, gentle pressure with a clean sterile gauze for 5-10 minutes.",
            "Keep skin moisturized with gentle emollients."
        ],
        "preventive_measures": [
            "Avoid aggressive scrubbing over blood vessel spots.",
            "Protect vulnerable spots from friction or injury."
        ],
        "things_to_avoid": [
            "Do NOT pick, needle, or puncture red vascular spots.",
            "Do NOT apply astringents, alcohol, or caustic chemicals.",
            "Do NOT leave active bleeding uncompressed."
        ],
        "when_to_see_doctor": [
            "A vascular lesion bleeds frequently or rapidly expands (pyogenic granuloma).",
            "Multiple new dark purple lesions appear suddenly."
        ],
        "urgent_warning_signs": [
            "Heavy bleeding that does not stop after 15 minutes of firm direct pressure.",
            "Rapidly growing vascular growth with surrounding dark purple discoloration."
        ],
        "medical_treatment_info": "Supportive home care manages clean protection. Clinical treatments include laser ablation, electrocautery, or shave excision.",
        "references": [
            {"source": "American Academy of Dermatology", "title": "Vascular Skin Lesions Guide", "url": "https://www.aad.org/public/diseases/a-z/cherry-angioma"}
        ],
        "translations": {
            "hi": {
                "condition_name": "वैस्कुलर लीजन (लाल रक्त वाहिका स्पॉट)",
                "description": "त्वचा की रक्त वाहिकाओं का लाल या बैंगनी धब्बा।",
                "supportive_care": ["रक्तस्राव होने पर साफ कपड़े से 5 मिनट दबाएं।"],
                "things_to_avoid": ["लाल धब्बों को सुई या नाखून से न फोड़ें।"]
            },
            "mr": {
                "condition_name": "व्हॅस्कुलर लीजन",
                "description": "रक्तवाहिन्यांचे लाल किंवा जांभळे डाग.",
                "supportive_care": ["रक्त आल्यास स्वच्छ कपड्याने दाबून धरा."],
                "things_to_avoid": ["डाग फोडण्याचा प्रयत्न करू नका."]
            }
        },
        "version": "1.0",
        "last_reviewed": "2026-10-01",
        "status": "approved"
    },
    {
        "condition_code": "scc",
        "condition_name": "Squamous Cell Carcinoma",
        "category": "Malignant",
        "risk_level": "High",
        "prevalence": "2nd most common skin cancer (1M cases/yr)",
        "description": "Malignant skin cancer arising from squamous epithelial cells. Potential to metastasize if left untreated.",
        "common_symptoms": ["Firm red nodule", "Scaly crusted flat sore", "Open sore that bleeds and fails to heal"],
        "supportive_care": [
            "Keep the affected sore clean with warm water and mild cleanser.",
            "Cover open lesions with sterile non-stick bandages.",
            "Strictly protect the lesion from sun exposure with hats, clothing, and broad-spectrum sunscreen."
        ],
        "preventive_measures": [
            "Daily SPF 30+ broad-spectrum sun protection.",
            "Treat pre-cancerous actinic keratoses early.",
            "Wear UV protective headwear and clothing."
        ],
        "things_to_avoid": [
            "Do NOT delay seeking urgent medical evaluation.",
            "Do NOT apply household remedies, essential oils, or unverified ointments.",
            "Do NOT pick off crusted sores or scratch lesions."
        ],
        "when_to_see_doctor": [
            "URGENT: Any scaly sore, firm red nodule, or non-healing skin lesion requires prompt dermatologist evaluation."
        ],
        "urgent_warning_signs": [
            "Rapidly expanding ulcer, severe local pain, or swollen regional lymph nodes."
        ],
        "medical_treatment_info": "Home care cannot treat SCC. Clinical evaluation requires Mohs micrographic surgery, surgical excision, or systemic radiation/immunotherapy.",
        "references": [
            {"source": "Skin Cancer Foundation", "title": "Squamous Cell Carcinoma Information", "url": "https://www.skincancer.org/skin-cancer-information/squamous-cell-carcinoma/"}
        ],
        "translations": {
            "hi": {
                "condition_name": "स्क्वैमस सेल कार्सिनोमा",
                "description": "त्वचा कैंसर का दूसरा सबसे सामान्य प्रकार, जिसका इलाज जरूरी है।",
                "supportive_care": ["घाव को साफ पट्टी से ढककर रखें और धूप से बचाएं।"],
                "things_to_avoid": ["डॉक्टर से जांच कराने में देरी न करें।"]
            },
            "mr": {
                "condition_name": "स्क्वॅमस सेल कार्सिनोमा",
                "description": "त्वचेच्या कर्करोगाचा प्रकार, वैद्यकीय उपचारांची तातडीची गरज.",
                "supportive_care": ["जखम स्वच्छ ठेवा व झाकून ठेवा."],
                "things_to_avoid": ["डॉक्टरांकडे जाण्यास विलंब करू नका."]
            }
        },
        "version": "1.0",
        "last_reviewed": "2026-10-01",
        "status": "approved"
    },
    {
        "condition_code": "psoriasis",
        "condition_name": "Psoriasis",
        "category": "Inflammatory",
        "risk_level": "Moderate",
        "prevalence": "Affects 2-3% of global population",
        "description": "Chronic autoimmune skin condition characterized by rapid skin cell buildup, producing thick silvery scales and red patches.",
        "common_symptoms": ["Red patches with silvery scales", "Dry cracked skin that may bleed", "Itching, burning, or soreness", "Pitted or ridged nails"],
        "supportive_care": [
            "Apply thick fragrance-free cream moisturizers (or petroleum jelly) immediately after bathing while skin is damp.",
            "Take short warm (not hot) baths with colloidal oatmeal or bath oils to soothe scaling.",
            "Use gentle, fragrance-free skin cleansers to preserve barrier lipids.",
            "Expose skin to brief, controlled natural sunlight (10-15 minutes) as advised."
        ],
        "preventive_measures": [
            "Identify and manage stress triggers.",
            "Avoid skin injury (cuts, scrapes, sunburns) which trigger Koebner phenomenon flare-ups.",
            "Maintain healthy indoor humidity levels."
        ],
        "things_to_avoid": [
            "Do NOT pick or peel silvery scales forcibly.",
            "Do NOT take hot showers or scrub skin aggressively with sponges.",
            "Do NOT use harsh alcohol-based toners or scented soaps.",
            "Do NOT use OTC steroid creams continuously without doctor oversight."
        ],
        "when_to_see_doctor": [
            "Psoriasis patches spread extensively or become painful.",
            "Joint stiffness or swelling develops (possible psoriatic arthritis).",
            "Topical moisturization fails to alleviate discomfort."
        ],
        "urgent_warning_signs": [
            "Widespread fiery skin redness covering most of the body with fever (erythrodermic psoriasis) or generalized pus-filled bumps (pustular psoriasis)."
        ],
        "medical_treatment_info": "Supportive care manages skin hydration and comfort. Clinical management includes prescription topicals (vitamin D analogues, steroids), phototherapy, systemic immunomodulators, or biologics.",
        "references": [
            {"source": "National Psoriasis Foundation", "title": "Psoriasis Causes, Symptoms & Care", "url": "https://www.psoriasis.org/about-psoriasis/"},
            {"source": "American Academy of Dermatology", "title": "Psoriasis Skin Care Guidance", "url": "https://www.aad.org/public/diseases/a-z/psoriasis-overview"}
        ],
        "translations": {
            "hi": {
                "condition_name": "सोरायसिस (त्वचा में जलन और पपड़ी)",
                "description": "ऑटोइम्यून स्थिति जिसके कारण त्वचा पर लाल पपड़ीदार चत्ते बनते हैं।",
                "supportive_care": ["नहाने के तुरंत बाद गाढ़ा मॉइस्चराइज़र लगाएं।", "हल्के गुनगुने पानी से नहाएं।"],
                "things_to_avoid": ["सफेद पपड़ी को ज़बरदस्ती न निकालें।", "गर्म पानी से न नहाएं।"]
            },
            "bho": {
                "condition_name": "सोरायसिस (चामड़ी पर छिलका आ लाली)",
                "description": "ऑटोइम्यून समस्या जेकरा वजह से चामड़ी पर लाल आ पांढर छिलका जइसन बन जाला।",
                "supportive_care": ["नहाये के तुरंत बाद सादा मॉइश्चराइजर या वैसलीन लगाईं।", "गुनगुना पानी से नहाईं।", "चामड़ी के सादा पानी से साफ रखीं।"],
                "things_to_avoid": ["सफेद छिलका के जबरदस्ती ना उखाड़ीं।", "गरम पानी से ना नहाईं।"]
            },
            "mr": {
                "condition_name": "सोरायसीस",
                "description": "त्वचेवरील लाल आणि पांढऱ्या खवल्यांचा त्रास.",
                "supportive_care": ["अंघोळीनंतर लगेच मॉइश्चरायझर लावा."],
                "things_to_avoid": ["पांढरी खवले ओढून काढू नका."]
            }
        },
        "version": "1.0",
        "last_reviewed": "2026-10-01",
        "status": "approved"
    },
    {
        "condition_code": "eczema",
        "condition_name": "Eczema / Atopic Dermatitis",
        "category": "Inflammatory",
        "risk_level": "Moderate",
        "prevalence": "Affects 10-20% of children and 2-5% of adults",
        "description": "Non-contagious inflammatory skin condition causing dry, itchy, red patches due to epidermal barrier disruption.",
        "common_symptoms": ["Itchy dry skin patches", "Red to brownish-gray patches", "Small raised bumps that may leak fluid", "Cracked scaly skin"],
        "supportive_care": [
            "Apply thick fragrance-free cream moisturizers or petroleum jelly twice daily and within 3 minutes of bathing.",
            "Take short warm (not hot) baths or showers (5-10 minutes).",
            "Use gentle, fragrance-free non-soap skin cleansers to preserve barrier lipids.",
            "Wear soft, breathable cotton clothing to minimize skin friction."
        ],
        "preventive_measures": [
            "Identify and manage individual flare-up triggers (dry air, synthetic wool, harsh detergents).",
            "Use a cool-mist humidifier in dry indoor spaces.",
            "Keep fingernails trimmed short to prevent skin trauma from scratching."
        ],
        "things_to_avoid": [
            "Do NOT take hot showers or scrub skin aggressively with sponges.",
            "Do NOT use scented soaps, alcohol-based lotions, or harsh bubble baths.",
            "Do NOT scratch dry patches, which worsens skin barrier breakdown.",
            "Do NOT use OTC steroid creams continuously without doctor oversight."
        ],
        "when_to_see_doctor": [
            "Eczema patches fail to improve despite daily moisturization.",
            "Itching causes sleep loss or daily distress.",
            "Skin develops weeping sores or painful cracks."
        ],
        "urgent_warning_signs": [
            "Yellow crusting, pus discharge, rapidly spreading redness, or fever (signs of secondary bacterial/viral infection)."
        ],
        "medical_treatment_info": "Supportive home care restores barrier hydration. Clinical management by a dermatologist includes prescription topical corticosteroids, calcineurin inhibitors, phototherapy, or targeted biologics.",
        "references": [
            {"source": "National Eczema Association", "title": "Eczema Causes, Symptoms & Care", "url": "https://nationaleczema.org/eczema/"},
            {"source": "American Academy of Dermatology", "title": "Atopic Dermatitis Management", "url": "https://www.aad.org/public/diseases/a-z/eczema-overview"}
        ],
        "translations": {
            "hi": {
                "condition_name": "एग्जिमा / एटोपिक डर्मेटाइटिस",
                "description": "गैर-संक्रामक त्वचा की जलन जिससे त्वचा लाल, सूखी और खुजलीदार हो जाती है।",
                "supportive_care": ["नहाने के 3 मिनट के भीतर गाढ़ा मॉइस्चराइज़र लगाएं।", "हल्के गुनगुने पानी से नहाएं।", "सूती कपड़े पहनें।"],
                "preventive_measures": ["सुगंधित साबुन और डिटर्जेंट से बचें।", "नाखून छोटे रखें।"],
                "things_to_avoid": ["गर्म पानी से न नहाएं।", "त्वचा को ज़ोर से न रगड़ें या खरोंचें।"],
                "when_to_see_doctor": ["यदि मॉइस्चराइज़र से भी राहत न मिले या त्वचा फटने लगे।"],
                "urgent_warning_signs": ["पीला मवाद आना, लालिमा का तेज़ी से फैलना या बुखार।"]
            },
            "bho": {
                "condition_name": "एग्जिमा (चामड़ी के नोचनी आ लाली)",
                "description": "चामड़ी के जलन आ नोचनी के समस्या जेमे चामड़ी सूख जाला आ लाल हो जाला।",
                "supportive_care": ["नहाये के 3 मिनट के भीतर सादा मॉइश्चराइजर लगाईं।", "गुनगुना पानी से नहाईं।", "सूती कपड़ा पहिनीं।"],
                "preventive_measures": ["सुगंधित साबुन से बचीं।", "नाखून छोटा रखीं।"],
                "things_to_avoid": ["गरम पानी से ना नहाईं।", "चामड़ी के जोर से ना रगड़ीं।"],
                "when_to_see_doctor": ["अगर आराम ना मिले या चामड़ी फटे लागी।"],
                "urgent_warning_signs": ["मवाद निकलल या बुखार आवहल।"]
            },
            "mr": {
                "condition_name": "एग्झिमा / ॲटोपिक डर्मेटायटीस",
                "description": "त्वचेचा दाह आणि खाज सुटणारा आजार.",
                "supportive_care": ["अंघोळीनंतर लगेच मॉइश्चरायझर लावा.", "कोमट पाण्याने अंघोळ करा.", "सुती कपडे वापरा."],
                "preventive_measures": ["कडक साबण टाळा.", "नखे लहान ठेवा."],
                "things_to_avoid": ["गरम पाणी वापरू नका.", "त्वचा जोरात घासणे टाळा."],
                "when_to_see_doctor": ["त्रास कमी न झाल्यास डॉक्टरांना दाखवा."],
                "urgent_warning_signs": ["पिवळा पू येणे किंवा ताप येणे."]
            }
        },
        "version": "1.0",
        "last_reviewed": "2026-10-01",
        "status": "approved"
    },
    {
        "condition_code": "tinea",
        "condition_name": "Tinea Ringworm Candidiasis",
        "category": "Fungal Skin Conditions",
        "risk_level": "Undetermined",
        "description": "This Dataset2 label groups ringworm (tinea) and skin candidiasis. They are distinct fungal infections. A healthcare professional can examine the rash and determine the cause.",
        "common_symptoms": ["Itching", "A scaly or ring-shaped rash with tinea", "A red rash in a skin fold with candidiasis"],
        "supportive_care": [
            "Wash the area gently and pat it dry, including within skin folds.",
            "Change out of damp clothing and let the area air out when practical."
        ],
        "preventive_measures": [
            "If ringworm is suspected, use your own towels, clothing, and bedding.",
            "Wear sandals in shared showers and change sweaty socks or clothing promptly."
        ],
        "things_to_avoid": [
            "Avoid starting a steroid cream on an undiagnosed rash that could be ringworm. Ask a clinician about any prescribed medicine.",
            "Avoid putting a tight or airtight dressing over the rash unless a clinician directs you to."
        ],
        "when_to_see_doctor": [
            "Arrange an examination to identify the cause, especially if the rash involves the scalp or nails.",
            "Contact a healthcare professional if the rash keeps spreading or does not improve."
        ],
        "urgent_warning_signs": [
            "Seek prompt medical advice if you develop fever, severe pain, pus, or rapidly spreading redness."
        ],
        "medical_treatment_info": "A healthcare professional can advise whether an antifungal is appropriate. The choice depends on the cause and location of the rash.",
        "references": [
            {"source": "CDC", "title": "Ringworm Basics", "url": "https://www.cdc.gov/ringworm/about/"},
            {"source": "CDC", "title": "Treatment of Ringworm", "url": "https://www.cdc.gov/ringworm/treatment/index.html"},
            {"source": "MedlinePlus", "title": "Candida Infection of the Skin", "url": "https://medlineplus.gov/ency/article/000880.htm"},
            {"source": "MedlinePlus", "title": "Ringworm of the Body", "url": "https://medlineplus.gov/ency/article/000877.htm"}
        ],
        "version": "1.0",
        "last_reviewed": "2026-11-04",
        "status": "approved"
    },
    {
        "condition_code": "unclassified",
        "condition_name": "No Confident Prediction / Unable to Assess",
        "category": "Inconclusive",
        "risk_level": "Undetermined",
        "prevalence": "Varies (occurs when score < 40% or entropy > 1.5)",
        "description": "The AI model evaluated the uploaded photo across all supported skin disease categories, but the highest similarity score was below the required 40.0% confidence threshold. No specific skin condition was diagnosed.",
        "common_symptoms": ["Low visual confidence", "High model uncertainty", "Non-dermatological or out-of-domain focus"],
        "supportive_care": [
            "Keep the affected skin area clean with warm water and a gentle, fragrance-free cleanser.",
            "Apply a simple fragrance-free emollient or petroleum jelly if skin is dry or uncomfortable.",
            "Protect exposed skin from sun exposure using broad-spectrum SPF 30+ sunscreen.",
            "Avoid unnecessary scratching or friction."
        ],
        "preventive_measures": [
            "Maintain gentle daily skin hygiene.",
            "Protect skin from environmental irritants and intense sunlight."
        ],
        "things_to_avoid": [
            "Do NOT pick, scratch, or attempt home surgical removal of any skin spot.",
            "Do NOT apply household chemicals, acids, toothpaste, or unverified remedies.",
            "Do NOT assume an unclassified result rules out unlisted conditions or confirms healthy skin."
        ],
        "when_to_see_doctor": [
            "Schedule an evaluation with a board-certified dermatologist if you have persistent or concerning skin symptoms.",
            "Consult a physician if any skin spot changes shape, color, bleeds, or causes pain."
        ],
        "urgent_warning_signs": [
            "Rapidly expanding redness, severe local pain, pus discharge, or fever."
        ],
        "medical_treatment_info": "No specific disease was identified by the AI scanner. Supportive skin care maintains skin comfort, but a clinical examination by a dermatologist is recommended for formal evaluation.",
        "references": [
            {"source": "American Academy of Dermatology (AAD)", "title": "General Skin Health Guidance", "url": "https://www.aad.org/public/everyday-care/skin-care-basics"}
        ],
        "translations": {
            "hi": {
                "condition_name": "कोई स्पष्ट अनुमान नहीं / मूल्यांकन में असमर्थ",
                "description": "एआई मॉडल ने फोटो का विश्लेषण किया, लेकिन उच्चतम मैच स्कोर 40% की सीमा से नीचे था। किसी विशेष बीमारी का निदान नहीं हुआ है।",
                "supportive_care": ["त्वचा को हल्के क्लींजर से साफ रखें।", "सूखी या जलन वाली त्वचा पर सादा मॉइस्चराइजर या वैसलीन लगाएं।", "धूप से बचाव के लिए सनस्क्रीन लगाएं।"],
                "preventive_measures": ["दैनिक त्वचा स्वच्छता बनाए रखें।", "तेज धूप से बचाव करें।"],
                "things_to_avoid": ["त्वचा को खरोंचें या नोचें नहीं।", "सिरका, नींबू, टूथपेस्ट या घरेलू रसायनों का प्रयोग न करें।"],
                "when_to_see_doctor": ["यदि लक्षण बने रहते हैं या चिंताजनक हैं, तो त्वचा विशेषज्ञ से मिलें।"],
                "urgent_warning_signs": ["तेजी से फैलती लाली, मवाद, या बुखार।"]
            },
            "bho": {
                "condition_name": "कौनों पक्का अनुमान ना मिलल / जांच में असमर्थ",
                "description": "एआई मॉडल फोटो के जांच कइलस, बाकिर स्कोर 40% से कम रहल। कौनों बीमारी के पक्का पहचान ना भइल।",
                "supportive_care": ["चामड़ी के हल्का साबुन से साफ रखीं।", "सूखल चामड़ी पर सादा वैसलीन या मॉइश्चराइजर लगाईं।", "घाम से बचे खातिर सनस्क्रीन लगाईं।"],
                "preventive_measures": ["सफाई के ध्यान रखीं।", "धूप से बचीं।"],
                "things_to_avoid": ["चामड़ी के खरोचे भा नोचे से बचीं।", "नींबू, सिरका या टूथपेस्ट ना लगाईं।"],
                "when_to_see_doctor": ["अगर तकलीफ बढ़त बा त डॉक्टर से मिलीं।"],
                "urgent_warning_signs": ["मवाद निकलल या बुखार आवहल।"]
            },
            "mr": {
                "condition_name": "स्पष्ट निदान नाही / तपासणीत असमर्थ",
                "description": "एआय मॉडेलने फोटोची तपासणी केली, पण सर्वोच्च स्कोर 40% पेक्षा कमी होता. कोणत्याही आजाराचे निदान झालेले नाही.",
                "supportive_care": ["त्वचा सौम्य क्लीन्झरने स्वच्छ ठेवा.", "कोरड्या त्वचेवर साधे मॉइश्चरायझर किंवा व्हॅसलीन लावा.", "सनस्क्रीन वापरा."],
                "preventive_measures": ["दैनंदिन स्वच्छता पाळा.", "उन्हापासून संरक्षण करा."],
                "things_to_avoid": ["त्वचा खाजवणे टाळा.", "लिंबू, व्हिनेगर किंवा टूथपेस्ट वापरू नका."],
                "when_to_see_doctor": ["त्रास कायम राहिल्यास त्वचारोग तज्ज्ञांना दाखवा."],
                "urgent_warning_signs": ["पिवळा पू येणे किंवा ताप येणे."]
            }
        },
        "version": "1.0",
        "last_reviewed": "2026-10-01",
        "status": "approved"
    }
]


def seed_medical_knowledge_base(db_path):
    """Seed and update structured medical knowledge base entries in SQLite."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    for item in SEED_KNOWLEDGE_BASE:
        cursor.execute("SELECT condition_code FROM medical_knowledge_base WHERE condition_code = ?", (item['condition_code'],))
        exists = cursor.fetchone()
        if exists:
            cursor.execute('''
                UPDATE medical_knowledge_base SET
                    condition_name = ?, category = ?, risk_level = ?, prevalence = ?,
                    description = ?, common_symptoms_json = ?, supportive_care_json = ?,
                    preventive_measures_json = ?, things_to_avoid_json = ?,
                    when_to_see_doctor_json = ?, urgent_warning_signs_json = ?,
                    medical_treatment_info = ?, references_json = ?,
                    translations_json = ?, version = ?, last_reviewed = ?, status = ?
                WHERE condition_code = ?
            ''', (
                item['condition_name'], item['category'], item['risk_level'], item.get('prevalence', ''),
                item['description'], json.dumps(item['common_symptoms']), json.dumps(item['supportive_care']),
                json.dumps(item['preventive_measures']), json.dumps(item['things_to_avoid']),
                json.dumps(item['when_to_see_doctor']), json.dumps(item['urgent_warning_signs']),
                item['medical_treatment_info'], json.dumps(item['references']),
                json.dumps(item.get('translations', {})), item.get('version', '1.0'),
                item.get('last_reviewed', '2026-10-01'), item.get('status', 'approved'),
                item['condition_code']
            ))
        else:
            cursor.execute('''
                INSERT INTO medical_knowledge_base (
                    condition_code, condition_name, category, risk_level, prevalence,
                    description, common_symptoms_json, supportive_care_json,
                    preventive_measures_json, things_to_avoid_json, when_to_see_doctor_json,
                    urgent_warning_signs_json, medical_treatment_info, references_json,
                    translations_json, version, last_reviewed, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                item['condition_code'], item['condition_name'], item['category'], item['risk_level'],
                item.get('prevalence', ''), item['description'], json.dumps(item['common_symptoms']),
                json.dumps(item['supportive_care']), json.dumps(item['preventive_measures']),
                json.dumps(item['things_to_avoid']), json.dumps(item['when_to_see_doctor']),
                json.dumps(item['urgent_warning_signs']), item['medical_treatment_info'],
                json.dumps(item['references']), json.dumps(item.get('translations', {})),
                item.get('version', '1.0'), item.get('last_reviewed', '2026-10-01'), item.get('status', 'approved')
            ))

    conn.commit()
    conn.close()


def get_knowledge_base_item(db_path, condition_code, lang='en'):
    """Retrieve structured medical knowledge base item by condition code."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM medical_knowledge_base WHERE condition_code = ?", (condition_code.lower(),))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    item = dict(row)
    item['common_symptoms']     = json.loads(item['common_symptoms_json'])     if item.get('common_symptoms_json')     else []
    item['supportive_care']     = json.loads(item['supportive_care_json'])     if item.get('supportive_care_json')     else []
    item['preventive_measures'] = json.loads(item['preventive_measures_json']) if item.get('preventive_measures_json') else []
    item['things_to_avoid']     = json.loads(item['things_to_avoid_json'])     if item.get('things_to_avoid_json')     else []
    item['when_to_see_doctor']  = json.loads(item['when_to_see_doctor_json'])  if item.get('when_to_see_doctor_json')  else []
    item['urgent_warning_signs']= json.loads(item['urgent_warning_signs_json'])if item.get('urgent_warning_signs_json')else []
    item['references']          = json.loads(item['references_json'])          if item.get('references_json')          else []
    item['translations']        = json.loads(item['translations_json'])        if item.get('translations_json')        else {}

    # Apply multilingual translation overlay if lang != 'en' and available
    if lang and lang in item['translations']:
        t = item['translations'][lang]
        if 'condition_name' in t: item['condition_name'] = t['condition_name']
        if 'description' in t:    item['description']    = t['description']
        if 'supportive_care' in t:item['supportive_care'] = t['supportive_care']
        if 'things_to_avoid' in t:item['things_to_avoid'] = t['things_to_avoid']

    item['disclaimer'] = (
        "Home-care information is provided for general educational and supportive purposes. "
        "It is not a diagnosis, prescription, or substitute for evaluation by a qualified healthcare professional. "
        "If your symptoms are severe, worsening, persistent, or concerning, seek professional medical care."
    )
    return item


def get_all_knowledge_base_items(db_path, search_query=None, category=None, risk_level=None, status=None):
    """Retrieve all knowledge base items with optional search and filters."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    query = "SELECT * FROM medical_knowledge_base WHERE 1=1"
    params = []

    if status and status.lower() != 'all':
        query += " AND status = ?"
        params.append(status.lower().strip())
    if category and category.lower() != 'all':
        query += " AND category = ?"
        params.append(category.strip())
    if risk_level and risk_level.lower() != 'all':
        query += " AND risk_level = ?"
        params.append(risk_level.strip())
    if search_query and search_query.strip():
        query += " AND (condition_code LIKE ? OR condition_name LIKE ? OR description LIKE ?)"
        pattern = "%{}%".format(search_query.strip())
        params.extend([pattern, pattern, pattern])

    query += " ORDER BY condition_name ASC"
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    result = []
    for r in rows:
        item = dict(r)
        item['common_symptoms']     = json.loads(item['common_symptoms_json'])     if item.get('common_symptoms_json')     else []
        item['supportive_care']     = json.loads(item['supportive_care_json'])     if item.get('supportive_care_json')     else []
        item['preventive_measures'] = json.loads(item['preventive_measures_json']) if item.get('preventive_measures_json') else []
        item['things_to_avoid']     = json.loads(item['things_to_avoid_json'])     if item.get('things_to_avoid_json')     else []
        item['when_to_see_doctor']  = json.loads(item['when_to_see_doctor_json'])  if item.get('when_to_see_doctor_json')  else []
        item['urgent_warning_signs']= json.loads(item['urgent_warning_signs_json'])if item.get('urgent_warning_signs_json')else []
        item['references']          = json.loads(item['references_json'])          if item.get('references_json')          else []
        result.append(item)
    return result


def update_knowledge_base_item(db_path, condition_code, data):
    """Update medical knowledge base entry (Admin content management)."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    cursor.execute('''
        UPDATE medical_knowledge_base SET
            condition_name = COALESCE(?, condition_name),
            category = COALESCE(?, category),
            risk_level = COALESCE(?, risk_level),
            description = COALESCE(?, description),
            supportive_care_json = COALESCE(?, supportive_care_json),
            preventive_measures_json = COALESCE(?, preventive_measures_json),
            things_to_avoid_json = COALESCE(?, things_to_avoid_json),
            when_to_see_doctor_json = COALESCE(?, when_to_see_doctor_json),
            urgent_warning_signs_json = COALESCE(?, urgent_warning_signs_json),
            references_json = COALESCE(?, references_json),
            version = COALESCE(?, version),
            last_reviewed = COALESCE(?, last_reviewed),
            status = COALESCE(?, status),
            updated_at = CURRENT_TIMESTAMP
        WHERE condition_code = ?
    ''', (
        data.get('condition_name'),
        data.get('category'),
        data.get('risk_level'),
        data.get('description'),
        json.dumps(data['supportive_care']) if 'supportive_care' in data else None,
        json.dumps(data['preventive_measures']) if 'preventive_measures' in data else None,
        json.dumps(data['things_to_avoid']) if 'things_to_avoid' in data else None,
        json.dumps(data['when_to_see_doctor']) if 'when_to_see_doctor' in data else None,
        json.dumps(data['urgent_warning_signs']) if 'urgent_warning_signs' in data else None,
        json.dumps(data['references']) if 'references' in data else None,
        data.get('version'),
        data.get('last_reviewed'),
        data.get('status'),
        condition_code.lower()
    ))

    affected = cursor.rowcount
    conn.commit()
    conn.close()
    return affected > 0


def delete_knowledge_base_item(db_path, condition_code):
    """Delete a medical knowledge base entry by condition code."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM medical_knowledge_base WHERE condition_code = ?", (condition_code.lower(),))
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    return affected > 0


def create_knowledge_base_item(db_path, data):
    """Create a new medical knowledge base entry."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    code = data.get('condition_code', '').lower().strip()
    if not code:
        conn.close()
        return False, "Condition code is required."

    cursor.execute("SELECT condition_code FROM medical_knowledge_base WHERE condition_code = ?", (code,))
    if cursor.fetchone():
        conn.close()
        return False, f"Condition code '{code}' already exists."

    cursor.execute('''
        INSERT INTO medical_knowledge_base (
            condition_code, condition_name, category, risk_level, prevalence,
            description, common_symptoms_json, supportive_care_json,
            preventive_measures_json, things_to_avoid_json, when_to_see_doctor_json,
            urgent_warning_signs_json, medical_treatment_info, references_json,
            translations_json, version, last_reviewed, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        code,
        data.get('condition_name', code.upper()),
        data.get('category', 'General'),
        data.get('risk_level', 'Low'),
        data.get('prevalence', 'Common'),
        data.get('description', ''),
        json.dumps(data.get('common_symptoms', [])),
        json.dumps(data.get('supportive_care', [])),
        json.dumps(data.get('preventive_measures', [])),
        json.dumps(data.get('things_to_avoid', [])),
        json.dumps(data.get('when_to_see_doctor', [])),
        json.dumps(data.get('urgent_warning_signs', [])),
        data.get('medical_treatment_info', ''),
        json.dumps(data.get('references', [])),
        json.dumps(data.get('translations', {})),
        data.get('version', '1.0'),
        datetime.now().strftime('%Y-%m-%d'),
        data.get('status', 'approved')
    ))

    conn.commit()
    conn.close()
    return True, f"Condition '{code.upper()}' created successfully."


def update_user_details(db_path, user_id, data):
    """Admin update user details (full_name, email, role, is_active)."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    full_name = data.get('full_name')
    email = data.get('email')
    role = data.get('role')
    is_active = data.get('is_active')

    fields = []
    params = []

    if full_name:
        fields.append("full_name = ?")
        params.append(full_name.strip())
    if email:
        fields.append("email = ?")
        params.append(email.strip().lower())
    if role and role in ('patient', 'admin'):
        fields.append("role = ?")
        params.append(role)
    if is_active is not None:
        fields.append("is_active = ?")
        params.append(1 if is_active else 0)

    if not fields:
        conn.close()
        return True

    params.append(user_id)
    cursor.execute("UPDATE users SET {} WHERE id = ?".format(", ".join(fields)), params)
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    return affected > 0


def delete_review_queue_item(db_path, queue_id):
    """Dismiss a review case while retaining its assessment and verdict history."""
    conn = get_db_connection(db_path)
    try:
        with conn:
            result = conn.execute('''
                UPDATE assessments SET review_queue_dismissed = 1
                WHERE id IN (
                    SELECT assessment_id FROM active_review_queue WHERE id = ? OR assessment_id = ?
                )
            ''', (queue_id, queue_id))
            return result.rowcount > 0
    finally:
        conn.close()
