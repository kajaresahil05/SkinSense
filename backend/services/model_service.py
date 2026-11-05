"""Inference for the Dataset2 Keras MobileNetV2 classifier."""
import json

import numpy as np
import tensorflow as tf
from PIL import Image

from training.preprocess import validate_image_quality
from backend.services.image_validation_service import ImageSuitabilityValidator


class ModelService:
    MODEL_ID = 'dataset2-mobilenetv2-keras'
    MODEL_NAME = 'Dataset2 Keras MobileNetV2'
    INPUT_SIZE = (224, 224)
    CLASS_CODES = {
        'Actinic keratosis': 'akiec',
        'Atopic Dermatitis': 'eczema',
        'Benign keratosis': 'bkl',
        'Dermatofibroma': 'df',
        'Melanocytic nevus': 'nv',
        'Melanoma': 'mel',
        'Squamous cell carcinoma': 'scc',
        'Tinea Ringworm Candidiasis': 'tinea',
        'Vascular lesion': 'vasc',
    }

    def __init__(self, model_path, class_names_path, class_labels_path, image_validator=None):
        self.image_validator = image_validator or ImageSuitabilityValidator(None)
        self.model = None
        self.is_loaded = False
        self.device = 'GPU' if tf.config.list_physical_devices('GPU') else 'CPU'
        self.config = {'confidence_threshold': 0.25, 'classes': []}
        self.class_labels = {}

        try:
            with open(class_names_path, encoding='utf-8') as file:
                names = json.load(file)
            if len(names) != len(self.CLASS_CODES) or set(names) != self.CLASS_CODES.keys():
                raise ValueError('Unexpected Dataset2 class labels.')
            classes = [self.CLASS_CODES[name] for name in names]

            with open(class_labels_path, encoding='utf-8') as file:
                descriptions = json.load(file)
            self.class_labels = {
                code: {**descriptions.get(code, {}), 'name': name}
                for code, name in zip(classes, names)
            }

            self.config['classes'] = classes
            model = tf.keras.models.load_model(model_path, compile=False)
            if model.input_shape[1:] != (*self.INPUT_SIZE, 3) or model.output_shape[-1] != len(classes):
                raise ValueError('Dataset2 checkpoint input or output shape does not match its metadata.')

            self.model = model
            self.is_loaded = True
            print(f"[ModelService] Dataset2 Keras MobileNetV2 loaded on {self.device}")
        except (OSError, ValueError, TypeError) as exc:
            print(f"[ModelService] Failed to load the Dataset2 checkpoint: {exc}")

    def preprocess_image(self, image):
        # The checkpoint rescales RGB pixels internally from [0, 255] to [-1, 1].
        image = image.convert('RGB').resize(self.INPUT_SIZE, Image.Resampling.BILINEAR)
        return tf.convert_to_tensor(np.asarray(image, dtype=np.float32)[None, ...])

    def predict(self, image_path):
        if not self.is_loaded:
            raise RuntimeError("Skin disease classification model is not available.")

        is_valid, quality_msg = validate_image_quality(image_path)
        if not is_valid:
            return {'status': 'error', 'error_message': quality_msg, 'is_reliable': False}

        with Image.open(image_path) as image:
            self.image_validator.validate(image)
            inputs = self.preprocess_image(image)
        probabilities = self.model(inputs, training=False).numpy()[0]
        entropy = float(-np.sum(probabilities * np.log(np.maximum(probabilities, 1e-8))))
        classes = self.config['classes']

        sorted_indices = probabilities.argsort()[::-1]

        top_predictions = []
        for idx in sorted_indices[:3]:
            cls_code = classes[idx]
            cls_info = self.class_labels.get(cls_code, {})
            prob_val = float(probabilities[idx])

            top_predictions.append({
                'code':                   cls_code,
                'name':                   cls_info.get('name', cls_code.upper()),
                'full_name':              cls_info.get('full_name', cls_code),
                'category':               cls_info.get('category', 'Dermatological Condition'),
                'score':                  round(prob_val, 4),
                'risk_level':             cls_info.get('risk_level', 'Unknown'),
                'description':            cls_info.get('description', ''),
                'recommendation':         cls_info.get('recommendation', '')
            })

        top_match = top_predictions[0]

        # ── 7. Reliability Assessment ──
        threshold = self.config['confidence_threshold']

        # High entropy (confused model) → unreliable even if top score is OK
        is_reliable = bool(
            top_match['score'] >= threshold
            and entropy < 1.5
        )

        # Uncertainty classification (tighter bands for medical context)
        if entropy < 0.5:
            uncertainty_level = 'Low'
        elif entropy < 1.0:
            uncertainty_level = 'Medium'
        elif entropy < 1.5:
            uncertainty_level = 'High'
        else:
            uncertainty_level = 'Very High'

        # ── 8. Inconclusive Assessment for very low confidence ──
        if not is_reliable:
            raw_top_code  = top_match['code']
            raw_top_name  = top_match['name']
            raw_top_score = float(top_match['score'])

            top_match = {
                'code':        'unclassified',
                'name':        'Inconclusive Assessment',
                'full_name':   'Low Confidence Image Assessment',
                'category':    'Inconclusive Assessment',
                'score':       raw_top_score,
                'risk_level':  'Undetermined',
                'description': (
                    f'The AI model could not identify a supported skin lesion class with sufficient '
                    f'confidence (highest visual match: {raw_top_name} at {raw_top_score * 100:.1f}%). '
                    'The image may depict healthy skin, non-dermatological features, or an unlisted condition. '
                    'Clinical evaluation by a board-certified dermatologist is recommended.'
                ),
                'recommendation':         'Consult a board-certified dermatologist for clinical assessment.',
                'is_unclassified':        True,
                'raw_highest_match': {
                    'code':  raw_top_code,
                    'name':  raw_top_name,
                    'score': raw_top_score
                }
            }

        return {
            'status':            'success',
            'top_prediction':    top_match,
            'top_3_predictions': top_predictions,
            'is_reliable':       bool(is_reliable),
            'quality_status':    quality_msg,
            'threshold_used':    threshold,
            'uncertainty': {
                'entropy':            round(entropy, 4),
                'uncertainty_level': uncertainty_level
            },
            'uncertainty_reason': (
                None if is_reliable else
                f'Model score {float(top_match["score"]) * 100:.1f}%. '
                f'Entropy: {entropy:.2f}. Clinical evaluation recommended.'
            )
        }
