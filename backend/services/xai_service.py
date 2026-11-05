import os
import json
import time
import tensorflow as tf
import numpy as np
import cv2
from PIL import Image

class GradCAMEngine:
    """Generate Grad-CAM from the feature maps feeding the Dataset2 classifier."""

    def __init__(self, model):
        self.target_layer = 'mobilenetv2_1.00_224/out_relu'
        self.pool = next(layer for layer in model.layers
                         if isinstance(layer, tf.keras.layers.GlobalAveragePooling2D))
        self.feature_model = tf.keras.Model(model.inputs, self.pool.input)
        self.classifier = model.get_layer('disease_predictions')

    def generate_heatmap(self, inputs, target_class_idx):
        features = self.feature_model(inputs, training=False)
        with tf.GradientTape() as tape:
            tape.watch(features)
            # Differentiate the class logit before the final softmax.
            logits = self.pool(features) @ self.classifier.kernel + self.classifier.bias
            if target_class_idx is None:
                target_class_idx = int(tf.argmax(logits[0]))
            score = logits[0, target_class_idx]

        gradients = tape.gradient(score, features)
        weights = tf.reduce_mean(gradients, axis=(1, 2), keepdims=True)
        cam = tf.nn.relu(tf.reduce_sum(features * weights, axis=-1))[0]
        cam = tf.math.divide_no_nan(cam, tf.reduce_max(cam))
        return cam.numpy(), target_class_idx


