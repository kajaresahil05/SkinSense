import os
import sys
import unittest
from unittest.mock import Mock
import io
import json
import numpy as np
from PIL import Image

# Import system modules
from app import create_app
from backend.services.model_service import ModelService
from backend.services.fuzzy_service import FuzzySeverityEngine
from backend.services.conversation_service import ConversationService

class TestSkinSenseSystem(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.base_dir = os.path.abspath(os.path.dirname(__file__))
        cls.model_path = os.path.join(cls.base_dir, 'Dataset2', 'skinsense_dataset2_mobilenetv2.keras')
        cls.config_path = os.path.join(cls.base_dir, 'Dataset2', 'skinsense_dataset2_class_names.json')
        cls.class_path = os.path.join(cls.base_dir, 'models', 'class_labels.json')
        cls.db_path = os.path.join(cls.base_dir, 'backend', 'database', 'skinsense.db')
        
        cls.model_service = ModelService(cls.model_path, cls.config_path, cls.class_path, image_validator=Mock())
        cls.fuzzy_engine = FuzzySeverityEngine()
        cls.conv_service = ConversationService(cls.model_service, cls.fuzzy_engine, cls.db_path)
        
        cls.app = create_app()
        cls.app.config['MODEL_SERVICE'].image_validator = Mock()
        cls.client = cls.app.test_client()

    def setUp(self):
        with self.client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['user_name'] = 'Test Admin'
            sess['user_email'] = 'testadmin@skinsense.org'
            sess['user_role'] = 'admin'
        print("\n[TEST] Verifying PyTorch skin classifier loading...")
        self.assertTrue(self.model_service.is_loaded)
        self.assertIsNotNone(self.model_service.model)

    def test_02_model_inference(self):
        print("[TEST] Running model inference on sample synthetic image...")
        img_path = os.path.join(self.base_dir, 'uploads', 'test_sample.jpg')
        os.makedirs(os.path.dirname(img_path), exist_ok=True)
        img_data = np.random.randint(100, 220, (224, 224, 3), dtype=np.uint8)
        img = Image.fromarray(img_data)
        img.save(img_path)

        res = self.model_service.predict(img_path)
        self.assertEqual(res['status'], 'success')
        self.assertIn('top_prediction', res)
        self.assertEqual(len(res['top_3_predictions']), 3)

    def test_03_fuzzy_severity_engine(self):
        print("[TEST] Testing Fuzzy Logic Severity Engine boundary conditions...")
        res_mild = self.fuzzy_engine.evaluate(itching=1, pain=0, redness=1, duration=2, fever=0, burning=0)
        self.assertGreaterEqual(res_mild['severity_score'], 0.0)
        self.assertLessEqual(res_mild['severity_score'], 100.0)

        res_severe = self.fuzzy_engine.evaluate(itching=9, pain=8, redness=9, duration=30, fever=2, burning=3)
        self.assertGreaterEqual(res_severe['severity_score'], 50.0)

    # --- 9 MANDATORY CHATBOT CONVERSATION TESTS ---

    def test_04_chat_test1_preventive_measures(self):
        print("[TEST CHAT 1] Asking 'Tell me preventive measures'...")
        res = self.conv_service.process_chat_message("Tell me preventive measures.", "test-session-1")
        content = res['content']
        self.assertIn("Simple Answer", content)
        self.assertIn("Preventive", content)
        self.assertNotIn("Thank you for reaching out to SkinSense. I can assist you in understanding", content)

    def test_05_chat_test2_simple_explanation(self):
        print("[TEST CHAT 2] Asking 'Explain my scan result in simple words'...")
        res = self.conv_service.process_chat_message("Explain my scan result in simple words.", "test-session-2")
        content = res['content']
        self.assertTrue("Skin" in content or "Scan" in content or "Result" in content or "Eczema" in content or "No Active Scan" in content)

    def test_06_chat_test3_followup_question(self):
        print("[TEST CHAT 3] Asking follow-up 'What precautions should I take?'...")
        res = self.conv_service.process_chat_message("What precautions should I take?", "test-session-3")
        content = res['content']
        self.assertIn("Simple Answer", content)
        self.assertIn("What You Can Do", content)

    def test_07_chat_test4_general_question(self):
        print("[TEST CHAT 4] Asking 'How can you help me?'...")
        res = self.conv_service.process_chat_message("How can you help me?", "test-session-4")
        content = res['content']
        self.assertIn("Simple Answer", content)
        self.assertIn("What You Can Do", content)

    def test_08_chat_test5_symptom_question(self):
        print("[TEST CHAT 5] Asking 'My skin is itching. What should I do?'...")
        res = self.conv_service.process_chat_message("My skin is itching. What should I do?", "test-session-5")
        content = res['content']
        self.assertIn("Simple Answer", content)
        self.assertIn("itching", content.lower())

    def test_09_chat_test6_confidence_explanation(self):
        print("[TEST CHAT 6] Asking 'What does 16.5% mean?'...")
        res = self.conv_service.process_chat_message("What does 16.5% mean?", "test-session-6")
        content = res['content']
        self.assertIn("Simple Answer", content)
        self.assertTrue("Similarity" in content or "Diagnostic" in content or "Confidence" in content or "16." in content)

    def test_10_chat_test7_missing_scan(self):
        print("[TEST CHAT 7] Asking 'Tell me my latest scan result' in empty session...")
        # Clear session to simulate missing scan
        empty_session_id = "empty-fresh-session-999"
        if empty_session_id in self.conv_service.sessions:
            del self.conv_service.sessions[empty_session_id]
        
        # Override temporary empty DB scan check for isolated test
        res = self.conv_service.process_chat_message("Explain scan result", empty_session_id)
        content = res['content']
        self.assertIn("Scan", content)

    def test_11_chat_test8_unclear_question(self):
        print("[TEST CHAT 8] Asking unclear question 'What about that?'...")
        res = self.conv_service.process_chat_message("What about that?", "test-session-8")
        content = res['content']
        self.assertTrue(len(content) > 10)

    def test_12_chat_test9_repeated_questions(self):
        print("[TEST CHAT 9] Testing consecutive different questions...")
        res1 = self.conv_service.process_chat_message("Tell me preventive measures.", "test-session-9")
        res2 = self.conv_service.process_chat_message("What does 16.5% mean?", "test-session-9")
        res3 = self.conv_service.process_chat_message("How can you help me?", "test-session-9")

        self.assertNotEqual(res1['content'], res2['content'])
        self.assertNotEqual(res2['content'], res3['content'])
        self.assertNotIn("Thank you for reaching out to SkinSense", res1['content'])
        self.assertNotIn("Thank you for reaching out to SkinSense", res2['content'])

    def test_14_all_17_intents_and_informal_phrases(self):
        print("[TEST CHAT 14] Testing informal phrasing & 17 intent coverage...")
        
        # Test 1: Greeting
        r1 = self.conv_service.process_chat_message("hello hey", "intent-session")
        self.assertIn("SkinSense AI Assistant", r1['content'])

        # Test 2: Capabilities with informal phrasing
        r2 = self.conv_service.process_chat_message("how i can help me", "intent-session")
        self.assertIn("Simple Answer", r2['content'])

        # Test 3: Preventive measures with informal phrasing
        r3 = self.conv_service.process_chat_message("tell me preventive measure", "intent-session")
        self.assertIn("Keep Skin Clean", r3['content'])

        # Test 4: Scan explanation
        r4 = self.conv_service.process_chat_message("explain my scan result in simple words", "intent-session")
        self.assertIn("Your Skin Scan Result", r4['content'])

        # Test 5: Confidence score
        r5 = self.conv_service.process_chat_message("what does 16.5% mean?", "intent-session")
        self.assertIn("NOT a Diagnostic Probability", r5['content'])

        # Test 6: Severity score
        r6 = self.conv_service.process_chat_message("what does severity score 28.5 mean?", "intent-session")
        self.assertIn("Fuzzy Logic Engine", r6['content'])

        # Test 7: Follow-up question
        r7 = self.conv_service.process_chat_message("is it dangerous", "intent-session")
        self.assertIn("What You Should Know", r7['content'])

        # Test 8: Emergency signs
        r8 = self.conv_service.process_chat_message("what are emergency warning signs?", "intent-session")
        self.assertIn("ABCDE Rule", r8['content'])

        # Test 9: When to consult dermatologist
        r9 = self.conv_service.process_chat_message("when to consult a dermatologist", "intent-session")
        self.assertIn("Clinical Evaluation", r9['content'])

        # Test 10: Skin disease explanation
        r10 = self.conv_service.process_chat_message("tell me about eczema", "intent-session")
        self.assertIn("Atopic Dermatitis", r10['content'])

        # Test 11: Symptom question
        r11 = self.conv_service.process_chat_message("what should i do for skin redness?", "intent-session")
        self.assertIn("cool, damp compress", r11['content'])

        # Test 12: Skin care & hygiene
        r12 = self.conv_service.process_chat_message("daily skincare routine", "intent-session")
        self.assertIn("Daily Skin Care", r12['content'])

        # Test 13: General skin health
        r13 = self.conv_service.process_chat_message("how to keep skin healthy", "intent-session")
        self.assertIn("Simple Answer", r13['content'])

        # Test 14: Unclear question
        r14 = self.conv_service.process_chat_message("what about that?", "intent-session")
        self.assertIn("Regarding", r14['content'])

        # Test 15: Unrelated question
        r15 = self.conv_service.process_chat_message("what is the weather today?", "intent-session")
        self.assertIn("specifically trained", r15['content'])

        # Test 16: Previous assessment lookup
        r16 = self.conv_service.process_chat_message("lookup ASS-99999", "intent-session")
        self.assertIn("Simple Answer", r16['content'])

    def test_15_multi_turn_context_flow(self):
        print("[TEST CHAT 15] Testing multi-turn context retention flow...")
        session_id = "context-flow-session"
        
        # Turn 1: Attach image / scan result
        sample_img = os.path.join(self.base_dir, 'uploads', 'test_sample.jpg')
        res1 = self.conv_service.process_chat_message("I uploaded a skin image", session_id, attached_image_path=sample_img)
        self.assertIn("Your Skin Scan Result", res1['content'])

        # Turn 2: Follow-up "Explain this in simple words"
        res2 = self.conv_service.process_chat_message("Explain this in simple words", session_id)
        self.assertIn("In Simple Words", res2['content'])

        # Turn 3: Follow-up "What precautions should I take?"
        res3 = self.conv_service.process_chat_message("What precautions should I take?", session_id)
        self.assertIn("Keep Skin Clean", res3['content'])

        # Turn 4: Follow-up "What about itching?"
        res4 = self.conv_service.process_chat_message("What about itching?", session_id)
        self.assertIn("itching", res4['content'].lower())

    def test_16_xai_service_gradcam_generation(self):
        print("\n[TEST XAI 1] Verifying Grad-CAM heatmap & overlay generation...")
        xai_service = self.app.config['XAI_SERVICE']
        self.assertIsNotNone(xai_service.gradcam_engine)

        sample_img = os.path.join(self.base_dir, 'uploads', 'test_sample.jpg')
        res = xai_service.generate_visual_explanation(sample_img, target_class_code='mel', assessment_id='TEST-XAI-01')
        
        self.assertEqual(res['status'], 'success')
        self.assertEqual(res['explanation_method'], 'Grad-CAM (Gradient-weighted Class Activation Mapping)')
        self.assertTrue(os.path.exists(os.path.join(self.base_dir, 'uploads', res['heatmap_filename'])))
        self.assertTrue(os.path.exists(os.path.join(self.base_dir, 'uploads', res['overlay_filename'])))

    def test_17_xai_service_fuzzy_explanation(self):
        print("[TEST XAI 2] Verifying Fuzzy Logic rule activation extraction...")
        xai_service = self.app.config['XAI_SERVICE']
        res = xai_service.get_fuzzy_explanation(itching=8, pain=6, redness=7, duration=14, fever=1, burning=2)
        
        self.assertIn('membership_levels', res)
        self.assertIn('activated_rules', res)
        self.assertGreater(res['total_activated_rules'], 0)
        self.assertIn('defuzzification_method', res)

    def test_18_xai_api_endpoints(self):
        print("[TEST XAI 3] Verifying /api/explain API endpoints...")
        # 1. Status endpoint
        res_status = self.client.get('/api/explain/status')
        self.assertEqual(res_status.status_code, 200)
        status_data = json.loads(res_status.data)
        self.assertEqual(status_data['status'], 'healthy')
        self.assertTrue(status_data['available'])

        # 2. Predict with XAI generation
        sample_img = os.path.join(self.base_dir, 'uploads', 'test_sample.jpg')
        with open(sample_img, 'rb') as f:
            res_pred = self.client.post('/api/predict', data={
                'image': (f, 'test_sample.jpg'),
                'image_screening_consent': 'true',
                'patient_name': 'Test Patient',
                'patient_age': '35',
                'itching': '8',
                'pain': '5',
                'redness': '7',
                'duration_days': '10',
                'fever_level': '1',
                'burning_level': '2'
            }, content_type='multipart/form-data')
        
        self.assertEqual(res_pred.status_code, 200)
        pred_data = json.loads(res_pred.data)
        asm = pred_data['assessment']
        asm_id = asm['id']
        self.assertIsNotNone(asm.get('heatmap_filename'))

        # 3. Retrieve explanation endpoint
        res_exp = self.client.get(f'/api/explain/{asm_id}')
        self.assertEqual(res_exp.status_code, 200)
        exp_data = json.loads(res_exp.data)
        self.assertEqual(exp_data['status'], 'success')
        self.assertIn('visual_explanation', exp_data)
        self.assertIn('fuzzy_explanation', exp_data)

    def test_19_chat_xai_heatmap_intent(self):
        print("[TEST XAI 4] Testing Dialogflow XAI queries ('Explain the highlighted area', 'Why did the AI predict this disease?')...")
        res1 = self.conv_service.process_chat_message("Explain the highlighted area", "xai-chat-session")
        self.assertIn("Grad-CAM", res1['content'])
        self.assertIn("What the Heatmap Means", res1['content'])

        res2 = self.conv_service.process_chat_message("Why did the AI predict this disease?", "xai-chat-session")
        self.assertIn("MobileNetV2", res2['content'])
        self.assertIn("Visual Pattern Match", res2['content'])

    def test_20_multilingual_end_to_end(self):
        print("\n[TEST MULTILINGUAL 1] Verifying multi-language localization across Chat, PDF, and Auth APIs...")
        # 1. Test POST /api/auth/language
        res_lang = self.client.post('/api/auth/language', json={'lang': 'bho'})
        self.assertEqual(res_lang.status_code, 200)
        data_lang = json.loads(res_lang.data)
        self.assertEqual(data_lang['preferred_language'], 'bho')

        # 2. Test Hindi Chat response
        res_hi = self.conv_service.process_chat_message("Tell me preventive measures", "lang-hi-session", lang='hi')
        self.assertIn("सरल उत्तर", res_hi['content'])

        # 3. Test Bhojpuri Chat response
        res_bho = self.conv_service.process_chat_message("Tell me preventive measures", "lang-bho-session", lang='bho')
        self.assertTrue("उत्तर" in res_bho['content'] or "उपाय" in res_bho['content'])

        # 4. Test Localized PDF report generation
        from backend.services.pdf_service import generate_assessment_pdf
        sample_asm = {
            'id': 'TEST-ASM-LANG-01',
            'patient_name': 'Akshat',
            'patient_age': 28,
            'predicted_name': 'Psoriasis',
            'predicted_class': 'psoriasis',
            'model_score': 0.88,
            'is_reliable': True,
            'severity_score': 35.0,
            'severity_category': 'Mild',
            'itching': 4,
            'pain': 2,
            'redness': 3,
            'duration_days': 5,
            'clinical_summary': 'Mild psoriasis lesion with good prognosis.'
        }
        pdf_bho_bytes = generate_assessment_pdf(sample_asm, upload_folder=os.path.join(self.base_dir, 'uploads'), lang='bho')
        self.assertGreater(len(pdf_bho_bytes), 1000)

        pdf_hi_bytes = generate_assessment_pdf(sample_asm, upload_folder=os.path.join(self.base_dir, 'uploads'), lang='hi')
        self.assertGreater(len(pdf_hi_bytes), 1000)

        print("  -> Multi-language end-to-end test passed successfully for English, Hindi, and Bhojpuri!")

    def test_16_chat_translation_all_10_languages(self):
        print("\n[TEST 16] Testing /api/chat/translate across all 10 supported languages...")
        supported_langs = ['en', 'hi', 'mr', 'bho', 'bn', 'ta', 'te', 'gu', 'kn', 'es']
        test_text = "### Simple Answer\nHere are practical, safe preventive measures for skin care."

        for lang in supported_langs:
            res = self.client.post('/api/chat/translate', json={
                'text': test_text,
                'target_lang': lang
            })
            self.assertEqual(res.status_code, 200)
            data = json.loads(res.data)
            self.assertEqual(data['status'], 'success')
            self.assertEqual(data['target_lang'], lang)
            self.assertTrue(len(data['translated_text']) > 0)
        print("  -> All 10 languages successfully translated via /api/chat/translate endpoint!")

if __name__ == '__main__':
    unittest.main()


