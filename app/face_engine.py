"""
TensorFlow-based Face Biometric Engine.

Uses MTCNN for face detection and a deep CNN (InceptionResNetV1-style)
for generating face embeddings. Compares faces using cosine similarity.
"""

import base64
import io
import logging
from typing import List, Optional, Tuple

import numpy as np
from PIL import Image

from app.config import settings

logger = logging.getLogger(__name__)

# ── Lazy-loaded global models ────────────────────
_detector = None
_embedder = None


def _get_detector():
    """Lazy-load MTCNN face detector."""
    global _detector
    if _detector is None:
        from mtcnn import MTCNN
        _detector = MTCNN()
        logger.info("MTCNN face detector loaded")
    return _detector


def _get_embedder():
    """
    Lazy-load the face embedding model.

    Uses Keras FaceNet (InceptionResNetV1) pre-trained on VGGFace2.
    Produces 128-dimensional face embeddings.
    """
    global _embedder
    if _embedder is None:
        from keras_facenet import FaceNet
        _embedder = FaceNet()
        logger.info("FaceNet embedding model loaded")
    return _embedder


# ── Image Processing ─────────────────────────────

def decode_base64_image(base64_str: str) -> np.ndarray:
    """
    Decode a base64-encoded image string to a numpy array (RGB).

    Args:
        base64_str: Base64 encoded image (JPEG/PNG).

    Returns:
        numpy.ndarray: RGB image array (H, W, 3).

    Raises:
        ValueError: If the image cannot be decoded.
    """
    try:
        # Handle data URI prefix if present
        if "," in base64_str:
            base64_str = base64_str.split(",", 1)[1]

        image_bytes = base64.b64decode(base64_str)
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        return np.array(image)
    except Exception as e:
        raise ValueError(f"Failed to decode base64 image: {str(e)}")


def preprocess_face(
    face_pixels: np.ndarray,
    target_size: tuple = None,
) -> np.ndarray:
    """
    Resize and normalize a face crop for the embedding model.

    Args:
        face_pixels: Cropped face image array (H, W, 3).
        target_size: Target (width, height). Defaults to config setting.

    Returns:
        Preprocessed face array ready for embedding extraction.
    """
    if target_size is None:
        target_size = settings.FACE_IMAGE_SIZE

    image = Image.fromarray(face_pixels)
    image = image.resize(target_size)
    face_array = np.array(image).astype("float32")
    return face_array


# ── Face Detection ───────────────────────────────

def detect_faces(image_array: np.ndarray) -> List[dict]:
    """
    Detect faces in an image using MTCNN.

    Args:
        image_array: RGB image as numpy array.

    Returns:
        List of detection dicts with keys: 'box', 'confidence', 'keypoints'.
    """
    detector = _get_detector()
    detections = detector.detect_faces(image_array)
    # Filter by minimum confidence
    return [
        d for d in detections
        if d["confidence"] >= settings.MIN_FACE_CONFIDENCE
    ]


def extract_face(
    image_array: np.ndarray,
    detection: Optional[dict] = None,
) -> Optional[np.ndarray]:
    """
    Extract and preprocess the largest/best face from an image.

    Args:
        image_array: RGB image as numpy array.
        detection: Optional pre-computed MTCNN detection. If None, will detect.

    Returns:
        Preprocessed face array, or None if no face found.
    """
    if detection is None:
        detections = detect_faces(image_array)
        if not detections:
            return None
        # Use the detection with highest confidence
        detection = max(detections, key=lambda d: d["confidence"])

    x, y, w, h = detection["box"]
    # Clamp to image bounds
    x, y = max(0, x), max(0, y)
    x2 = min(image_array.shape[1], x + w)
    y2 = min(image_array.shape[0], y + h)

    face_crop = image_array[y:y2, x:x2]
    if face_crop.size == 0:
        return None

    return preprocess_face(face_crop)


# ── Embedding Extraction ────────────────────────

