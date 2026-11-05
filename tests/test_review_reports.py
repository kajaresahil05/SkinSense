import tempfile
import time
from unittest.mock import patch
import unittest
from pathlib import Path

from flask import Flask, send_from_directory
from PIL import Image
from itsdangerous import URLSafeTimedSerializer

from backend.database.db import init_db, save_assessment, get_assessment_by_id
from backend.routes.report import report_bp
from backend.routes.review import review_bp


class TestReviewReports(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        root = Path(self.folder.name)
        self.uploads = root / 'uploads'
        self.uploads.mkdir()
        self.db = str(root / 'test.db')
        init_db(self.db)
        Image.new('RGB', (80, 80), (150, 100, 80)).save(self.uploads / 'skin.png')
        for scan in ('ASS-ONE', 'ASS-TWO'):
            save_assessment(self.db, {
                'id': scan, 'patient_name': 'Fixture patient', 'patient_age': 35,
                'image_filename': 'skin.png', 'predicted_class': 'nv',
                'predicted_name': 'Melanocytic nevus', 'model_score': 0.85,
                'itching': 2, 'clinical_summary': 'Synthetic test report.',
            }, user_id=1)
        self.app = Flask(__name__)
        self.app.config.update(SECRET_KEY='test-key', DATABASE_PATH=self.db, UPLOAD_FOLDER=str(self.uploads))
        self.app.register_blueprint(review_bp)
        self.app.register_blueprint(report_bp)

        @self.app.route('/uploads/<path:filename>')
        def uploaded_file(filename):
            return send_from_directory(str(self.uploads), filename)

        self.client = self.app.test_client()
        with self.client.session_transaction() as session:
            session.update(user_id=1, user_role='admin')
        queue = self.client.get('/api/review/queue').json['queue']
        self.cases = {item['assessment_id']: item['id'] for item in queue}
        self.endpoint = f"/api/review/queue/{self.cases['ASS-ONE']}"

    def test_report_contains_assessment_and_downloadable_pdf_with_missing_entropy(self):
        data = self.client.get(self.endpoint).json
        self.assertEqual(data['report']['id'], 'ASS-ONE')
        self.assertEqual(data['report']['patient_age'], 35)
        self.assertEqual(data['report']['itching'], 2)
        self.assertEqual(self.client.get(data['report_assets']['image_filename']).status_code, 200)
        self.assertIsNone(data['report_assets']['overlay_filename'])
        response = self.client.get(data['report_download_url'])
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data.startswith(b'%PDF'))

    def test_verdict_requires_report_confirmation_and_matching_token(self):
        verdict = {'diagnosis': 'Fixture verdict', 'verdict_category': 'reviewed'}
        self.assertEqual(self.client.post(self.endpoint + '/verdict', json=verdict).status_code, 400)
        data = self.client.get(self.endpoint).json
        verdict['report_review_token'] = data['report_review_token']
        self.assertEqual(self.client.post(self.endpoint + '/verdict', json=verdict).status_code, 400)
        verdict['report_reviewed'] = True
        other = f"/api/review/queue/{self.cases['ASS-TWO']}/verdict"
        self.assertEqual(self.client.post(other, json=verdict).status_code, 400)
        invalid = dict(verdict, report_review_token='invalid')
        self.assertEqual(self.client.post(self.endpoint + '/verdict', json=invalid).status_code, 400)
        signer = URLSafeTimedSerializer(self.app.secret_key, salt='review-report')
        claims = {'queue_id': str(self.cases['ASS-ONE']), 'assessment_id': 'ASS-ONE', 'admin_id': 999}
        other_admin = dict(verdict, report_review_token=signer.dumps(claims))
        self.assertEqual(self.client.post(self.endpoint + '/verdict', json=other_admin).status_code, 400)
        claims['admin_id'] = 1
        past = time.time() - 3600
        with patch('itsdangerous.timed.time.time', return_value=past):
            expired_token = signer.dumps(claims)
        expired = dict(verdict, report_review_token=expired_token)
        self.assertEqual(self.client.post(self.endpoint + '/verdict', json=expired).status_code, 400)
        self.assertEqual(self.client.post(self.endpoint + '/verdict', json=verdict).status_code, 200)
        self.assertEqual(get_assessment_by_id(self.db, 'ASS-ONE')['dermatologist_diagnosis'], 'Fixture verdict')

    def test_patient_cannot_access_review_report(self):
        with self.client.session_transaction() as session:
            session['user_role'] = 'patient'
        self.assertEqual(self.client.get(self.endpoint).status_code, 403)
