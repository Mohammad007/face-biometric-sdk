"""
Router: Subject Management — tenant-isolated.
All operations scoped by client_id from the validated API key.
"""

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth import verify_api_key
from app.database import db
from app.face_engine import get_embedding_from_base64
from app.models import (
    ErrorResponse, SubjectAddImageRequest, SubjectCreateRequest,
    SubjectDeleteRequest, SubjectInfo, SubjectListResponse, SubjectResponse,
)

router = APIRouter(prefix="/subject", tags=["Subject Management"])


@router.post(
    "/create",
    response_model=SubjectResponse,
    summary="Create Subject",
    description="Register a new subject. Data is isolated to your API key's client account.",
    responses={400: {"model": ErrorResponse}, 401: {"model": ErrorResponse}},
)
async def create_subject(
    request: SubjectCreateRequest,
    key_record: dict = Depends(verify_api_key),
):
    client_id = key_record["client_id"]

    # Check subject limit
    current_count = db.count_subjects(client_id)
    if current_count >= key_record["max_subjects"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Subject limit reached ({key_record['max_subjects']}). Upgrade your plan.",
        )

    try:
        subject = db.create_subject(client_id, request.subjectName)
        return SubjectResponse(
            success=True,
            message=f"Subject '{request.subjectName}' created successfully",
            subject_name=subject["subject_name"],
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post(
    "/add-image",
    response_model=SubjectResponse,
    summary="Add Face Image to Subject",
    description="Add a base64 face image to an existing subject. Extracts and stores face embedding.",
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
async def add_image(
    request: SubjectAddImageRequest,
    key_record: dict = Depends(verify_api_key),
):
    client_id = key_record["client_id"]
    subject = db.get_subject(client_id, request.subjectName)
    if not subject:
        raise HTTPException(status_code=404, detail=f"Subject '{request.subjectName}' not found")

    try:
        embedding = get_embedding_from_base64(request.imageInBase64)
        db.add_embedding(subject["id"], embedding)
        return SubjectResponse(
            success=True,
            message=f"Face image added to '{request.subjectName}' successfully",
            subject_name=request.subjectName,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to add image: {str(e)}")


@router.get(
    "/list",
    response_model=SubjectListResponse,
    summary="List All Subjects",
    description="List all subjects under your client account.",
)
async def list_subjects(key_record: dict = Depends(verify_api_key)):
    client_id = key_record["client_id"]
    subjects = db.list_subjects(client_id)
    return SubjectListResponse(
        subjects=[SubjectInfo(**s) for s in subjects],
        total=len(subjects),
    )


@router.delete(
    "/delete",
    response_model=SubjectResponse,
    summary="Delete Subject",
    description="Delete a subject and all associated face data.",
    responses={404: {"model": ErrorResponse}},
)
async def delete_subject(
    request: SubjectDeleteRequest,
    key_record: dict = Depends(verify_api_key),
):
    client_id = key_record["client_id"]
    deleted = db.delete_subject(client_id, request.subjectName)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Subject '{request.subjectName}' not found")
    return SubjectResponse(
        success=True,
        message=f"Subject '{request.subjectName}' deleted",
        subject_name=request.subjectName,
    )
