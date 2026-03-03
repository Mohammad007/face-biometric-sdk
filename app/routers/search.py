"""
Router: POST /one-to-n
1:N face identification — tenant-isolated.
"""

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth import verify_api_key
from app.database import db
from app.face_engine import search_one_to_n
from app.models import ErrorResponse, MatchResult, OneToNRequest, OneToNResponse

router = APIRouter(tags=["Face Search"])


@router.post(
    "/one-to-n",
    response_model=OneToNResponse,
    summary="1:N Face Identification",
    description=(
        "Search a probe face against all enrolled subjects under your account. "
        "Returns ranked matches by similarity score."
    ),
    responses={
        400: {"model": ErrorResponse},
        401: {"model": ErrorResponse},
    },
)
async def one_to_n_search(
    request: OneToNRequest,
    key_record: dict = Depends(verify_api_key),
):
    client_id = key_record["client_id"]
    gallery = db.get_all_embeddings(client_id)

    if not gallery:
        return OneToNResponse(
            results=[], total_subjects_searched=0,
            message="No subjects enrolled. Add subjects first.",
        )

    try:
        results = search_one_to_n(request.image, gallery)
        match_results = [MatchResult(**r) for r in results]
        matched_count = sum(1 for r in match_results if r.matched)

        if matched_count > 0:
            best = match_results[0]
            message = f"Found {matched_count} match(es). Best: '{best.subject_name}' ({best.similarity:.2%})"
        else:
            message = "No matches found above the threshold."

        return OneToNResponse(
            results=match_results,
            total_subjects_searched=len(set(name for name, _ in gallery)),
            message=message,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")