def get_embedding(face_array: np.ndarray) -> np.ndarray:
    """
    Generate a face embedding vector using FaceNet.

    Args:
        face_array: Preprocessed face image (160x160x3).

    Returns:
        numpy.ndarray: 512-dimensional face embedding vector (L2 normalized).
    """
    embedder = _get_embedder()
    # FaceNet expects a batch; add batch dimension
    detections = [face_array.astype("uint8")]
    embeddings = embedder.embeddings(detections)
    embedding = embeddings[0]
    # L2 normalize
    norm = np.linalg.norm(embedding)
    if norm > 0:
        embedding = embedding / norm
    return embedding


def get_embedding_from_base64(base64_str: str) -> np.ndarray:
    """
    Full pipeline: base64 image → face detection → embedding.

    Args:
        base64_str: Base64 encoded face image.

    Returns:
        Face embedding vector.

    Raises:
        ValueError: If no face is detected in the image.
    """
    image_array = decode_base64_image(base64_str)
    face = extract_face(image_array)
    if face is None:
        raise ValueError(
            "No face detected in the provided image. "
            "Ensure the image contains a clear, front-facing face."
        )
    return get_embedding(face)


# ── Face Comparison ──────────────────────────────

def cosine_similarity(emb1: np.ndarray, emb2: np.ndarray) -> float:
    """
    Compute cosine similarity between two embedding vectors.

    Args:
        emb1: First embedding vector.
        emb2: Second embedding vector.

    Returns:
        Similarity score between 0.0 and 1.0.
    """
    dot = np.dot(emb1, emb2)
    norm1 = np.linalg.norm(emb1)
    norm2 = np.linalg.norm(emb2)
    if norm1 == 0 or norm2 == 0:
        return 0.0
    similarity = float(dot / (norm1 * norm2))
    # Clamp to [0, 1]
    return max(0.0, min(1.0, similarity))


def compare_faces(
    base64_image1: str,
    base64_image2: str,
    threshold: float = None,
) -> dict:
    """
    Compare two face images (1:1 verification).

    Args:
        base64_image1: First face image in base64.
        base64_image2: Second face image in base64.
        threshold: Match threshold. Defaults to config setting.

    Returns:
        Dict with 'similarity', 'matched', 'threshold', 'message'.
    """
    if threshold is None:
        threshold = settings.FACE_MATCH_THRESHOLD

    emb1 = get_embedding_from_base64(base64_image1)
    emb2 = get_embedding_from_base64(base64_image2)

    similarity = cosine_similarity(emb1, emb2)
    matched = similarity >= threshold

    return {
        "similarity": round(similarity, 6),
        "matched": matched,
        "threshold": threshold,
        "message": (
            f"Faces match with {similarity:.2%} similarity"
            if matched
            else f"Faces do not match (similarity: {similarity:.2%}, threshold: {threshold:.2%})"
        ),
    }


def search_one_to_n(
    probe_base64: str,
    gallery: List[Tuple[str, np.ndarray]],
    threshold: float = None,
) -> List[dict]:
    """
    Search a probe face against a gallery of enrolled face embeddings (1:N).

    Args:
        probe_base64: Probe face image in base64.
        gallery: List of (subject_name, embedding) tuples.
        threshold: Match threshold. Defaults to config setting.

    Returns:
        List of match result dicts sorted by similarity (descending).
    """
    if threshold is None:
        threshold = settings.FACE_MATCH_THRESHOLD

    probe_embedding = get_embedding_from_base64(probe_base64)

    # Compare against every gallery embedding
    results_map: dict = {}
    for subject_name, gallery_emb in gallery:
        sim = cosine_similarity(probe_embedding, gallery_emb)
        # Keep the best score per subject
        if subject_name not in results_map or sim > results_map[subject_name]:
            results_map[subject_name] = sim

    results = [
        {
            "subject_name": name,
            "similarity": round(sim, 6),
            "matched": sim >= threshold,
        }
        for name, sim in results_map.items()
    ]

    # Sort by similarity descending
    results.sort(key=lambda r: r["similarity"], reverse=True)
    return results
