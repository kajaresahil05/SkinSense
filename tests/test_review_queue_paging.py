import tempfile
import unittest
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path

from flask import Flask

from backend.database.db import get_db_connection, init_db
from backend.routes.review import review_bp


class TestReviewQueuePaging(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.db = str(Path(self.folder.name, 'test.db'))
        init_db(self.db)
        start = datetime(2026, 1, 1)
        rows = [
            (f'ASS-{i:04d}', 1, 'nv', 'Melanocytic nevus', .8,
             (start + timedelta(minutes=i)).strftime('%Y-%m-%d %H:%M:%S'))
            for i in range(105)
        ]
        with closing(get_db_connection(self.db)) as conn, conn:
            conn.executemany(
                'INSERT INTO assessments (id, user_id, predicted_class, predicted_name, model_score, created_at) VALUES (?, ?, ?, ?, ?, ?)',
                rows
            )
        app = Flask(__name__)
        app.config.update(SECRET_KEY='fixture', DATABASE_PATH=self.db)
        app.register_blueprint(review_bp)
        self.client = app.test_client()
        with self.client.session_transaction() as session:
            session.update(user_id=1, user_role='admin')

    def test_latest_report_is_first_and_every_report_can_be_loaded(self):
        loaded = []
        offset = 0
        while True:
            page = self.client.get(f'/api/review/queue?limit=50&offset={offset}').json
            self.assertEqual(page['total_count'], 105)
            self.assertEqual(page['pending_count'], 105)
            loaded.extend(row['assessment_id'] for row in page['items'])
            if not page['has_more']:
                break
            offset = page['next_offset']
        self.assertEqual(loaded, [f'ASS-{i:04d}' for i in reversed(range(105))])

    def test_search_and_priority_filter_apply_before_pagination(self):
        self.client.get('/api/review/queue')
        with closing(get_db_connection(self.db)) as conn, conn:
            conn.execute("UPDATE review_queue SET priority='urgent' WHERE assessment_id='ASS-0000'")
        search = self.client.get('/api/review/queue?search=ass-0000').json
        self.assertEqual(search['total_count'], 1)
        self.assertEqual(search['items'][0]['assessment_id'], 'ASS-0000')
        priority = self.client.get('/api/review/queue?priority=urgent').json
        self.assertEqual(priority['total_count'], 1)
        latest = self.client.get('/api/review/queue?limit=1').json
        self.assertEqual(latest['items'][0]['assessment_id'], 'ASS-0104')

    def test_invalid_page_parameters_are_rejected(self):
        response = self.client.get('/api/review/queue?offset=bad')
        self.assertEqual(response.status_code, 400)
