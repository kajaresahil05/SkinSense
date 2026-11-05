import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from flask import Flask
from PIL import Image

from backend.database.db import init_db, get_all_assessments, get_review_queue
from backend.routes.prediction import prediction_bp
from backend.services.assessment_service import AssessmentService
from backend.services.conversation_service import ConversationService
from backend.services.image_validation_service import ImageSuitabilityValidator, ImageValidationError


class TestImageSuitability(unittest.TestCase):
    def test_categories_and_failed_service(self):
        client = Mock()
        validator = ImageSuitabilityValidator(client)
        image = Image.new('RGB', (100, 100))
        for category in ('not_skin_photo', 'uncertain'):
            with self.subTest(category=category):
                client.models.generate_content.return_value.text = json.dumps({'category': category})
                with self.assertRaises(ImageValidationError) as rejected:
                    validator.validate(image)
                self.assertEqual(rejected.exception.status_code, 422)
        client.models.generate_content.return_value.text = '{"category": "skin_lesion_photo"}'
        validator.validate(image)
        for reply in ('{}', 'invalid', '[]'):
            client.models.generate_content.return_value.text = reply
            with self.assertRaises(ImageValidationError) as unavailable:
                validator.validate(image)
            self.assertEqual(unavailable.exception.status_code, 503)
        client.models.generate_content.side_effect = TimeoutError
        with self.assertRaises(ImageValidationError) as unavailable:
            validator.validate(image)
        self.assertEqual(unavailable.exception.status_code, 503)
        with self.assertRaises(ImageValidationError):
            ImageSuitabilityValidator(None).validate(image)

    def test_rejected_uploads_create_no_assessment_or_review(self):
        with tempfile.TemporaryDirectory() as folder:
            db = str(Path(folder, 'test.db'))
            uploads = Path(folder, 'uploads')
            uploads.mkdir()
            init_db(db)
            model = Mock()
            service = AssessmentService(model, Mock(), db)
            app = Flask(__name__)
            app.config.update(SECRET_KEY='fixture', DATABASE_PATH=db,
                              UPLOAD_FOLDER=str(uploads), ASSESSMENT_SERVICE=service)
            app.register_blueprint(prediction_bp)
            client = app.test_client()
            with client.session_transaction() as session:
                session.update(user_id=1, user_role='patient')
            def upload(consent):
                data = io.BytesIO()
                image = Image.new('RGB', (100, 100), 'blue')
                image.save(data, format='PNG')
                data.seek(0)
                return client.post('/api/predict', data={
                    'image': (data, 'test.png'), 'image_screening_consent': consent
                })
            self.assertEqual(upload('false').status_code, 400)
            model.predict.assert_not_called()
            for status, code in ((422, 'image_not_suitable'), (503, 'image_validation_unavailable')):
                model.predict.side_effect = ImageValidationError('Screening rejected', code, status)
                response = upload('true')
                self.assertEqual(response.status_code, status)
                self.assertEqual(response.json['error_code'], code)
                self.assertNotIn('assessment', response.json)
                self.assertFalse(list(uploads.iterdir()))
            self.assertFalse(get_all_assessments(db))
            self.assertFalse(get_review_queue(db))

    def test_chat_rejection_does_not_describe_previous_scan(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder, 'image.png')
            Image.new('RGB', (100, 100)).save(path)
            model = Mock()
            model.predict.side_effect = ImageValidationError('Please upload a skin photo.')
            conversation = ConversationService(model, Mock(), str(Path(folder, 'unused.db')), gemini_api_key='')
            result = conversation.process_chat_message('Analyze this', 'fixture', attached_image_path=str(path))
            self.assertEqual(result['content'], 'Please upload a skin photo.')
            self.assertFalse(result['has_image_analysis'])
            self.assertIsNone(result['assessment_referenced'])
