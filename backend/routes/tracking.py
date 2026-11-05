"""
SkinSense Longitudinal Lesion Tracking Routes — v2.0
Enables patients to:
  - Create named lesion tracks (e.g. "Mole on left shoulder")
  - Add assessments to a track over time
  - View progression timeline (ABCDE evolution tracking)
  - Detect significant changes between assessments
"""
from flask import Blueprint, request, jsonify, session, current_app
from backend.routes.auth import login_required
from backend.database.db import (
    create_lesion_track, get_lesion_tracks_for_user,
    get_lesion_track_by_id, add_assessment_to_track,
    get_track_assessments, delete_lesion_track
)

tracking_bp = Blueprint('tracking', __name__)


@tracking_bp.route('/api/tracks', methods=['GET'])
@login_required
def list_tracks():
    """GET /api/tracks — List all lesion tracks for authenticated patient."""
    db_path = current_app.config['DATABASE_PATH']
    user_id = session.get('user_id')
    tracks  = get_lesion_tracks_for_user(db_path, user_id)
    return jsonify({'status': 'success', 'count': len(tracks), 'tracks': tracks})


@tracking_bp.route('/api/tracks', methods=['POST'])
@login_required
def create_track():
    """
    POST /api/tracks
    Create a new lesion track.
    Body: { "track_name": "Mole on shoulder", "body_region": "upper_back", "notes": "..." }
    """
    data        = request.get_json(silent=True) or {}
    user_id     = session.get('user_id')
    db_path     = current_app.config['DATABASE_PATH']
    track_name  = data.get('track_name', '').strip()
    body_region = data.get('body_region', '')
    notes       = data.get('notes', '')

    if not track_name:
        return jsonify({'status': 'error', 'message': 'Track name is required.'}), 400

    track = create_lesion_track(db_path, user_id, track_name, body_region, notes)
    return jsonify({'status': 'success', 'message': 'Lesion track created.', 'track': track}), 201


@tracking_bp.route('/api/tracks/<int:track_id>', methods=['GET'])
@login_required
def get_track(track_id):
    """GET /api/tracks/<id> — Get single track with full assessment timeline."""
    db_path = current_app.config['DATABASE_PATH']
    user_id = session.get('user_id')

    track = get_lesion_track_by_id(db_path, track_id, user_id)
    if not track:
        return jsonify({'status': 'error', 'message': 'Track not found or access denied.'}), 404

    assessments = get_track_assessments(db_path, track_id)

    # Compute progression analysis
    progression = _analyze_progression(assessments)

    return jsonify({
        'status':      'success',
        'track':       track,
        'assessments': assessments,
        'progression': progression
    })


@tracking_bp.route('/api/tracks/<int:track_id>/add', methods=['POST'])
@login_required
def add_to_track(track_id):
    """
    POST /api/tracks/<id>/add
    Link an existing assessment to this lesion track.
    Body: { "assessment_id": "ASS-XXXXXXXX", "change_notes": "..." }
    """
    data          = request.get_json(silent=True) or {}
    user_id       = session.get('user_id')
    db_path       = current_app.config['DATABASE_PATH']
    assessment_id = data.get('assessment_id', '').strip()
    change_notes  = data.get('change_notes', '')

    if not assessment_id:
        return jsonify({'status': 'error', 'message': 'Assessment ID is required.'}), 400

    # Verify track belongs to this user
    track = get_lesion_track_by_id(db_path, track_id, user_id)
    if not track:
        return jsonify({'status': 'error', 'message': 'Track not found or access denied.'}), 404

    success = add_assessment_to_track(db_path, track_id, assessment_id, user_id, change_notes)
    if not success:
        return jsonify({'status': 'error', 'message': 'Assessment not found or access denied.'}), 404

    return jsonify({'status': 'success', 'message': 'Assessment added to lesion track.'})


@tracking_bp.route('/api/tracks/<int:track_id>', methods=['DELETE'])
@login_required
def remove_track(track_id):
    """DELETE /api/tracks/<id> — Remove a lesion track."""
    db_path = current_app.config['DATABASE_PATH']
    user_id = session.get('user_id')

    success = delete_lesion_track(db_path, track_id, user_id)
    if not success:
        return jsonify({'status': 'error', 'message': 'Track not found or access denied.'}), 404

    return jsonify({'status': 'success', 'message': 'Lesion track deleted.'})


def _analyze_progression(assessments):
    """
    Analyze lesion progression across multiple assessments.
    Flags: severity trend, class changes, confidence trend.
    """
    if len(assessments) < 2:
        return {
            'has_progression': False,
            'message': 'Add more assessments over time to track progression.'
        }

    scores    = [a.get('model_score', 0) for a in assessments]
    severities = [a.get('severity_score', 0) for a in assessments]
    classes   = [a.get('predicted_class', '') for a in assessments]

    severity_trend = 'stable'
    if severities[-1] > severities[0] + 10:
        severity_trend = 'worsening'
    elif severities[-1] < severities[0] - 10:
        severity_trend = 'improving'

    class_changed = len(set(classes)) > 1
    alerts = []

    if severity_trend == 'worsening':
        alerts.append({
            'type': 'warning',
            'message': 'Severity score increased from {:.0f} to {:.0f}. Consider consulting a dermatologist.'.format(
                severities[0], severities[-1]
            )
        })

    if class_changed:
        alerts.append({
            'type': 'alert',
            'message': 'Predicted condition changed across assessments: {}. This warrants clinical evaluation.'.format(
                ' → '.join(set(classes))
            )
        })

    latest_class = classes[-1].lower() if classes else ''
    if latest_class in ('mel', 'bcc', 'akiec'):
        alerts.append({
            'type': 'urgent',
            'message': 'Latest assessment suggests potential malignancy ({}). Seek immediate dermatologist evaluation.'.format(
                latest_class.upper()
            )
        })

    return {
        'has_progression':    True,
        'total_assessments':  len(assessments),
        'severity_trend':     severity_trend,
        'severity_start':     round(severities[0], 1),
        'severity_latest':    round(severities[-1], 1),
        'severity_change':    round(severities[-1] - severities[0], 1),
        'class_changed':      class_changed,
        'all_classes':        classes,
        'confidence_trend':   'improving' if scores[-1] > scores[0] else 'declining',
        'alerts':             alerts
    }
