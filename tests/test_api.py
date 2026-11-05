import os
import io
import json
import unittest
from unittest.mock import Mock
import tempfile
from app import create_app
from PIL import Image

class TestAPIEndpointsAndAuthentication(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_skinsense.db")
        
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.app.config['MODEL_SERVICE'].image_validator = Mock()
        self.app.config['DATABASE_PATH'] = self.db_path
        
        from backend.database.db import init_db
        init_db(self.db_path)

        self.client = self.app.test_client()

    def tearDown(self):
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_01_unauthenticated_requests_blocked(self):
        """Verify unauthenticated requests return 401/403."""
        res_predict = self.client.post('/api/predict')
        self.assertEqual(res_predict.status_code, 401)

        res_history = self.client.get('/api/history')
        self.assertEqual(res_history.status_code, 401)

        res_analytics = self.client.get('/api/analytics')
        self.assertIn(res_analytics.status_code, [401, 403])

    def test_02_patient_registration_and_login_flow(self):
        """Verify registration, login, profile check, and logout."""
        test_email = f"patient_{os.urandom(4).hex()}@example.com"
        
        # 1. Register new patient
        reg_res = self.client.post('/api/auth/register', json={
            'full_name': 'Jane Patient',
            'email': test_email,
            'password': 'Password123!',
            'confirm_password': 'Password123!'
        })
        self.assertEqual(reg_res.status_code, 200)
        reg_data = reg_res.get_json()
        self.assertEqual(reg_data['status'], 'success')
        self.assertEqual(reg_data['user']['role'], 'patient')

        # 2. Check profile (/api/auth/me)
        me_res = self.client.get('/api/auth/me')
        self.assertEqual(me_res.status_code, 200)
        me_data = me_res.get_json()
        self.assertTrue(me_data['authenticated'])
        self.assertEqual(me_data['user']['email'], test_email)

        # 3. Patient cannot access admin analytics (/api/analytics)
        analytics_res = self.client.get('/api/analytics')
        self.assertEqual(analytics_res.status_code, 403)

        # 4. Logout
        logout_res = self.client.post('/api/auth/logout')
        self.assertEqual(logout_res.status_code, 200)

        # 5. Check profile after logout
        me_after = self.client.get('/api/auth/me').get_json()
        self.assertFalse(me_after['authenticated'])

    def test_03_invalid_login_credentials(self):
        """Verify invalid credentials return 401."""
        res = self.client.post('/api/auth/login', json={
            'email': 'nonexistent@example.com',
            'password': 'WrongPassword'
        })
        self.assertEqual(res.status_code, 401)

    def test_04_admin_authentication_and_analytics_access(self):
        """Verify default administrator login and access to admin analytics."""
        admin_res = self.client.post('/api/auth/admin-login', json={
            'email': 'admin@skinsense.org',
            'password': 'Admin@SkinSense2026'
        })
        self.assertEqual(admin_res.status_code, 200)
        admin_data = admin_res.get_json()
        self.assertEqual(admin_data['user']['role'], 'admin')

        # Admin can access analytics endpoint
        analytics_res = self.client.get('/api/analytics')
        self.assertEqual(analytics_res.status_code, 200)
        analytics_data = analytics_res.get_json()
        self.assertEqual(analytics_data['status'], 'success')

    def test_05_authenticated_prediction_and_history(self):
        """Verify authenticated patient can upload photo and retrieve their own history."""
        with self.client.session_transaction() as sess:
            sess['user_id'] = 'TEST-PATIENT-SESSION-01'
            sess['user_name'] = 'Test Patient'
            sess['user_email'] = 'testpatient@example.com'
            sess['user_role'] = 'patient'

        health_res = self.client.get('/api/health')
        self.assertEqual(health_res.status_code, 200)

        img = Image.new('RGB', (224, 224), color='red')
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='JPEG')
        img_bytes.seek(0)

        data = {
            'image': (img_bytes, 'test.jpg'),
            'patient_name': 'Test Patient',
            'patient_age': '30',
            'itching': '4',
            'pain': '2',
            'redness': '3',
            'duration_days': '5',
            'fever_level': '0',
            'image_screening_consent': 'true',
            'burning_level': '0'
        }

        res = self.client.post('/api/predict', data=data, content_type='multipart/form-data')
        self.assertEqual(res.status_code, 200)
        json_data = res.get_json()
        self.assertEqual(json_data['status'], 'success')

        history_res = self.client.get('/api/history')
        self.assertEqual(history_res.status_code, 200)

    def test_multilingual_guidance_all_10_languages(self):
        languages = ['en', 'hi', 'mr', 'bho', 'bn', 'ta', 'te', 'gu', 'kn', 'es']
        for lang in languages:
            res = self.client.get(f'/api/conditions/knowledge/psoriasis?lang={lang}')
            self.assertEqual(res.status_code, 200)
            data = res.get_json()
            self.assertEqual(data['status'], 'success')
            guidance = data['guidance']
            self.assertIn('doctor_consultation_mandatory', guidance)
            self.assertTrue(len(guidance['doctor_consultation_mandatory']) > 20)

        # Test POST personalized-guidance with language
        payload = {
            'condition_code': 'psoriasis',
            'itching': 8,
            'pain': 7,
            'duration_days': 40,
            'is_spreading': True,
            'lang': 'bho'
        }
        res_post = self.client.post('/api/conditions/personalized-guidance', json=payload)
        self.assertEqual(res_post.status_code, 200)
        data_post = res_post.get_json()
        self.assertEqual(data_post['status'], 'success')
        self.assertIn('doctor_consultation_mandatory', data_post['guidance'])


if __name__ == '__main__':
    unittest.main()
