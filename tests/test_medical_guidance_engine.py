"""
SkinSense — Test Medical Guidance Engine v2.0
Validates condition-aware, evidence-based, severity-aware, symptom-aware, and multilingual medical guidance.
"""
import os
import json
from unittest.mock import Mock
import unittest
import tempfile
from backend.database.db import init_db
from backend.services.personalized_care_service import PersonalizedCareService

class TestMedicalGuidanceEngine(unittest.TestCase):
    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix='.db')
        os.close(self.db_fd)
        init_db(self.db_path)
        self.care_service = PersonalizedCareService(self.db_path)

    def tearDown(self):
        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except OSError:
                pass

    def test_all_11_conditions_coverage(self):
        """Verify knowledge profiles exist for all 11 conditions in all 4 supported languages."""
        conditions = ['akiec', 'bcc', 'bkl', 'df', 'mel', 'nv', 'vasc', 'eczema', 'psoriasis', 'scc', 'unclassified']
        languages = ['en', 'hi', 'bho', 'mr']

        for cond in conditions:
            for lang in languages:
                guidance = self.care_service.get_guidance_for_condition(cond, lang=lang)
                self.assertIsNotNone(guidance, f"Guidance for {cond} ({lang}) should not be None")
                self.assertIn('condition_name', guidance)
                self.assertIn('supportive_care', guidance)
                self.assertIn('preventive_measures', guidance)
                self.assertIn('things_to_avoid', guidance)
                self.assertIn('when_to_see_doctor', guidance)
                self.assertIn('urgent_warning_signs', guidance)
                self.assertTrue(len(guidance['supportive_care']) > 0, f"Supportive care for {cond} ({lang}) must not be empty")

    def test_tinea_uses_sourced_guidance_and_keeps_the_area_dry(self):
        guidance = self.care_service.get_guidance_for_condition(
            'tinea', symptom_data={'itching': 8, 'pain': 7, 'is_spreading': True}, lang='en'
        )
        self.assertEqual(guidance['condition_code'], 'tinea')
        self.assertTrue(guidance['is_approved_kb'])
        self.assertTrue(guidance['references'])
        care = ' '.join(guidance['supportive_care']).lower()
        self.assertIn('pat it dry', care)
        self.assertNotIn('damp compress', care)
        self.assertNotIn('petrolatum', care)
        self.assertIn('ALERT', guidance['urgent_warning_signs'][0])

    def test_gemini_rewrites_only_care_and_prevention(self):
        original = self.care_service.get_guidance_for_condition('tinea')
        client = Mock()
        client.models.generate_content.return_value.text = json.dumps({
            'supportive_care': ['Gently clean and dry the area.', 'Change out of damp clothing.'],
            'preventive_measures': ['Use your own towels if ringworm is suspected.', 'Wear sandals in shared showers.'],
        })
        self.care_service.gemini_client = client
        result = self.care_service.get_guidance_for_condition('tinea', use_gemini=True)
        self.assertEqual(result['guidance_source'], 'gemini')
        self.assertNotEqual(result['supportive_care'], original['supportive_care'])
        for key in ('things_to_avoid', 'medical_treatment_info', 'references', 'urgent_warning_signs',
                    'when_to_see_doctor', 'doctor_consultation_mandatory'):
            self.assertEqual(result[key], original[key])

    def test_gemini_failure_and_invalid_content_use_original_guidance(self):
        original = self.care_service.get_guidance_for_condition('tinea')
        client = Mock()
        self.care_service.gemini_client = client
        client.models.generate_content.side_effect = TimeoutError
        self.assertEqual(self.care_service.get_guidance_for_condition('tinea', use_gemini=True), original)
        client.models.generate_content.side_effect = None
        client.models.generate_content.return_value.text = '{"supportive_care": ["<script>bad</script>", "Text"], "preventive_measures": ["Text", "Text"]}'
        self.assertEqual(self.care_service.get_guidance_for_condition('tinea', use_gemini=True), original)

    def test_inconclusive_and_unknown_guidance_skip_gemini(self):
        client = Mock()
        self.care_service.gemini_client = client
        rejected = self.care_service.get_guidance_for_condition('tinea', is_reliable=False, use_gemini=True)
        missing = self.care_service.get_guidance_for_condition('missing', use_gemini=True)
        self.assertEqual(rejected['condition_code'], 'unclassified')
        self.assertEqual(missing['guidance_source'], 'general_fallback')
        client.models.generate_content.assert_not_called()

    def test_unclassified_rejection_state(self):
        """Verify rejected/unreliable predictions route to unclassified profile and never claim disease or healthy cure."""
        # Test direct call to unclassified
        guidance = self.care_service.get_guidance_for_condition('unclassified', lang='en')
        self.assertIn("No Confident Prediction", guidance['condition_name'])
        self.assertIn("No specific skin condition was diagnosed", guidance['condition_explanation'])
        
        # Test routing via is_reliable=False on a disease code (e.g., mel)
        rejected_guidance = self.care_service.get_guidance_for_condition('mel', is_reliable=False, assessment_status='unable_to_assess', lang='en')
        self.assertEqual(rejected_guidance['condition_code'], 'unclassified')
        self.assertNotIn("melanoma treatment", " ".join(rejected_guidance['supportive_care']).lower())

    def test_serious_malignant_conditions_safety(self):
        """Verify serious conditions (mel, bcc, akiec, scc) do not present home care as a cure and mandate dermatologist consultation."""
        for serious_code in ['mel', 'bcc', 'akiec', 'scc']:
            guidance = self.care_service.get_guidance_for_condition(serious_code, lang='en')
            supportive_text = " ".join(guidance['supportive_care']).lower()
            self.assertNotIn("cure", supportive_text)
            self.assertNotIn("treat cancer at home", supportive_text)
            self.assertTrue(any("dermatologist" in item.lower() or "medical" in item.lower() for item in guidance['when_to_see_doctor']))

    def test_dynamic_symptom_adaptation(self):
        """Verify reported symptoms (itching, pain, spreading, discharge) dynamically modify guidance bullets."""
        symptoms_high = {
            'itching': 8,
            'pain': 7,
            'is_spreading': True,
            'has_discharge': True,
            'is_cracked_bleeding': True
        }
        guidance = self.care_service.get_guidance_for_condition('eczema', symptom_data=symptoms_high, lang='en')
        supportive_text = " ".join(guidance['supportive_care']).lower()
        self.assertIn("compress", supportive_text)
        self.assertTrue(any("discharge" in item.lower() or "cracked" in item.lower() or "spreading" in item.lower() for item in guidance['urgent_warning_signs']))

    def test_bhojpuri_multilingual(self):
        """Verify Bhojpuri language translations return non-empty localized strings."""
        guidance_bho = self.care_service.get_guidance_for_condition('psoriasis', lang='bho')
        self.assertEqual(guidance_bho['condition_code'], 'psoriasis')
        self.assertTrue(len(guidance_bho['supportive_care']) > 0)
        self.assertTrue(any("चमड़ी" in item or "डॉक्टर" in item or "सफाई" in item or "पानी" in item for item in guidance_bho['supportive_care']))

if __name__ == '__main__':
    unittest.main()
