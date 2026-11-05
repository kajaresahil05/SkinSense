"""
SkinSense Prediction Route — v2.0
Enhanced with:
  - Magic byte file validation (not just extension)
  - EXIF metadata stripping (privacy/HIPAA)
  - SHA-256 file hash for deduplication
  - HIPAA audit logging on assessment creation
  - Escalation to dermatologist queue for low-confidence / high-severity cases
  - Body region capture
  - Prediction entropy metadata in response
"""
import os
import uuid
from flask import Blueprint, request, jsonify, current_app, session
from werkzeug.utils import secure_filename
from backend.routes.auth import login_required
from backend.services.security_service import (
    validate_file_magic_bytes,
    strip_exif_and_save,
    compute_file_hash,
    write_audit_log
)
from backend.database.db import save_review_queue_item
from backend.services.image_validation_service import ImageValidationError

prediction_bp = Blueprint('prediction', __name__)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@prediction_bp.route('/api/predict', methods=['POST'])
@login_required
def predict():
    """
    POST /api/predict
    Full assessment pipeline: image upload → magic byte check → EXIF strip
    → CNN classification → fuzzy severity → Grad-CAM XAI → auto-escalate if needed.
    """
    ip = request.headers.get('X-Forwarded-For', request.remote_addr or 'unknown').split(',')[0].strip()
    ua = request.headers.get('User-Agent', 'unknown')[:255]
    db_path = current_app.config['DATABASE_PATH']
    user_id = session.get('user_id')
    user_email = session.get('user_email', '')

    # ── 1. File presence checks ──
    if 'image' not in request.files:
        return jsonify({'status': 'error', 'message': 'No image file provided in request.'}), 400

    if request.form.get('image_screening_consent') != 'true':
        return jsonify({
            'status': 'error',
            'error_code': 'image_screening_consent_required',
            'message': 'Please allow the Gemini skin-photo suitability check before uploading.',
        }), 400

    file = request.files['image']
    if not file or file.filename == '':
        return jsonify({'status': 'error', 'message': 'No selected image file.'}), 400

    if not allowed_file(file.filename):
        return jsonify({
            'status': 'error',
            'message': 'Invalid file format. Supported: PNG, JPG, JPEG, WEBP.'
        }), 400

    # ── 2. Save file securely ──
    upload_folder = current_app.config['UPLOAD_FOLDER']
    os.makedirs(upload_folder, exist_ok=True)

    ext = file.filename.rsplit('.', 1)[1].lower()
    safe_filename = '{}.{}'.format(uuid.uuid4().hex, ext)
    saved_path = os.path.join(upload_folder, safe_filename)
    file.save(saved_path)

    # ── 3. Magic byte deep validation ──
    is_valid_magic, magic_msg = validate_file_magic_bytes(saved_path)
    if not is_valid_magic:
        os.remove(saved_path)  # Delete suspect file
        write_audit_log(db_path, 'upload_rejected',
                        user_id=user_id, user_email=user_email,
                        resource=safe_filename, ip_address=ip, user_agent=ua,
                        status='blocked', details=magic_msg)
        return jsonify({
            'status': 'error',
            'message': 'File rejected: {}. Please upload a genuine image file.'.format(magic_msg)
        }), 400

    # ── 4. EXIF metadata stripping (HIPAA/Privacy) ──
    exif_info = strip_exif_and_save(saved_path)
    if exif_info.get('gps_removed'):
        current_app.logger.info("[Privacy] GPS EXIF removed from upload: %s", safe_filename)

    # ── 5. Compute file hash for deduplication ──
    file_hash = compute_file_hash(saved_path)

    # ── 6. Parse patient info and symptom vector ──
    try:
        patient_info = {
            'name': request.form.get('patient_name', session.get('user_name', 'Patient')),
            'age':  int(request.form.get('patient_age', 0)) if request.form.get('patient_age') else 0
        }
        body_region = request.form.get('body_region', '')
        symptom_vector = {
            'itching':  float(request.form.get('itching', 0)),
            'pain':     float(request.form.get('pain', 0)),
            'redness':  float(request.form.get('redness', 0)),
            'duration': float(request.form.get('duration_days', 0)),
            'fever':    int(request.form.get('fever_level', 0)),
            'burning':  int(request.form.get('burning_level', 0))
        }
    except ValueError as e:
        os.remove(saved_path)
        return jsonify({'status': 'error', 'message': 'Invalid numeric symptom values: {}'.format(e)}), 400

    assessment_service = current_app.config['ASSESSMENT_SERVICE']

    try:
        lang = request.form.get('lang') or request.args.get('lang') or session.get('lang') or 'en'
        assessment_res = assessment_service.process_full_assessment(
            image_path=saved_path,
            filename=safe_filename,
            patient_info=patient_info,
            symptom_vector=symptom_vector,
            user_id=user_id,
            body_region=body_region,
            image_hash=file_hash,
            lang=lang
        )

        # ── 7. Auto-escalation to dermatologist review queue ──
        _auto_escalate_if_needed(assessment_res, db_path, user_id)

        # ── 8. HIPAA Audit log ──
        write_audit_log(db_path, 'assessment_create',
                        user_id=user_id, user_email=user_email,
                        resource=assessment_res.get('id'),
                        ip_address=ip, user_agent=ua, status='success',
                        details={
                            'predicted': assessment_res.get('predicted_class'),
                            'score': assessment_res.get('model_score'),
                            'severity': assessment_res.get('severity_category'),
                            'exif_stripped': exif_info.get('stripped'),
                            'gps_removed': exif_info.get('gps_removed')
                        })

        return jsonify({'status': 'success', 'assessment': assessment_res})

    except ImageValidationError as error:
        if os.path.exists(saved_path):
            os.remove(saved_path)
        return jsonify({
            'status': 'error',
            'error_code': error.code,
            'message': str(error),
        }), error.status_code

    except Exception as e:
        current_app.logger.error("[Prediction Error] %s", e, exc_info=True)
        write_audit_log(db_path, 'assessment_create',
                        user_id=user_id, user_email=user_email,
                        ip_address=ip, status='error', details=str(e))
        return jsonify({'status': 'error', 'message': str(e)}), 500


