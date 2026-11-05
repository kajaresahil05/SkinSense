"""
SkinSense Admin Routes — v2.0
Endpoints:
  - GET  /api/admin/stats            — Platform statistics (admin only)
  - GET  /api/admin/users            — Paginated user list (admin only)
  - POST /api/admin/users/<id>/toggle-active — Enable/disable user account
"""
from flask import Blueprint, request, jsonify, session, current_app
from backend.routes.auth import admin_required
from backend.database.db import get_all_assessments, get_db_connection, get_model_prediction_distribution

admin_bp = Blueprint('admin', __name__)


@admin_bp.route('/api/admin/stats', methods=['GET'])
@admin_required
def admin_stats():
    """
    GET /api/admin/stats
    Returns high-level platform statistics for the admin dashboard.
    """
    db_path     = current_app.config['DATABASE_PATH']
    model_svc   = current_app.config.get('MODEL_SERVICE')
    upload_dir  = current_app.config.get('UPLOAD_FOLDER', '')

    try:
        conn   = get_db_connection(db_path)
        cursor = conn.cursor()

        # Total users
        cursor.execute("SELECT COUNT(*) FROM users WHERE role = 'patient'")
        total_users = cursor.fetchone()[0]

        # Total assessments
        cursor.execute("SELECT COUNT(*) FROM assessments")
        total_scans = cursor.fetchone()[0]

        # Pending review
        cursor.execute("SELECT COUNT(*) FROM active_review_queue WHERE status = 'pending'")
        pending_review = cursor.fetchone()[0]

        # Live prediction distribution from assessments
        cursor.execute("""
            SELECT predicted_class, COUNT(*) as cnt
            FROM assessments
            WHERE predicted_class IS NOT NULL
            GROUP BY predicted_class
            ORDER BY cnt DESC
        """)
        dist_rows = cursor.fetchall()
        class_distribution = {r[0]: r[1] for r in dist_rows}

        conn.close()
        active_distribution = get_model_prediction_distribution(db_path, model_svc)
    except Exception as e:
        current_app.logger.error("[Admin Stats] DB error: %s", e)
        return jsonify({'status': 'error', 'message': 'Database error.'}), 500

    import os
    xai_service = current_app.config.get('XAI_SERVICE')
    health = {
        'Database':     {'ok': True,  'label': 'Connected'},
        'ML Model':     {'ok': bool(model_svc and model_svc.is_loaded), 'label': 'Loaded' if (model_svc and model_svc.is_loaded) else 'Not Loaded'},
        'Upload Dir':   {'ok': os.path.isdir(upload_dir), 'label': 'OK' if os.path.isdir(upload_dir) else 'Missing'},
        'XAI (Grad-CAM)': {'ok': bool(xai_service and xai_service.gradcam_engine), 'label': 'Active' if xai_service and xai_service.gradcam_engine else 'Unavailable'},
    }

    return jsonify({
        'status': 'success',
        'stats': {
            'total_users':        total_users,
            'total_scans':        total_scans,
            'pending_review':     pending_review,
            'model_status':       'Ready' if (model_svc and model_svc.is_loaded) else 'Not Loaded',
            'class_distribution': class_distribution,
            'active_model_name':   model_svc.MODEL_NAME if model_svc else None,
            'active_model_distribution': active_distribution,
            'health':             health,
        }
    })


