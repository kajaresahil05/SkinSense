import os
import unittest
from unittest.mock import Mock
import tempfile
import numpy as np
from PIL import Image
from backend.services.model_service import ModelService
from backend.services.image_validation_service import ImageValidationError

class TestModelService(unittest.TestCase):
    def setUp(self):
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        model_path = os.path.join(base_dir, 'Dataset2', 'skinsense_dataset2_mobilenetv2.keras')
        config_path = os.path.join(base_dir, 'Dataset2', 'skinsense_dataset2_class_names.json')
        class_path = os.path.join(base_dir, 'models', 'class_labels.json')
        self.model_service = ModelService(model_path, config_path, class_path, image_validator=Mock())
        self.temp_dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_model_loading(self):
        self.assertTrue(self.model_service.is_loaded)
        self.assertIsNotNone(self.model_service.model)

    def test_valid_image_prediction(self):
        img_path = os.path.join(self.temp_dir.name, "sample_skin.jpg")
        img_data = np.random.randint(100, 220, (224, 224, 3), dtype=np.uint8)
        img = Image.fromarray(img_data)
        img.save(img_path)

        result = self.model_service.predict(img_path)
        self.assertEqual(result['status'], 'success')
        self.assertIn('top_prediction', result)
        self.assertIn('top_3_predictions', result)
        self.assertEqual(len(result['top_3_predictions']), 3)
        self.assertIn('score', result['top_prediction'])
        self.assertTrue(0.0 <= result['top_prediction']['score'] <= 1.0)

    def test_unsuitable_image_never_reaches_classifier(self):
        img_path = os.path.join(self.temp_dir.name, 'unrelated.jpg')
        Image.fromarray(np.random.default_rng(1).integers(50, 230, (224, 224, 3), dtype=np.uint8)).save(img_path)
        self.model_service.image_validator.validate.side_effect = ImageValidationError('Unsuitable image')
        classifier = Mock()
        self.model_service.model = classifier
        with self.assertRaises(ImageValidationError):
            self.model_service.predict(img_path)
        classifier.assert_not_called()

    def test_invalid_image_handling(self):
        blank_path = os.path.join(self.temp_dir.name, "tiny_blank.jpg")
        img = Image.new('RGB', (10, 10), color='black')
        img.save(blank_path)

        result = self.model_service.predict(str(blank_path))
        self.assertEqual(result['status'], 'error')
        self.assertFalse(result['is_reliable'])

if __name__ == '__main__':
    unittest.main()