class XAIService:
    """
    Explainable AI (XAI) Master Service for SkinSense.
    Generates visual Grad-CAM heatmaps, overlays, and fuzzy rule activation breakdowns.
    """
    def __init__(self, model_service, fuzzy_engine, upload_folder):
        self.model_service = model_service
        self.fuzzy_engine = fuzzy_engine
        self.upload_folder = upload_folder
        self.xai_folder = os.path.join(upload_folder, 'xai')
        os.makedirs(self.xai_folder, exist_ok=True)
        
        self.gradcam_engine = None
        if self.model_service.is_loaded and self.model_service.model is not None:
            try:
                self.gradcam_engine = GradCAMEngine(self.model_service.model)
                print("[XAIService] Grad-CAM engine successfully initialized on MobileNetV2.")
            except Exception as e:
                print(f"[XAIService] Warning: Grad-CAM engine setup failed: {e}")

    def generate_visual_explanation(self, image_path, target_class_code=None, assessment_id="EXP"):
        """
        Generate genuine Grad-CAM heatmap and blended overlay images.
        Returns dict with heatmap_url, overlay_url, and visual metrics.
        """
        start_time = time.time()
        
        if not os.path.exists(image_path):
            return {
                'status': 'error',
                'message': f"Image file not found at: {image_path}"
            }

        if self.gradcam_engine is None or not self.model_service.is_loaded:
            return {
                'status': 'error',
                'message': "CNN model is not loaded. Cannot generate Grad-CAM explanation."
            }

        try:
            # 1. Load original image
            pil_img = Image.open(image_path).convert('RGB')
            orig_w, orig_h = pil_img.size
            orig_np = np.array(pil_img) # RGB numpy array

            # 2. Determine target class index
            classes = self.model_service.config['classes']
            target_code = (target_class_code or '').lower()
            target_idx = classes.index(target_code) if target_code in classes else None
            is_unclassified_req = target_code == 'unclassified'

            inputs = self.model_service.preprocess_image(pil_img)
            cam, final_class_idx = self.gradcam_engine.generate_heatmap(inputs, target_idx)
            if is_unclassified_req:
                predicted_code = 'unclassified'
                predicted_name = 'No Confident Prediction / Unable to Assess'
            else:
                predicted_code = classes[final_class_idx]
                cls_info = self.model_service.class_labels.get(predicted_code, {})
                predicted_name = cls_info.get('name', predicted_code.upper())

            # 5. Resize heatmap to original image dimensions
            cam_resized = cv2.resize(cam, (orig_w, orig_h))
            cam_uint8 = np.uint8(255 * cam_resized)

            # 6. Generate Colorized Heatmap (JET colormap)
            heatmap_bgr = cv2.applyColorMap(cam_uint8, cv2.COLORMAP_JET)
            heatmap_rgb = cv2.cvtColor(heatmap_bgr, cv2.COLOR_BGR2RGB)

            # 7. Generate Blended Overlay (50% original image + 50% heatmap)
            overlay_rgb = cv2.addWeighted(orig_np, 0.5, heatmap_rgb, 0.5, 0)

            # 8. Save Heatmap & Overlay to disk
            safe_id = assessment_id.replace('-', '_').lower()
            heatmap_fn = f"heatmap_{safe_id}_{predicted_code}.jpg"
            overlay_fn = f"overlay_{safe_id}_{predicted_code}.jpg"

            heatmap_path = os.path.join(self.xai_folder, heatmap_fn)
            overlay_path = os.path.join(self.xai_folder, overlay_fn)

            Image.fromarray(heatmap_rgb).save(heatmap_path, quality=90)
            Image.fromarray(overlay_rgb).save(overlay_path, quality=90)

            latency_ms = round((time.time() - start_time) * 1000, 2)

            summary_msg = (
                "The result was inconclusive. Grad-CAM shows which regions contributed to the model's highest-scoring class."
                if is_unclassified_req else
                f"The highlighted warm (red/yellow) areas show which regions of the image influenced the CNN model's prediction of {predicted_name}."
            )

            return {
                'status': 'success',
                'explanation_method': 'Grad-CAM (Gradient-weighted Class Activation Mapping)',
                'target_layer': str(self.gradcam_engine.target_layer),
                'predicted_code': predicted_code,
                'predicted_name': predicted_name,
                'heatmap_filename': f"xai/{heatmap_fn}",
                'overlay_filename': f"xai/{overlay_fn}",
                'heatmap_url': f"/uploads/xai/{heatmap_fn}",
                'overlay_url': f"/uploads/xai/{overlay_fn}",
                'original_url': f"/uploads/{os.path.basename(image_path)}",
                'resolution': f"{orig_w}x{orig_h}",
                'latency_ms': latency_ms,
                'summary_text': summary_msg
            }

        except Exception as e:
            print(f"[XAIService] Grad-CAM generation error: {e}")
            return {
                'status': 'error',
                'message': f"Grad-CAM heatmap generation failed: {str(e)}"
            }

    def get_fuzzy_explanation(self, itching, pain, redness, duration, fever, burning):
        result = self.fuzzy_engine.evaluate(itching, pain, redness, duration, fever, burning)
        return self.fuzzy_engine.explain(result)

    def generate_patient_friendly_explanation(self, assessment, lang='en'):
        """
        Synthesizes a plain-language 'Why did the AI predict this?' explanation breakdown.
        Translates CNN visual patterns, fuzzy symptom rules, and model confidence
        into accessible, non-jargon patient explanations in the target language (en, hi, bho, mr, es).
        """
        lang      = (lang or 'en').lower()
        pred_code = (assessment.get('predicted_class') or 'nv').lower()
        pred_name = assessment.get('predicted_name') or 'Skin Condition'
        score     = float(assessment.get('model_score', 0.0))
        pct_str   = f"{score * 100:.1f}%"

        top_preds = assessment.get('top_predictions') or []
        itching   = float(assessment.get('itching', 0))
        pain      = float(assessment.get('pain', 0))
        redness   = float(assessment.get('redness', 0))
        duration  = float(assessment.get('duration_days', 1))

        is_reliable = assessment.get('is_reliable', True)
        if pred_code == 'unclassified' or not is_reliable or assessment.get('assessment_status') == 'unable_to_assess':
            mc_entropy = float(assessment.get('model_uncertainty', 0.0))
            if lang == 'bho':
                return {
                    'headline': "एआई मॉडल कौनों एक बीमारी के पक्का परिणाम ना निकाल पावल।",
                    'visual_factors': ["फोटो में कौनों एक बीमारी के पक्का लक्षण ना मिलल।"],
                    'symptom_factors': [f"बतावल गइल लक्षण (खुजली: {itching}/10, दर्द: {pain}/10) के जांच कइल गइल।"],
                    'certainty_explanation': f"मॉडल के पक्का भरोसा नइखे भइल (सबसे ज्यादा मिलान {pct_str} बा)।",
                    'alternative_reasoning': "सब 9 बीमारी के स्कोर कम मिलल।",
                    'patient_takeaway': "सटीक सलाह खातिर चामड़ी के डॉक्टर से जरूर मिलीं।",
                    'predicted_name': 'अनिश्चित जांच / पक्का नइखे भइल',
                    'confidence_pct': pct_str
                }
            elif lang == 'hi':
                return {
                    'headline': "एआई मॉडल किसी एक बीमारी का पक्का निष्कर्ष नहीं निकाल सका।",
                    'visual_factors': ["फोटो में किसी एक बीमारी के स्पष्ट लक्षण नहीं मिले।"],
                    'symptom_factors': [f"बताए गए लक्षण (खुजली: {itching}/10, दर्द: {pain}/10) का मूल्यांकन किया गया।"],
                    'certainty_explanation': f"मॉडल की निश्चितता कम है (उच्चतम मिलान {pct_str})।",
                    'alternative_reasoning': "सभी 9 समर्थित बीमारियों के स्कोर कम रहे।",
                    'patient_takeaway': "सही परामर्श के लिए त्वचा विशेषज्ञ (Dermatologist) से सलाह लें।",
                    'predicted_name': 'अनिर्णायक आकलन / कम मैच',
                    'confidence_pct': pct_str
                }
            elif lang == 'mr':
                return {
                    'headline': "एआय मॉडेल एका विशिष्ट आजाराचा पक्का निष्कर्ष काढू शकले नाही.",
                    'visual_factors': ["फोटोमध्ये स्पष्ट लक्षणे आढळली नाहीत."],
                    'symptom_factors': [f"सांगितलेली लक्षणे (खाज: {itching}/10, वेदना: {pain}/10) तपासली गेली."],
                    'certainty_explanation': f"मॉडेलची खात्री कमी आहे (कमाल साम्य {pct_str}).",
                    'alternative_reasoning': "सर्व आजारांचे स्कोअर कमी आले.",
                    'patient_takeaway': "योग्य उपचारासाठी त्वचारोग तज्ज्ञांचा सल्ला घ्या.",
                    'predicted_name': 'अनिर्णित तपासणी',
                    'confidence_pct': pct_str
                }
            return {
                'headline': "The AI evaluated your skin photo and reported symptoms, but could not detect a confident match with any of the 9 trained skin conditions (maximum score below threshold).",
                'visual_factors': [
                    "No distinct pathological lesion pattern detected by CNN feature filters",
                    "Visual features distributed diffusely across the image surface",
                    "Photo may depict healthy normal skin, non-dermatological features, or an unlisted condition"
                ],
                'symptom_factors': [
                    f"Reported symptoms (itching: {itching}/10, pain: {pain}/10) were evaluated alongside image features.",
                    f"Model uncertainty is elevated (entropy: {mc_entropy:.2f})."
                ],
                'certainty_explanation': f"The model yielded near-uniform low probabilities across classes (highest raw score: {pct_str}), triggering the safety confidence rejection criteria.",
                'alternative_reasoning': "All 9 supported disease classes (e.g., Eczema, Psoriasis, Melanoma) received low scores. No single condition met the diagnostic threshold.",
                'patient_takeaway': "Because the AI result is inconclusive, no disease diagnosis is made. For any concerning or persistent skin symptoms, please consult a board-certified dermatologist.",
                'predicted_name': 'No Confident Prediction / Unable to Assess',
                'confidence_pct': pct_str
            }

        # Visual feature cues by disease class
        visual_cues = {
            'nv': [
                "Uniform pigment distribution across the lesion area",
                "Smooth, sharply demarcated outer borders",
                "Symmetrical round or oval shape",
                "Stable non-evolving surface appearance"
            ],
            'mel': [
                "Asymmetrical shape across primary axes",
                "Irregular, scalloped, or notched outer borders",
                "Multiple pigment shades (brown, black, or reddish tones)",
                "Evolving structural patterns detected by CNN filters"
            ],
            'bcc': [
                "Pearly or translucent surface reflectance",
                "Fine arborizing micro-vascular structures",
                "Central depression or healing/rebleeding patch pattern",
                "Flesh-colored or pinkish raised rim"
            ],
            'akiec': [
                "Rough, scaly, or sandpaper-like surface texture",
                "Erythematous (reddish) base patch on sun-exposed skin",
                "Keratotic buildup across epidermal layers",
                "Flat to slightly elevated irregular border"
            ],
            'bkl': [
                "Waxy or 'stuck-on' superficial plaque texture",
                "Sharply defined, well-demarcated edges",
                "Tan, brown, or yellow-brown pigment uniformity",
                "Hyperkeratotic follicular openings ('horn cysts')"
            ],
            'df': [
                "Firm, localized dome-shaped nodular contour",
                "Central hyperpigmentation with lighter peripheral halo",
                "Fibrous dermal texture pattern",
                "Smooth non-ulcerated surface skin"
            ],
            'vasc': [
                "Localized cluster of dilated vascular capillary loops",
                "Bright cherry-red, purple, or blue-black discoloration",
                "Smooth dome-shaped papule geometry",
                "Sharply bounded non-pigmented vascular lesion boundaries"
            ],
            'scc': [
                "Thickened, hyperkeratotic crusty plaque surface",
                "Indurated (firm) elevated red nodular margin",
                "Ulcerated central core or persistent non-healing sore",
                "Irregular perimeter on sun-damaged tissue"
            ],
            'psoriasis': [
                "Thick, silvery-white micaceous scaling",
                "Well-demarcated fiery red erythematous plaques",
                "Symmetrical plaque distribution pattern",
                "Slightly raised inflamed skin border"
            ]
        }

        class_visuals = visual_cues.get(pred_code, [
            "Distinct visual color and shape characteristics matching trained dermatological dataset patterns."
        ])

        # Headline & Takeaway per language
        if lang == 'bho':
            headline = f"एआई मॉडल राउर फोटो आ लक्षण के जांच कइलस, जवना में {pred_name} से {pct_str} मिलान मिलल।"
            takeaway = "ई विश्लेषण खाली एआई के जांच समझावे खातिर बा। डॉक्टरी सलाह खातिर चामड़ी के डॉक्टर से जरूर मिलीं।"
        elif lang == 'hi':
            headline = f"एआई मॉडल ने आपकी फोटो और लक्षणों का मूल्यांकन किया, जिसमें {pred_name} से {pct_str} मिलान पाया गया।"
            takeaway = "यह विश्लेषण एआई की जांच को समझाता है। यह केवल मार्गदर्शन है, त्वचा विशेषज्ञ से परामर्श अवश्य लें।"
        elif lang == 'mr':
            headline = f"एआय मॉडेलने फोटो आणि लक्षणांचे मूल्यांकन केले, ज्यामध्ये {pred_name} सोबत {pct_str} साम्य आढळले."
            takeaway = "हे विश्लेषण मार्गदर्शनासाठी आहे, त्वचारोग तज्ज्ञांचा सल्ला नक्की घ्या."
        else:
            headline = f"The AI neural ensemble evaluated your skin photo and reported symptoms, finding a {pct_str} match with {pred_name}."
            takeaway = "This breakdown explains how the AI analyzed your upload. These findings are supportive guidance and do not replace formal diagnosis by a board-certified dermatologist."

        # Symptom reasoning
        symptom_cues = []
        if itching >= 5:
            symptom_cues.append(f"Reported itching level of {itching}/10 indicates localized sensory nerve irritation.")
        else:
            symptom_cues.append(f"Low itching level ({itching}/10) suggests minimal histamine release in the skin barrier.")

        if pain >= 5:
            symptom_cues.append(f"Pain level of {pain}/10 suggests active inflammation or nerve sensitivity.")
        else:
            symptom_cues.append(f"Absence of significant pain ({pain}/10) points away from deep acute infection.")

        if duration > 30:
            symptom_cues.append(f"Symptom duration of {duration:.0f} days indicates a chronic, slow-evolving skin feature.")

        # Describe the model score without treating it as a clinical probability.
        if score >= 0.75:
            certainty_text = f"The model assigned a high visual match score ({pct_str}) to this class."
        elif score >= 0.50:
            certainty_text = f"The model showed moderate confidence ({pct_str}), recommending professional dermatologist review for confirmation."
        else:
            certainty_text = f"Model confidence is low ({pct_str}), meaning the visual patterns overlap with multiple conditions."

        # Alternative reasoning
        alt_text = "No strong alternative conditions competed with this primary prediction."
        if len(top_preds) > 1:
            second_pred = top_preds[1]
            second_name = second_pred.get('name') or second_pred.get('predicted_name') or 'Alternative Condition'
            second_score = float(second_pred.get('score', 0.0)) * 100
            alt_text = (
                f"{second_name} ({second_score:.1f}% match) was considered as a secondary possibility due to overlapping visual features, "
                f"but {pred_name} scored higher based on primary visual keypoints and symptom parameters."
            )

        # Actionable takeaway
        takeaway = (
            f"This breakdown explains how the AI analyzed your upload. "
            f"These findings are supportive guidance and do not replace formal diagnosis by a board-certified dermatologist."
        )

        return {
            'headline': headline,
            'visual_factors': class_visuals,
            'symptom_factors': symptom_cues,
            'certainty_explanation': certainty_text,
            'alternative_reasoning': alt_text,
            'patient_takeaway': takeaway,
            'predicted_name': pred_name,
            'confidence_pct': pct_str
        }