@admin_bp.route('/api/admin/users', methods=['GET'])
@admin_required
def admin_list_users():
    """
    GET /api/admin/users
    Returns list of user accounts with optional search, role, and status filters.
    Query params: search, role, status, limit, offset
    """
    db_path = current_app.config['DATABASE_PATH']
    search  = request.args.get('search', '').strip()
    role_f  = request.args.get('role', '').strip()
    stat_f  = request.args.get('status', '').strip()
    limit   = min(int(request.args.get('limit', 100)), 500)
    offset  = int(request.args.get('offset', 0))

    try:
        conn   = get_db_connection(db_path)
        cursor = conn.cursor()

        where_clauses = ["1=1"]
        params = []

        if role_f and role_f.lower() != 'all':
            where_clauses.append("u.role = ?")
            params.append(role_f.lower())

        if stat_f and stat_f.lower() != 'all':
            if stat_f.lower() == 'active':
                where_clauses.append("(u.is_active IS NULL OR u.is_active = 1)")
            elif stat_f.lower() == 'disabled':
                where_clauses.append("u.is_active = 0")

        if search:
            where_clauses.append("(LOWER(u.full_name) LIKE ? OR LOWER(u.email) LIKE ? OR u.id LIKE ?)")
            pattern = f"%{search.lower()}%"
            params.extend([pattern, pattern, pattern])

        where_sql = "WHERE " + " AND ".join(where_clauses)

        cursor.execute(f"""
            SELECT u.id, u.full_name, u.email, u.role, u.created_at, u.last_login,
                   COALESCE(u.is_active, 1) as is_active,
                   (SELECT COUNT(*) FROM assessments a WHERE a.user_id = u.id OR CAST(a.user_id AS INTEGER) = u.id OR (a.patient_name IS NOT NULL AND LOWER(a.patient_name) = LOWER(u.full_name))) as scan_count
            FROM users u
            {where_sql}
            ORDER BY u.created_at DESC
            LIMIT ? OFFSET ?
        """, params + [limit, offset])

        rows = cursor.fetchall()
        users = [dict(r) for r in rows]

        cursor.execute(f"SELECT COUNT(*) FROM users u {where_sql}", params)
        total = cursor.fetchone()[0]
        conn.close()

    except Exception as e:
        current_app.logger.error("[Admin Users] DB error: %s", e)
        return jsonify({'status': 'error', 'message': f'Database error: {str(e)}'}), 500

    return jsonify({
        'status': 'success',
        'total':  total,
        'count':  len(users),
        'users':  users
    })


@admin_bp.route('/api/admin/users/<int:user_id>', methods=['PUT'])
@admin_required
def update_user(user_id):
    """
    PUT /api/admin/users/<id>
    Update user profile details (full_name, email, role, is_active).
    """
    db_path = current_app.config['DATABASE_PATH']
    data = request.get_json(silent=True) or {}
    admin_id = session.get('user_id')
    admin_email = session.get('user_email', 'admin')

    from backend.database.db import update_user_details
    from backend.services.security_service import write_audit_log

    try:
        success = update_user_details(db_path, user_id, data)
        if not success:
            return jsonify({'status': 'error', 'message': 'User update failed or user not found.'}), 404

        ip = request.headers.get('X-Forwarded-For', request.remote_addr or 'unknown').split(',')[0].strip()
        try:
            write_audit_log(
                db_path, 'user_updated',
                user_id=str(admin_id), user_email=admin_email,
                resource=f"users/{user_id}", ip_address=ip, status='success',
                details={'updated_fields': list(data.keys())}
            )
        except Exception:
            pass

        return jsonify({'status': 'success', 'message': f'User account #{user_id} updated successfully.'})
    except Exception as e:
        current_app.logger.error("[Admin UpdateUser] Error: %s", e)
        return jsonify({'status': 'error', 'message': str(e)}), 500


