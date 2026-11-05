import os
from flask import Blueprint, request, jsonify, current_app, session
from backend.routes.auth import login_required
from backend.database.db import get_assessment_by_id

xai_bp = Blueprint('xai', __name__)

@xai_bp.route('/api/explain/status', methods=['GET'])
@login_required
def get_xai_status():
    """
    GET /api/explain/status
    Check whether Explainable AI (XAI) service is active.
    """
    xai_service = current_app.config.get('XAI_SERVICE')
    if not xai_service or xai_service.gradcam_engine is None:
        return jsonify({
            'status': 'degraded',
            'available': False,
            'explanation_method': 'Grad-CAM (Gradient-weighted Class Activation Mapping)',
            'message': 'Grad-CAM engine is not initialized or model is missing.'
        })

    return jsonify({
        'status': 'healthy',
        'available': True,
        'explanation_method': 'Grad-CAM (Gradient-weighted Class Activation Mapping)',
        'target_layer': str(xai_service.gradcam_engine.target_layer),
        'model_architecture': 'Dataset2 MobileNetV2 (Keras)',
        'supported_features': [
            'Visual Grad-CAM Heatmaps',
            'Blended Overlay View',
            'Fuzzy Logic Membership & Rule Activations',
            'Model Score Explanations'
        ]
    })


@xai_bp.route('/api/explain/<assessment_id>', methods=['GET'])
@login_required
def get_explanation(assessment_id):
    """
    GET /api/explain/<assessment_id>
    Retrieve saved Explainable AI explanation enforcing assessment ownership.
    """
    db_path = current_app.config['DATABASE_PATH']
    user_id = session.get('user_id')
    is_admin = (session.get('user_role') == 'admin')

    assessment = get_assessment_by_id(db_path, assessment_id, user_id=user_id, is_admin=is_admin)
    
    if not assessment:
        return jsonify({'status': 'error', 'message': f'Assessment ID {assessment_id} not found or access denied.'}), 404

    xai_service = current_app.config.get('XAI_SERVICE')
    upload_folder = current_app.config['UPLOAD_FOLDER']

    # Generate or re-use visual Grad-CAM explanation
    visual_exp = None
    if assessment.get('image_filename'):
        image_path = os.path.join(upload_folder, assessment['image_filename'])
        if os.path.exists(image_path) and xai_service:
            visual_exp = xai_service.generate_visual_explanation(
                image_path=image_path,
                target_class_code=assessment.get('predicted_class'),
                assessment_id=assessment['id']
            )

    # Use the rules saved with the assessment's original score.
    fuzzy_exp = assessment.get('fuzzy_explanation')

    return jsonify({
        'status': 'success',
        'assessment_id': assessment['id'],
        'predicted_class': assessment.get('predicted_class'),
        'predicted_name': assessment.get('predicted_name'),
        'model_score': assessment.get('model_score'),
        'quality_status': assessment.get('quality_status', 'Optimal quality'),
        'image_filename': assessment.get('image_filename'),
        'overlay_filename': assessment.get('overlay_filename'),
        'heatmap_filename': assessment.get('heatmap_filename'),
        'visual_explanation': visual_exp,
        'fuzzy_explanation': fuzzy_exp,
        'disclaimer': 'These explanations describe the AI model\'s behavior. They do not confirm a medical diagnosis.'
    })


@xai_bp.route('/api/explain', methods=['POST'])
@login_required
def generate_explanation():
    """
    POST /api/explain
    Generate an XAI explanation for an assessment ID.
    """
    data = request.get_json(silent=True) or request.form or {}
    assessment_id = data.get('assessment_id')

    if not assessment_id:
        return jsonify({'status': 'error', 'message': 'Assessment ID is required.'}), 400

    return get_explanation(assessment_id)
