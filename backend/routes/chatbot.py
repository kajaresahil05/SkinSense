import os
import uuid
from flask import Blueprint, request, jsonify, current_app, session
from werkzeug.utils import secure_filename
from backend.routes.auth import login_required
from backend.database.db import save_chat_message, get_chat_history

chatbot_bp = Blueprint('chatbot', __name__)

@chatbot_bp.route('/api/chat', methods=['POST'])
@login_required
def chat():
    """
    POST /api/chat
    Process user chat prompt, optional assessment_id context, or attached image.
    Returns dynamic AI response for authenticated user.
    """
    data = request.form if request.form else (request.get_json(silent=True) or {})
    
    user_message = data.get('message', '').strip()
    conversation_id = data.get('conversation_id', 'default-session')
    assessment_id = data.get('assessment_id')
    lang = data.get('lang', session.get('lang', 'en'))
    user_id = session.get('user_id')

    if not user_message and 'image' not in request.files:
        return jsonify({'status': 'error', 'message': 'Message text or image attachment required.'}), 400

    if 'image' in request.files and data.get('image_screening_consent') != 'true':
        return jsonify({
            'status': 'error',
            'message': 'Please allow the Gemini skin-photo suitability check before sending an image.',
        }), 400

    attached_image_path = None
    if 'image' in request.files:
        file = request.files['image']
        if file and file.filename != '':
            upload_folder = current_app.config['UPLOAD_FOLDER']
            os.makedirs(upload_folder, exist_ok=True)
            ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else 'jpg'
            safe_fn = f"chat_{uuid.uuid4().hex}.{ext}"
            attached_image_path = os.path.join(upload_folder, safe_fn)
            file.save(attached_image_path)

    db_path = current_app.config['DATABASE_PATH']

    # Save user message
    save_chat_message(
        db_path=db_path,
        conversation_id=conversation_id,
        role='user',
        content=user_message or '[Image Attached]',
        assessment_id=assessment_id,
        image_attached=attached_image_path,
        user_id=user_id
    )

    session['lang'] = lang

    conversation_service = current_app.config['CONVERSATION_SERVICE']
    
    response_obj = conversation_service.process_chat_message(
        user_message=user_message,
        conversation_id=conversation_id,
        assessment_id=assessment_id,
        attached_image_path=attached_image_path,
        lang=lang
    )

    # Save assistant message
    save_chat_message(
        db_path=db_path,
        conversation_id=conversation_id,
        role='assistant',
        content=response_obj['content'],
        assessment_id=response_obj.get('assessment_referenced'),
        user_id=user_id
    )

    return jsonify({
        'status': 'success',
        'response': response_obj
    })

@chatbot_bp.route('/api/chat/history/<conversation_id>', methods=['GET'])
@login_required
def get_history(conversation_id):
    """GET /api/chat/history/<conversation_id>"""
    db_path = current_app.config['DATABASE_PATH']
    user_id = session.get('user_id')
    is_admin = (session.get('user_role') == 'admin')

    history = get_chat_history(db_path, conversation_id, user_id=user_id, is_admin=is_admin)
    return jsonify({'status': 'success', 'history': history})

@chatbot_bp.route('/api/chat/translate', methods=['POST'])
@login_required
def translate():
    """
    POST /api/chat/translate
    Translate chat text or conversation messages dynamically into target language.
    """
    data = request.get_json(silent=True) or {}
    text = data.get('text', '').strip()
    target_lang = data.get('target_lang', session.get('lang', 'en'))

    if not text:
        return jsonify({'status': 'error', 'message': 'Text is required for translation.'}), 400

    session['lang'] = target_lang
    conversation_service = current_app.config['CONVERSATION_SERVICE']
    translated_text = conversation_service.translate_text(text, target_lang=target_lang)

    return jsonify({
        'status': 'success',
        'target_lang': target_lang,
        'translated_text': translated_text
    })

