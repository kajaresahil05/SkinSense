import os
import sqlite3
import unittest
import tempfile
from app import create_app
from backend.database.db import init_db, save_assessment, get_all_assessments

class TestDateFiltering(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_date_filter.db")
        init_db(self.db_path)

        # Seed sample assessments with specific created_at dates
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        sample_records = [
            ('ASS-DATE-01', 1, 'mel', 'Melanoma', 0.95, '2026-09-01 08:00:00'),
            ('ASS-DATE-02', 1, 'nv', 'Nevi', 0.88, '2026-09-15 12:30:00'),
            ('ASS-DATE-03', 1, 'bcc', 'Basal Cell Carcinoma', 0.91, '2026-09-27 09:15:00'),
            ('ASS-DATE-04', 1, 'mel', 'Melanoma', 0.82, '2026-09-27 23:59:00'),
            ('ASS-DATE-05', 1, 'akiec', 'Actinic Keratosis', 0.79, '2026-10-04 11:00:00'),
        ]

        for aid, uid, pclass, pname, score, created_at in sample_records:
            c.execute('''
                INSERT INTO assessments (
                    id, user_id, predicted_class, predicted_name, model_score, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
            ''', (aid, uid, pclass, pname, score, created_at))

        conn.commit()
        conn.close()

        self.app = create_app()
        self.app.config['TESTING'] = True
        self.app.config['DATABASE_PATH'] = self.db_path
        self.client = self.app.test_client()

    def tearDown(self):
        self.temp_dir.cleanup()

    def _login(self, user_id=1, role='patient'):
        with self.client.session_transaction() as sess:
            sess['user_id'] = user_id
            sess['user_name'] = 'Test User'
            sess['user_email'] = 'testuser@example.com'
            sess['user_role'] = role

    def test_01_all_records_no_dates(self):
        self._login()
        res = self.client.get('/api/history')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data['count'], 5)

    def test_02_filter_date_from_only(self):
        self._login()
        # From 2026-09-27 onwards (should return 3 records: ASS-DATE-03, ASS-DATE-04, ASS-DATE-05)
        res = self.client.get('/api/history?date_from=2026-09-27')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        ids = [a['id'] for a in data['assessments']]
        self.assertEqual(data['count'], 3)
        self.assertIn('ASS-DATE-03', ids)
        self.assertIn('ASS-DATE-04', ids)
        self.assertIn('ASS-DATE-05', ids)
        self.assertNotIn('ASS-DATE-01', ids)

    def test_03_filter_date_to_only(self):
        self._login()
        # Up to 2026-09-15 (should return 2 records: ASS-DATE-01, ASS-DATE-02)
        res = self.client.get('/api/history?date_to=2026-09-15')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        ids = [a['id'] for a in data['assessments']]
        self.assertEqual(data['count'], 2)
        self.assertIn('ASS-DATE-01', ids)
        self.assertIn('ASS-DATE-02', ids)
        self.assertNotIn('ASS-DATE-03', ids)

    def test_04_filter_both_dates_inclusive(self):
        self._login()
        # From 2026-09-15 to 2026-09-27 inclusive (should return 3 records: ASS-DATE-02, ASS-DATE-03, ASS-DATE-04)
        res = self.client.get('/api/history?date_from=2026-09-15&date_to=2026-09-27')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        ids = [a['id'] for a in data['assessments']]
        self.assertEqual(data['count'], 3)
        self.assertIn('ASS-DATE-02', ids)
        self.assertIn('ASS-DATE-03', ids)
        self.assertIn('ASS-DATE-04', ids)
        self.assertNotIn('ASS-DATE-01', ids)
        self.assertNotIn('ASS-DATE-05', ids)

    def test_05_single_day_boundary_inclusion(self):
        self._login()
        # Single day range 2026-09-27 to 2026-09-27 (should return ASS-DATE-03 and ASS-DATE-04)
        res = self.client.get('/api/history?date_from=2026-09-27&date_to=2026-09-27')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        ids = [a['id'] for a in data['assessments']]
        self.assertEqual(data['count'], 2)
        self.assertIn('ASS-DATE-03', ids)
        self.assertIn('ASS-DATE-04', ids)

    def test_06_combine_dates_with_search_and_class_filter(self):
        self._login()
        # date_from=2026-09-01 & class_filter=mel -> should return ASS-DATE-01 & ASS-DATE-04
        res = self.client.get('/api/history?date_from=2026-09-01&class_filter=mel')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        ids = [a['id'] for a in data['assessments']]
        self.assertEqual(data['count'], 2)
        self.assertIn('ASS-DATE-01', ids)
        self.assertIn('ASS-DATE-04', ids)

        # Combine with search_query
        res_search = self.client.get('/api/history?date_from=2026-09-01&search=Basal')
        self.assertEqual(res_search.status_code, 200)
        data_search = res_search.get_json()
        ids_search = [a['id'] for a in data_search['assessments']]
        self.assertEqual(data_search['count'], 1)
        self.assertEqual(ids_search[0], 'ASS-DATE-03')

    def test_07_empty_result_range(self):
        self._login()
        # Range with no records
        res = self.client.get('/api/history?date_from=2025-01-01&date_to=2025-01-31')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data['count'], 0)
        self.assertEqual(data['assessments'], [])

    def test_08_invalid_date_formats_gracefully_handled(self):
        self._login()
        # Invalid date strings should be ignored gracefully
        res = self.client.get('/api/history?date_from=invalid-date&date_to=undefined')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data['count'], 5)

if __name__ == '__main__':
    unittest.main()
