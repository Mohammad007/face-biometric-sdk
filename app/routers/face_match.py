"""
Router: POST /get-face-match-score
1:1 face verification — tenant-isolated.
"""

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth import verify_api_key
from app.face_engine import compare_faces
from app.models import FaceMatchRequest, FaceMatchResponse, ErrorResponse

router = APIRouter(tags=["Face Match"])


@router.post(
    "/get-face-match-score",
    response_model=FaceMatchResponse,
    summary="1:1 Face Match Score",
    description=(
        "Compare two face images and return a similarity score. "
        "Both images must be base64-encoded (JPEG/PNG). "
        "Uses TensorFlow FaceNet deep face embedding comparison."
    ),
    responses={
        400: {"model": ErrorResponse, "description": "Invalid image or no face detected"},
        401: {"model": ErrorResponse, "description": "Invalid API key"},
        429: {"model": ErrorResponse, "description": "Rate limit or quota exceeded"},
    },
)
async def get_face_match_score(
    request: FaceMatchRequest,
    key_record: dict = Depends(verify_api_key),
):
    try:
        result = compare_faces(request.image1, request.image2)
        return FaceMatchResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Face matching failed: {str(e)}")
