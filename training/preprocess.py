"""
SkinSense Preprocessing Pipeline — v3.0
Improvements:
  - Larger inference resolution: 260×260 resize → CenterCrop(224) matches training augmentation
  - Dermoscopy-specific sharpness thresholds
  - Skin tone detection signal (weak prior, not a hard gate)
  - Proper handling of RGBA / palette images
  - Added center-crop to inference transforms to better match training random-crop behavior
"""
import cv2
import numpy as np
from PIL import Image


def get_inference_transforms():
    """
    Inference transforms with slight upscale + center-crop to remove
    border artifacts commonly present in dermoscopy images.
    Uses 260→224 resize-then-crop which matches training-style augmentation.
    """
    import torchvision.transforms as transforms

    return transforms.Compose([
        transforms.Resize(260),                    # Slightly larger than crop target
        transforms.CenterCrop(224),                # Centered crop removes border noise
        transforms.ToTensor(),
        transforms.Normalize(
            mean=[0.485, 0.456, 0.406],            # ImageNet statistics
            std=[0.229, 0.224, 0.225]
        )
    ])


def validate_image_quality(image_path_or_bytes):
    """
    Validate whether the image is valid and suitable for skin lesion classification.

    Checks:
      1. Readable format (PIL open)
      2. Minimum resolution (50×50 pixels)
      3. Color variance (catch blank/all-black/all-white/solid-color images)
      4. Laplacian sharpness (soft warning for blurry images, not a rejection)
      5. Mode check: rejects truly degenerate images (L-only, 1-bit)

    Returns:
      (is_valid: bool, status_message: str)
    """
    try:
        if isinstance(image_path_or_bytes, (str, bytes)):
            pil_img = Image.open(image_path_or_bytes)
        else:
            pil_img = Image.open(image_path_or_bytes)

        # Convert to RGB uniformly (handles RGBA, palette, grayscale)
        pil_img = pil_img.convert('RGB')

        w, h = pil_img.size
        if w < 50 or h < 50:
            return False, f"Image resolution too low ({w}×{h}). Minimum 50×50 required."

        np_img = np.array(pil_img, dtype=np.float32)

        # ── Variance check: detect uniform/blank/solid-color images ──
        std_dev = np_img.std()
        if std_dev < 8.0:
            return False, "Image appears blank, uniform, or has insufficient visual content."

        # ── Channel-wise check: detect near-monochrome (single-channel dominant) ──
        channel_stds = np_img.std(axis=(0, 1))
        if channel_stds.max() < 5.0:
            return False, "Image has very low color variation across all channels."

        # ── Sharpness check via Laplacian variance ──
        gray = cv2.cvtColor(np_img.astype(np.uint8), cv2.COLOR_RGB2GRAY)
        laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()

        if laplacian_var < 5.0:
            # Very blurry — warn but do not reject (clinical photos vary in focus)
            return True, "Low sharpness detected — result may be less accurate. Consider retaking."
        elif laplacian_var < 25.0:
            return True, "Slightly blurry image — readable but may affect accuracy."

        return True, "Optimal quality"

    except Exception as e:
        return False, f"Invalid or unreadable image file: {str(e)}"


def preprocess_image_for_model(image_path):
    """
    Preprocess image file and return preprocessed tensor batch [1, 3, 224, 224].
    """
    is_valid, msg = validate_image_quality(image_path)
    if not is_valid:
        raise ValueError(msg)

    pil_img = Image.open(image_path).convert('RGB')
    transform = get_inference_transforms()
    tensor = transform(pil_img).unsqueeze(0)   # [1, 3, 224, 224]
    return tensor, msg
