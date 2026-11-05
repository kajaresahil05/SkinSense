import unittest
from backend.services.fuzzy_service import FuzzySeverityEngine

class TestFuzzyEngine(unittest.TestCase):
    def setUp(self):
        self.fuzzy_engine = FuzzySeverityEngine()

    def test_fuzzy_mild_symptoms(self):
        res = self.fuzzy_engine.evaluate(itching=1, pain=0, redness=1, duration=2, fever=0, burning=0)
        self.assertTrue(0.0 <= res['severity_score'] <= 100.0)
        self.assertEqual(res['category'], 'Mild')

    def test_fuzzy_severe_symptoms(self):
        res = self.fuzzy_engine.evaluate(itching=9, pain=8, redness=9, duration=30, fever=2, burning=3)
        self.assertGreaterEqual(res['severity_score'], 70.0)
        self.assertEqual(res['category'], 'High')
        self.assertGreater(len(res['contributing_factors']), 0)

    def test_fuzzy_input_clamping(self):
        res = self.fuzzy_engine.evaluate(itching=15, pain=-5, redness=20, duration=100, fever=5, burning=10)
        self.assertTrue(0.0 <= res['severity_score'] <= 100.0)

    def test_redness_cannot_dilute_high_pain(self):
        pain_only = self.fuzzy_engine.evaluate(0, 10, 0, 0, 0, 0)
        with_redness = self.fuzzy_engine.evaluate(0, 10, 10, 0, 0, 0)
        self.assertEqual(with_redness['category'], 'High')
        self.assertGreaterEqual(with_redness['severity_score'], pain_only['severity_score'])

    def test_high_fever_and_severe_burning_reach_review_threshold(self):
        for fever, burning in [(2, 0), (0, 3)]:
            with self.subTest(fever=fever, burning=burning):
                result = self.fuzzy_engine.evaluate(0, 0, 0, 0, fever, burning)
                self.assertEqual(result['category'], 'High')

    def test_explanation_matches_score(self):
        result = self.fuzzy_engine.evaluate(8, 6, 7, 14, 1, 2)
        explanation = self.fuzzy_engine.explain(result)
        self.assertEqual(explanation['severity_score'], result['severity_score'])
        self.assertEqual(explanation['severity_category'], result['category'])
        self.assertEqual(explanation['activated_rules'][0]['score_contribution'], result['severity_score'])

if __name__ == '__main__':
    unittest.main()