@admin_bp.route('/api/admin/users/<int:user_id>/toggle-active', methods=['POST'])
@admin_required
def toggle_user_active(user_id):
    """
    POST /api/admin/users/<id>/toggle-active
    Toggle the is_active status of a patient account.
    Cannot deactivate other admin accounts.
    """
    db_path = current_app.config['DATABASE_PATH']
    admin_id = session.get('user_id')

    if user_id == admin_id:
        return jsonify({'status': 'error', 'message': 'Cannot deactivate your own account.'}), 400

    try:
        conn   = get_db_connection(db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT id, role, is_active, full_name FROM users WHERE id = ?", (user_id,))
        user = cursor.fetchone()
        if not user:
            conn.close()
            return jsonify({'status': 'error', 'message': 'User not found.'}), 404

        if user['role'] == 'admin':
            conn.close()
            return jsonify({'status': 'error', 'message': 'Cannot toggle admin account status.'}), 403

        current_active = user['is_active'] if user['is_active'] is not None else 1
        new_active     = 0 if current_active else 1

        conn.execute("UPDATE users SET is_active = ? WHERE id = ?", (new_active, user_id))
        conn.commit()
        conn.close()

        action = 'activated' if new_active else 'deactivated'
        return jsonify({
            'status':  'success',
            'message': f"User {user['full_name']} has been {action}.",
            'is_active': bool(new_active)
        })

    except Exception as e:
        current_app.logger.error("[Admin ToggleUser] Error: %s", e)
        return jsonify({'status': 'error', 'message': 'Database error.'}), 500


@admin_bp.route('/api/admin/users/<int:user_id>', methods=['DELETE'])
@admin_required
def delete_user(user_id):
    """
    DELETE /api/admin/users/<id>
    Delete a patient user account. Cannot delete self or admin accounts.
    Writes audit log for security accountability.
    """
    admin_id = session.get('user_id')
    admin_email = session.get('user_email', 'admin')
    if user_id == admin_id:
        return jsonify({'status': 'error', 'message': 'Cannot delete your own administrator account.'}), 400

    db_path = current_app.config['DATABASE_PATH']
    from backend.database.db import delete_user_by_id
    from backend.services.security_service import write_audit_log

    try:
        success, msg = delete_user_by_id(db_path, user_id)
        if not success:
            return jsonify({'status': 'error', 'message': msg}), 400

        ip = request.headers.get('X-Forwarded-For', request.remote_addr or 'unknown').split(',')[0].strip()
        try:
            write_audit_log(
                db_path, 'user_deleted',
                user_id=str(admin_id), user_email=admin_email,
                resource=f"users/{user_id}", ip_address=ip, status='success',
                details={'target_user_id': user_id}
            )
        except Exception as audit_err:
            current_app.logger.warning("Failed writing audit log for user deletion: %s", audit_err)

        return jsonify({'status': 'success', 'message': msg})
    except Exception as e:
        current_app.logger.error("[Admin DeleteUser] Error: %s", e)
        return jsonify({'status': 'error', 'message': f"Database error: {str(e)}"}), 500


# ────────────────────────────────────────────────
# MEDICAL CONTENT KNOWLEDGE BASE MANAGEMENT (Req 30)
# ────────────────────────────────────────────────

@admin_bp.route('/api/admin/knowledge-base', methods=['GET'])
@admin_required
def admin_list_knowledge_base():
    """
    GET /api/admin/knowledge-base
    Returns condition entries in the medical knowledge base with optional search and filtering.
    """
    db_path = current_app.config['DATABASE_PATH']
    search     = request.args.get('search')
    category   = request.args.get('category')
    risk_level = request.args.get('risk_level')
    status     = request.args.get('status')

    from backend.database.db import get_all_knowledge_base_items
    try:
        items = get_all_knowledge_base_items(
            db_path,
            search_query=search,
            category=category,
            risk_level=risk_level,
            status=status
        )
        return jsonify({'status': 'success', 'count': len(items), 'items': items})
    except Exception as e:
        current_app.logger.error("[Admin KB List] Error: %s", e)
        return jsonify({'status': 'error', 'message': str(e)}), 500


@admin_bp.route('/api/admin/knowledge-base', methods=['POST'])
@admin_required
def admin_create_knowledge_base_item():
    """
    POST /api/admin/knowledge-base
    Create a new medical condition entry in knowledge base.
    """
    db_path = current_app.config['DATABASE_PATH']
    data = request.get_json(silent=True) or {}
    admin_email = session.get('user_email', 'admin')

    from backend.database.db import create_knowledge_base_item
    from backend.services.security_service import write_audit_log

    try:
        success, msg = create_knowledge_base_item(db_path, data)
        if not success:
            return jsonify({'status': 'error', 'message': msg}), 400

        ip = request.headers.get('X-Forwarded-For', request.remote_addr or 'unknown').split(',')[0].strip()
        try:
            write_audit_log(
                db_path, 'medical_content_create',
                user_id=str(session.get('user_id')), user_email=admin_email,
                resource=data.get('condition_code', '').lower(), ip_address=ip, status='success',
                details={'condition_name': data.get('condition_name')}
            )
        except Exception:
            pass

        return jsonify({'status': 'success', 'message': msg})
    except Exception as e:
        current_app.logger.error("[Admin KB Create] Error: %s", e)
        return jsonify({'status': 'error', 'message': str(e)}), 500


@admin_bp.route('/api/admin/knowledge-base/<condition_code>', methods=['GET'])
@admin_required
def admin_get_knowledge_base_item(condition_code):
    """
    GET /api/admin/knowledge-base/<condition_code>
    Returns single knowledge base entry for editing.
    """
    db_path = current_app.config['DATABASE_PATH']
    from backend.database.db import get_knowledge_base_item
    try:
        item = get_knowledge_base_item(db_path, condition_code)
        if not item:
            return jsonify({'status': 'error', 'message': f'Condition "{condition_code}" not found in KB.'}), 404
        return jsonify({'status': 'success', 'item': item})
    except Exception as e:
        current_app.logger.error("[Admin KB Get] Error: %s", e)
        return jsonify({'status': 'error', 'message': str(e)}), 500


@admin_bp.route('/api/admin/knowledge-base/<condition_code>', methods=['PUT'])
@admin_required
def admin_update_knowledge_base_item(condition_code):
    """
    PUT /api/admin/knowledge-base/<condition_code>
    Update medical content fields for a condition.
    """
    db_path = current_app.config['DATABASE_PATH']
    data = request.get_json(silent=True) or {}
    admin_email = session.get('user_email', 'admin')

    from backend.database.db import update_knowledge_base_item
    from backend.services.security_service import write_audit_log

    try:
        success = update_knowledge_base_item(db_path, condition_code, data)
        if not success:
            return jsonify({'status': 'error', 'message': 'Condition not found or update failed.'}), 404

        ip = request.headers.get('X-Forwarded-For', request.remote_addr or 'unknown').split(',')[0].strip()
        try:
            write_audit_log(
                db_path, 'medical_content_update',
                user_id=str(session.get('user_id')), user_email=admin_email,
                resource=condition_code, ip_address=ip, status='success',
                details={'version': data.get('version'), 'status': data.get('status')}
            )
        except Exception:
            pass

        return jsonify({'status': 'success', 'message': f'Medical content for "{condition_code.upper()}" updated successfully.'})
    except Exception as e:
        current_app.logger.error("[Admin KB Update] Error: %s", e)
        return jsonify({'status': 'error', 'message': str(e)}), 500


@admin_bp.route('/api/admin/knowledge-base/<condition_code>', methods=['DELETE'])
@admin_required
def admin_delete_knowledge_base_item(condition_code):
    """
    DELETE /api/admin/knowledge-base/<condition_code>
    Delete a medical condition entry from knowledge base.
    """
    db_path = current_app.config['DATABASE_PATH']
    admin_email = session.get('user_email', 'admin')

    from backend.database.db import delete_knowledge_base_item
    from backend.services.security_service import write_audit_log

    try:
        success = delete_knowledge_base_item(db_path, condition_code)
        if not success:
            return jsonify({'status': 'error', 'message': f'Condition "{condition_code}" not found.'}), 404

        ip = request.headers.get('X-Forwarded-For', request.remote_addr or 'unknown').split(',')[0].strip()
        try:
            write_audit_log(
                db_path, 'medical_content_delete',
                user_id=str(session.get('user_id')), user_email=admin_email,
                resource=condition_code, ip_address=ip, status='success'
            )
        except Exception:
            pass

        return jsonify({'status': 'success', 'message': f'Condition "{condition_code.upper()}" deleted successfully.'})
    except Exception as e:
        current_app.logger.error("[Admin KB Delete] Error: %s", e)
        return jsonify({'status': 'error', 'message': str(e)}), 500

