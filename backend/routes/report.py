"""
SkinSense Report Routes — v2.0
Endpoints:
  - GET /api/report/<assessment_id> — Download PDF assessment report
  - GET /api/report/<assessment_id>/preview — Get report metadata
"""
import os
from flask import Blueprint, request, jsonify, session, current_app, send_file, make_response
from backend.routes.auth import login_required
from backend.database.db import get_assessment_by_id
from backend.services.pdf_service import generate_assessment_pdf
from backend.services.security_service import write_audit_log
import io

report_bp = Blueprint('report', __name__)


@report_bp.route('/api/report/<assessment_id>', methods=['GET'])
@login_required
def download_pdf_report(assessment_id):
    """
    GET /api/report/<assessment_id>
    Generate and stream a PDF assessment report.
    Patient can only download their own reports. Admin can download any.
    """
    db_path      = current_app.config['DATABASE_PATH']
    upload_folder = current_app.config['UPLOAD_FOLDER']
    user_id      = session.get('user_id')
    user_email   = session.get('user_email', '')
    is_admin     = (session.get('user_role') == 'admin')
    ip           = request.headers.get('X-Forwarded-For', request.remote_addr or '').split(',')[0].strip()
    ua           = request.headers.get('User-Agent', '')[:255]

    # Retrieve assessment (enforces ownership)
    assessment = get_assessment_by_id(db_path, assessment_id,
                                       user_id=user_id, is_admin=is_admin)
    if not assessment:
        return jsonify({
            'status': 'error',
            'message': 'Assessment {} not found or access denied.'.format(assessment_id)
        }), 404

    lang = request.args.get('lang') or session.get('lang') or session.get('preferred_language') or assessment.get('lang') or 'en'

    try:
        pdf_bytes = generate_assessment_pdf(assessment, upload_folder, lang=lang)

        write_audit_log(db_path, 'report_downloaded',
                        user_id=user_id, user_email=user_email,
                        resource=assessment_id, ip_address=ip, user_agent=ua,
                        status='success')

        response = make_response(pdf_bytes)
        response.headers['Content-Type']        = 'application/pdf'
        response.headers['Content-Disposition'] = 'attachment; filename="SkinSense_Report_{}.pdf"'.format(assessment_id)
        response.headers['Content-Length']      = len(pdf_bytes)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        return response

    except Exception as e:
        current_app.logger.error("[ReportRoute] PDF generation failed: %s", e, exc_info=True)
        write_audit_log(db_path, 'report_downloaded',
                        user_id=user_id, user_email=user_email,
                        resource=assessment_id, ip_address=ip,
                        status='error', details=str(e))
        return jsonify({'status': 'error', 'message': 'PDF generation failed: {}'.format(e)}), 500


@report_bp.route('/api/report/<assessment_id>/preview', methods=['GET'])
@login_required
def report_preview(assessment_id):
    """
    GET /api/report/<assessment_id>/preview
    Return report metadata without generating the full PDF.
    """
    db_path  = current_app.config['DATABASE_PATH']
    user_id  = session.get('user_id')
    is_admin = (session.get('user_role') == 'admin')

    assessment = get_assessment_by_id(db_path, assessment_id,
                                       user_id=user_id, is_admin=is_admin)
    if not assessment:
        return jsonify({'status': 'error', 'message': 'Assessment not found.'}), 404

    return jsonify({
        'status': 'success',
        'preview': {
            'assessment_id':       assessment.get('id'),
            'patient_name':        assessment.get('patient_name', 'Anonymous'),
            'predicted_condition': assessment.get('predicted_name', 'Unknown'),
            'severity_category':   assessment.get('severity_category', 'Unknown'),
            'model_score_pct':     '{:.1f}%'.format((assessment.get('model_score') or 0) * 100),
            'created_at':          assessment.get('created_at', ''),
            'has_heatmap':         bool(assessment.get('heatmap_filename')),
            'download_url':        '/api/report/{}'.format(assessment_id),
            'filename':            'SkinSense_Report_{}.pdf'.format(assessment_id)
        }
    })
