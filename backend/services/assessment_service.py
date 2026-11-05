import uuid
import json
from backend.database.db import save_assessment, get_assessment_by_id
from backend.services.personalized_care_service import PersonalizedCareService
from backend.services.image_validation_service import ImageValidationError

class AssessmentService:
    def __init__(self, model_service, fuzzy_engine, db_path, xai_service=None, gemini_client=None):
        self.model_service = model_service
        self.fuzzy_engine = fuzzy_engine
        self.db_path = db_path
        self.xai_service = xai_service
        self.care_service = PersonalizedCareService(db_path, gemini_client=gemini_client)

    def process_full_assessment(self, image_path, filename, patient_info, symptom_vector, user_id=None, body_region='', image_hash=None, lang='en'):
        """
        Orchestrate complete dermatological assessment combining CNN Image Classifier,
        Fuzzy Logic Severity Engine, Explainable AI (XAI) Grad-CAM Engine, Clinical Decision Chain,
        and Personalized Home Care & Medical Knowledge Base Guidance.
        """
        lang = (lang or 'en').lower()
        # Generate Unique Assessment ID
        assessment_id = f"ASS-{uuid.uuid4().hex[:8].upper()}"

        # 1. CNN Model Image Classification
        model_res = self.model_service.predict(image_path)
        if model_res.get('status') == 'error':
            raise ImageValidationError(model_res.get('error_message', 'Image analysis failed.'))

        top_pred = model_res['top_prediction']
        top_3 = model_res['top_3_predictions']
        quality_status = model_res.get('quality_status', 'Optimal quality')
        is_reliable = model_res.get('is_reliable', True)
        uncertainty_data = model_res.get('uncertainty', {})
        entropy = uncertainty_data.get('entropy', 0.0)
        uncertainty_level = uncertainty_data.get('uncertainty_level', 'Low')

        # 2. Fuzzy Logic Severity Assessment
        fuzzy_res = self.fuzzy_engine.evaluate(
            itching=symptom_vector.get('itching', 0),
            pain=symptom_vector.get('pain', 0),
            redness=symptom_vector.get('redness', 0),
            duration=symptom_vector.get('duration', 0),
            fever=symptom_vector.get('fever', 0),
            burning=symptom_vector.get('burning', 0)
        )

        # 3. Explainable AI (XAI) Generation: Grad-CAM & Fuzzy Rule Activation
        xai_visual = None
        fuzzy_exp = self.fuzzy_engine.explain(fuzzy_res)
        if self.xai_service:
            try:
                xai_visual = self.xai_service.generate_visual_explanation(
                    image_path=image_path,
                    target_class_code=top_pred['code'],
                    assessment_id=assessment_id
                )
            except Exception as e:
                print(f"[AssessmentService] Warning: Grad-CAM generation failed: {e}")
                xai_visual = {'status': 'error', 'message': str(e)}

        # 4. Clinical Decision Chain Summary Synthesis
        cond_name = top_pred['name']
        score_pct = f"{top_pred['score'] * 100:.1f}%"
        sev_cat = fuzzy_res['category']
        sev_score = fuzzy_res['severity_score']

        if top_pred.get('is_unclassified') or not is_reliable:
            thresh_pct = f"{self.model_service.config.get('confidence_threshold', 0.40) * 100:.1f}%"
            clinical_summary = (
                "The AI model could not identify any supported skin lesion class with sufficient confidence "
                "(highest match score: {}, below the {} threshold). "
                "The image may depict healthy normal skin, non-dermatological features, or an unlisted condition. "
                "Fuzzy symptom logic calculated a {} severity score of {}/100 based on reported symptoms. "
                "Clinical evaluation by a board-certified dermatologist is recommended for any concerning skin symptoms.".format(
                    score_pct, thresh_pct, sev_cat, sev_score
                )
            )
        else:
            clinical_summary = (
                "Dataset2 MobileNetV2 image analysis indicates visual characteristics matching {} (Model Score: {}, Uncertainty: {} entropy={:.3f}). "
                "Fuzzy symptom logic calculated a {} severity score of {}/100 based on reported symptom intensity. "
                "Patient should monitor lesion and consult a healthcare professional for clinical confirmation.".format(
                    cond_name, score_pct, uncertainty_level, entropy, sev_cat, sev_score
                )
            )

        heatmap_fn = xai_visual.get('heatmap_filename') if xai_visual and xai_visual.get('status') == 'success' else None
        overlay_fn = xai_visual.get('overlay_filename') if xai_visual and xai_visual.get('status') == 'success' else None
        exp_method = xai_visual.get('explanation_method', 'Grad-CAM') if xai_visual else 'Grad-CAM'

        # 5. Personalized Home Care & Knowledge Base Guidance (Reqs 19-28)
        asm_status = 'unable_to_assess' if (top_pred.get('is_unclassified') or not is_reliable) else 'assessed'
        symptom_full = dict(symptom_vector)
        symptom_full['body_region'] = body_region
        care_guidance = self.care_service.get_guidance_for_condition(
            condition_code=top_pred['code'],
            symptom_data=symptom_full,
            lang=lang,
            is_reliable=is_reliable,
            assessment_status=asm_status,
            use_gemini=True
        )

        assessment_record = {
            'id':                assessment_id,
            'user_id':           user_id,
            'request_status':    'success',
            'assessment_status': asm_status,
            'image_filename':    filename,
            'image_hash':        image_hash,
            'body_region':       body_region,
            'predicted_class':   top_pred['code'],
            'predicted_name':    cond_name,
            'model_score':       top_pred['score'],
            'model_id':          getattr(self.model_service, 'MODEL_ID', None),
            'top_predictions':   top_3,
            'top_prediction':    top_pred,
            'quality_status':    quality_status,
            'is_reliable':       bool(is_reliable),
            'model_uncertainty': float(entropy),
            'uncertainty':       uncertainty_data,
            'patient_name':      patient_info.get('name', 'Anonymous'),
            'patient_age':       patient_info.get('age', 0),
            'itching':           symptom_vector.get('itching', 0),
            'pain':              symptom_vector.get('pain', 0),
            'redness':           symptom_vector.get('redness', 0),
            'duration_days':     symptom_vector.get('duration', 0),
            'fever_level':       symptom_vector.get('fever', 0),
            'burning_level':     symptom_vector.get('burning', 0),
            'severity_score':    sev_score,
            'severity_category': sev_cat,
            'contributing_factors': fuzzy_res['contributing_factors'],
            'clinical_summary':  clinical_summary,
            'heatmap_filename':  heatmap_fn,
            'overlay_filename':  overlay_fn,
            'explanation_method': exp_method,
            'fuzzy_explanation': fuzzy_exp,
            'visual_explanation': xai_visual,
            'home_care_and_prevention': care_guidance,
            'knowledge_base':           care_guidance,
            'patient_friendly_xai':     self.xai_service.generate_patient_friendly_explanation({
                'predicted_class': top_pred['code'],
                'predicted_name': cond_name,
                'model_score': top_pred['score'],
                'top_predictions': top_3,
                'itching': symptom_vector.get('itching', 0),
                'pain': symptom_vector.get('pain', 0),
                'redness': symptom_vector.get('redness', 0),
                'duration_days': symptom_vector.get('duration', 0),
                'model_uncertainty': entropy
            }, lang=lang) if self.xai_service else None,
            'decision_chain': {
                'step1_image_analysis': {
                    'predicted_condition': cond_name,
                    'model_score': top_pred['score'],
                    'score_formatted': score_pct,
                    'quality_status': quality_status,
                    'is_reliable': is_reliable,
                    'risk_level': top_pred['risk_level']
                },
                'step2_symptom_assessment': {
                    'patient_name': patient_info.get('name', 'Anonymous'),
                    'patient_age': patient_info.get('age', 0),
                    'symptoms': symptom_vector,
                    'missing_info': None
                },
                'step3_fuzzy_severity': {
                    'severity_score': sev_score,
                    'severity_category': sev_cat,
                    'contributing_factors': fuzzy_res['contributing_factors'],
                    'activated_rules_count': fuzzy_exp.get('total_activated_rules', 0) if fuzzy_exp else 0
                },
                'step4_visual_explanation': {
                    'explanation_method': exp_method,
                    'heatmap_url': xai_visual.get('heatmap_url') if xai_visual and xai_visual.get('status') == 'success' else None,
                    'overlay_url': xai_visual.get('overlay_url') if xai_visual and xai_visual.get('status') == 'success' else None,
                    'summary_text': xai_visual.get('summary_text') if xai_visual and xai_visual.get('status') == 'success' else 'Grad-CAM heatmap not generated.'
                },
                'step5_summary': clinical_summary
            }
        }

        # 6. Save to Persistent Database with user ownership
        save_assessment(self.db_path, assessment_record, user_id=user_id)

        return assessment_record

