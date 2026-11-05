from flask import Blueprint, request, jsonify, current_app, session
from backend.routes.auth import login_required
from backend.database.db import (
    get_all_assessments,
    get_assessment_by_id,
    delete_assessment_by_id
)

assessments_bp = Blueprint('assessments', __name__)

@assessments_bp.route('/api/assess-symptoms', methods=['POST'])
@login_required
def assess_symptoms():
    """
    POST /api/assess-symptoms
    Evaluate standalone symptom vector using Fuzzy Severity Engine.
    """
    data = request.get_json(silent=True) or request.form or {}

    try:
        itching = float(data.get('itching', 0))
        pain = float(data.get('pain', 0))
        redness = float(data.get('redness', 0))
        duration = float(data.get('duration_days', 0))
        fever = int(data.get('fever_level', 0))
        burning = int(data.get('burning_level', 0))
    except ValueError as e:
        return jsonify({'status': 'error', 'message': f'Invalid symptom values: {str(e)}'}), 400

    fuzzy_engine = current_app.config['FUZZY_ENGINE']
    result = fuzzy_engine.evaluate(itching, pain, redness, duration, fever, burning)
    
    return jsonify({'status': 'success', 'fuzzy_assessment': result})


@assessments_bp.route('/api/history', methods=['GET'])
@login_required
def list_history():
    """
    GET /api/history
    Retrieve saved assessments for authenticated user (or all if admin).
    Supports search, class_filter, date_from, and date_to parameters.
    """
    db_path = current_app.config['DATABASE_PATH']
    search_q = request.args.get('search')
    class_f = request.args.get('class_filter')
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')

    user_id = session.get('user_id')
    is_admin = (session.get('user_role') == 'admin')

    records = get_all_assessments(
        db_path,
        search_query=search_q,
        class_filter=class_f,
        user_id=user_id,
        is_admin=is_admin,
        date_from=date_from,
        date_to=date_to
    )
    return jsonify({
        'status': 'success',
        'count': len(records),
        'assessments': records
    })


@assessments_bp.route('/api/history/<assessment_id>', methods=['GET'])
@login_required
def get_single_history(assessment_id):
    """
    GET /api/history/<assessment_id>
    Retrieve single saved assessment record enforcing ownership.
    """
    db_path = current_app.config['DATABASE_PATH']
    user_id = session.get('user_id')
    is_admin = (session.get('user_role') == 'admin')

    item = get_assessment_by_id(db_path, assessment_id, user_id=user_id, is_admin=is_admin)
    if not item:
        return jsonify({'status': 'error', 'message': f'Assessment ID {assessment_id} not found or access denied.'}), 404
    
    return jsonify({'status': 'success', 'assessment': item})


@assessments_bp.route('/api/history/<assessment_id>', methods=['DELETE'])
@login_required
def delete_single_history(assessment_id):
    """
    DELETE /api/history/<assessment_id>
    Delete specified assessment record enforcing ownership.
    """
    db_path = current_app.config['DATABASE_PATH']
    user_id = session.get('user_id')
    is_admin = (session.get('user_role') == 'admin')

    success = delete_assessment_by_id(db_path, assessment_id, user_id=user_id, is_admin=is_admin)
    if not success:
        return jsonify({'status': 'error', 'message': f'Assessment ID {assessment_id} not found or could not be deleted.'}), 404

    return jsonify({'status': 'success', 'message': f'Assessment {assessment_id} successfully deleted.'})
