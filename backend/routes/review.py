"""
SkinSense Dermatologist Review Queue Routes — v2.0
Endpoints for:
  - Viewing the pending review queue (dermatologist/admin)
  - Submitting a dermatologist verdict
  - Patient viewing their review status
  - Automatic queue entry for flagged assessments
"""
import os

from flask import Blueprint, request, jsonify, session, current_app, url_for
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from werkzeug.utils import safe_join
from backend.routes.auth import login_required, admin_required
from backend.database.db import (
    get_review_queue, get_review_queue_page, get_review_item_by_id,
    update_review_verdict, get_all_assessments, get_assessment_by_id
)
from backend.services.security_service import write_audit_log

review_bp = Blueprint('review', __name__)


@review_bp.route('/api/review/queue', methods=['GET'])
@admin_required
def get_queue():
    """
    GET /api/review/queue
    List all dermatologist review items. Admin/dermatologist only.
    """
    db_path  = current_app.config['DATABASE_PATH']
    status   = request.args.get('status')
    priority = request.args.get('priority')
    try:
        limit = max(1, min(500, int(request.args.get('limit', 50))))
        offset = max(0, int(request.args.get('offset', 0)))
    except ValueError:
        return jsonify({'status': 'error', 'message': 'Invalid review page parameters.'}), 400

    if status and status.lower() in ('all', ''):
        status = None
    if priority and priority.lower() in ('all', ''):
        priority = None

    page = get_review_queue_page(
        db_path, status=status, priority=priority, limit=limit, offset=offset,
        search=request.args.get('search'), newest_first=True,
    )
    items = page['items']
    next_offset = offset + len(items)
    return jsonify({
        'status': 'success', 'count': len(items), 'queue': items, **page,
        'has_more': next_offset < page['total_count'], 'next_offset': next_offset,
    })


@review_bp.route('/api/review/queue/<int:queue_id>', methods=['GET'])
@admin_required
def get_queue_item(queue_id):
    """GET /api/review/queue/<id> — Single queue entry with full assessment."""
    db_path = current_app.config['DATABASE_PATH']
    item    = get_review_item_by_id(db_path, queue_id)
    if not item:
        return jsonify({'status': 'error', 'message': 'Review item not found.'}), 404
    report = get_assessment_by_id(db_path, item['assessment_id'], is_admin=True)
    if not report:
        return jsonify({'status': 'error', 'message': 'Assessment report not found.'}), 404

    assets = {}
    for key in ('image_filename', 'overlay_filename', 'heatmap_filename'):
        filename = report.get(key)
        path = safe_join(current_app.config['UPLOAD_FOLDER'], filename) if filename else None
        assets[key] = url_for('uploaded_file', filename=filename) if path and os.path.isfile(path) else None

    signer = URLSafeTimedSerializer(current_app.secret_key, salt='review-report')
    token = signer.dumps({
        'queue_id': str(item['id']),
        'assessment_id': report['id'],
        'admin_id': session['user_id'],
    })
    return jsonify({
        'status': 'success',
        'item': item,
        'report': report,
        'report_assets': assets,
        'report_download_url': url_for('report.download_pdf_report', assessment_id=report['id']),
        'report_review_token': token,
    })