def _auto_escalate_if_needed(assessment, db_path, user_id):
    """
    Automatically add an assessment to the dermatologist review queue if:
    - Model confidence is LOW (is_reliable = False), OR
    - Predicted condition is melanoma (mel) with any confidence >= 0.4, OR
    - Severity is High
    """
    should_escalate = False
    reason = []
    priority = 'normal'

    if not assessment.get('is_reliable', True):
        should_escalate = True
        reason.append('Low model confidence')

    predicted_class = assessment.get('predicted_class', '').lower()
    model_score     = assessment.get('model_score', 0)

    if predicted_class == 'mel' and model_score >= 0.40:
        should_escalate = True
        reason.append('Melanoma detected — urgent clinical review required')
        priority = 'urgent'
    elif predicted_class in ('bcc', 'akiec', 'scc') and model_score >= 0.50:
        should_escalate = True
        reason.append('Potential malignancy ({}) flagged'.format(predicted_class.upper()))
        priority = 'high'

    if assessment.get('severity_category') == 'High':
        should_escalate = True
        if priority == 'normal':
            priority = 'high'
        reason.append('High fuzzy severity score ({}/100)'.format(assessment.get('severity_score', 0)))

    if should_escalate:
        try:
            saved = save_review_queue_item(db_path, {
                'assessment_id': assessment.get('id'),
                'patient_id':    user_id,
                'priority':      priority,
                'queue_reason':  ' | '.join(reason)
            })
            if saved:
                assessment['escalated_to_review'] = True
                assessment['escalation_reason']   = ' | '.join(reason)
        except Exception as e:
            print('[Prediction] Auto-escalation failed: {}'.format(e))


@prediction_bp.route('/api/xai/explanation', methods=['POST'])
def get_translated_xai_explanation():
    """
    POST /api/xai/explanation
    Returns translated patient-friendly XAI explanation breakdown for an assessment.
    """
    data = request.get_json() or {}
    lang = (data.get('lang') or 'en').lower()
    xai_svc = current_app.config.get('XAI_SERVICE')
    if not xai_svc:
        return jsonify({'status': 'error', 'message': 'XAI service not configured.'}), 500

    explanation = xai_svc.generate_patient_friendly_explanation(data, lang=lang)
    return jsonify({'status': 'success', 'explanation': explanation})