@review_bp.route('/api/review/queue/<queue_id>/verdict', methods=['POST'])
@admin_required
def submit_verdict(queue_id):
    """
    POST /api/review/queue/<id>/verdict
    Dermatologist submits clinical verdict on a review item.
    Body: { "verdict": "Confirmed Melanoma", "notes": "...", "status": "completed" }
    """
    try:
        data         = request.get_json(silent=True) or {}
        diagnosis    = (data.get('diagnosis') or data.get('verdict') or '').strip()
        verdict_cat  = data.get('verdict_category') or None
        notes        = (data.get('notes') or data.get('clinical_notes') or '').strip()
        raw_status   = str(data.get('status', 'completed')).lower().strip()

        # Map raw status to allowed SQLite CHECK constraint values
        if raw_status in ('pending', 'in_review', 'completed', 'rejected'):
            new_status = raw_status
        else:
            new_status = 'completed'

        if not diagnosis:
            return jsonify({'status': 'error', 'message': 'Verdict text is required.'}), 400
        if verdict_cat not in (None, 'reviewed', 'confirmed', 'corrected', 'urgent'):
            return jsonify({'status': 'error', 'message': 'Invalid verdict category.'}), 400

        db_path      = current_app.config['DATABASE_PATH']
        derm_id      = session.get('user_id')
        derm_email   = session.get('user_email', '')
        ip           = request.headers.get('X-Forwarded-For', request.remote_addr or '').split(',')[0].strip()

        if data.get('report_reviewed') is not True:
            return jsonify({'status': 'error', 'message': 'Open and review the patient report before submitting a verdict.'}), 400
        try:
            signer = URLSafeTimedSerializer(current_app.secret_key, salt='review-report')
            viewed = signer.loads(data.get('report_review_token', ''), max_age=1800)
        except (BadSignature, SignatureExpired, TypeError):
            return jsonify({'status': 'error', 'message': 'Please reopen the patient report before submitting a verdict.'}), 400

        item = get_review_item_by_id(db_path, queue_id)
        if not item:
            return jsonify({'status': 'error', 'message': 'Review item not found.'}), 404
        if viewed != {
            'queue_id': str(item['id']),
            'assessment_id': item['assessment_id'],
            'admin_id': derm_id,
        }:
            return jsonify({'status': 'error', 'message': 'The opened report does not match this review case.'}), 400

        success = update_review_verdict(db_path, queue_id, {
            'status':           new_status,
            'derm_verdict':     diagnosis,
            'verdict_category': verdict_cat,
            'derm_notes':       notes,
            'assigned_derm_id': derm_id
        })

        if not success:
            return jsonify({'status': 'error', 'message': 'Review item #{} not found or already closed.'.format(queue_id)}), 404

        try:
            write_audit_log(db_path, 'review_verdict_submitted',
                            user_id=derm_id, user_email=derm_email,
                            resource='review_queue/{}'.format(queue_id),
                            ip_address=ip, status='success',
                            details={'verdict': diagnosis, 'queue_id': queue_id, 'report_assessment_id': item['assessment_id']})
        except Exception as audit_err:
            current_app.logger.warning("Failed to write audit log for verdict: %s", audit_err)

        return jsonify({
            'status': 'success',
            'message': 'Clinical verdict recorded.',
            'queue_id': queue_id
        })
    except Exception as e:
        current_app.logger.error("Error submitting verdict: %s", str(e), exc_info=True)
        return jsonify({'status': 'error', 'message': 'Server error: {}'.format(str(e))}), 500


@review_bp.route('/api/review/queue/<queue_id>', methods=['DELETE'])
@admin_required
def delete_review_item(queue_id):
    """
    DELETE /api/review/queue/<queue_id>
    Remove an item from the dermatologist review queue.
    """
    db_path = current_app.config['DATABASE_PATH']
    from backend.database.db import delete_review_queue_item
    try:
        success = delete_review_queue_item(db_path, queue_id)
        if not success:
            return jsonify({'status': 'error', 'message': f'Review queue item {queue_id} not found.'}), 404
        return jsonify({'status': 'success', 'message': f'Review item {queue_id} removed from the queue.'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@review_bp.route('/api/review/my-status', methods=['GET'])
@login_required
def my_review_status():
    """
    GET /api/review/my-status
    Patient views their own pending review items and verdicts.
    """
    db_path = current_app.config['DATABASE_PATH']
    user_id = session.get('user_id')

    items = get_review_queue(db_path, patient_id=user_id, limit=20)
    return jsonify({
        'status': 'success',
        'count': len(items),
        'reviews': [{
            'queue_id':     item.get('id'),
            'assessment_id': item.get('assessment_id'),
            'priority':     item.get('priority'),
            'queue_reason': item.get('queue_reason'),
            'status':       item.get('status'),
            'verdict':      item.get('derm_verdict'),
            'notes':        item.get('derm_notes'),
            'created_at':   item.get('created_at'),
            'completed_at': item.get('completed_at')
        } for item in items]
    })


@review_bp.route('/api/review/stats', methods=['GET'])
@admin_required
def review_stats():
    """GET /api/review/stats — Admin dashboard statistics for review queue."""
    db_path = current_app.config['DATABASE_PATH']

    pending   = get_review_queue(db_path, status='pending',   limit=1000)
    urgent    = [i for i in pending if i.get('priority') == 'urgent']
    completed = get_review_queue(db_path, status='completed', limit=1000)

    return jsonify({
        'status': 'success',
        'stats': {
            'pending_total':   len(pending),
            'urgent_count':    len(urgent),
            'completed_total': len(completed),
            'pending_by_priority': {
                'urgent': len([i for i in pending if i.get('priority') == 'urgent']),
                'high':   len([i for i in pending if i.get('priority') == 'high']),
                'normal': len([i for i in pending if i.get('priority') == 'normal']),
                'low':    len([i for i in pending if i.get('priority') == 'low']),
            }
        }
    })
