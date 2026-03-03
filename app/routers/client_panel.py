"""
Client Admin Panel API routes.

JWT-protected endpoints for clients to manage their API keys, view subjects, and usage.
"""

from fastapi import APIRouter, Depends, HTTPException

from app.config import settings
from app.database import db
from app.jwt_auth import create_access_token, get_current_client
from app.models import (
    ApiKeyCreateRequest, ApiKeyCreateResponse, ApiKeyInfo,
    DashboardResponse, ErrorResponse, LoginRequest, SubjectInfo,
    SubjectListResponse, TokenResponse, UsageStats,
)
from app.security import (
    generate_api_key, hash_api_key,
    is_locked_out, record_failed_attempt, clear_failed_attempts,
)

router = APIRouter(prefix="/client", tags=["Client Admin"])


# ── Login ────────────────────────────────────────

@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Client Login",
    description="Authenticate as a client and receive a JWT token.",
)
async def client_login(request: LoginRequest):
    if is_locked_out(request.email):
        raise HTTPException(status_code=429, detail="Account locked. Try again later.")

    client = db.verify_client_password(request.email, request.password)
    if not client:
        record_failed_attempt(request.email)
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not client["is_active"]:
        raise HTTPException(status_code=403, detail="Account is suspended")

    clear_failed_attempts(request.email)
    token = create_access_token({
        "sub": request.email, "role": "client_admin", "client_id": client["id"]
    })
    return TokenResponse(
        access_token=token, role="client_admin",
        expires_in_hours=settings.JWT_EXPIRY_HOURS,
    )


# ── Dashboard ────────────────────────────────────

@router.get(
    "/dashboard",
    response_model=DashboardResponse,
    summary="Client Dashboard",
    description="View usage stats, quota remaining, and subscription info.",
)
async def client_dashboard(current: dict = Depends(get_current_client)):
    client = db.get_client(current["client_id"])
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    usage_data = db.get_client_usage_stats(current["client_id"])
    subjects_count = db.count_subjects(current["client_id"])
    return DashboardResponse(
        client_name=client["company_name"],
        plan_name=client["plan_name"],
        max_subjects=client["max_subjects"],
        max_requests_per_month=client["max_requests_per_month"],
        current_subjects=subjects_count,
        usage=UsageStats(**usage_data),
    )


# ── API Keys ─────────────────────────────────────

@router.post(
    "/api-keys",
    response_model=ApiKeyCreateResponse,
    summary="Generate API Key",
    description="Generate a new API key. ⚠️ The raw key is shown ONLY ONCE!",
)
async def create_api_key(
    request: ApiKeyCreateRequest,
    current: dict = Depends(get_current_client),
):
    raw_key = generate_api_key()
    key_hash = hash_api_key(raw_key)
    key_prefix = raw_key[:8] + "..."

    key_id = db.store_api_key(
        client_id=current["client_id"],
        key_hash=key_hash,
        key_prefix=key_prefix,
        label=request.label,
        ip_whitelist=request.ip_whitelist,
    )
    return ApiKeyCreateResponse(
        id=key_id,
        raw_key=raw_key,
        key_prefix=key_prefix,
        label=request.label,
        message="⚠️ Save this key now! It will NOT be shown again.",
    )


@router.get(
    "/api-keys",
    response_model=list[ApiKeyInfo],
    summary="List API Keys",
    description="List all API keys (only prefix shown, not full key).",
)
async def list_api_keys(current: dict = Depends(get_current_client)):
    keys = db.list_client_api_keys(current["client_id"])
    return [ApiKeyInfo(**k) for k in keys]


@router.delete(
    "/api-keys/{key_id}",
    summary="Revoke API Key",
    description="Revoke (deactivate) an API key. It can no longer be used.",
)
async def revoke_api_key(key_id: int, current: dict = Depends(get_current_client)):
    success = db.revoke_api_key(key_id, current["client_id"])
    if not success:
        raise HTTPException(status_code=404, detail="API key not found")
    return {"success": True, "message": "API key revoked"}


@router.post(
    "/api-keys/{key_id}/rotate",
    response_model=ApiKeyCreateResponse,
    summary="Rotate API Key",
    description="Revoke old key and generate a new one (zero downtime rotation).",
)
async def rotate_api_key(key_id: int, current: dict = Depends(get_current_client)):
    # Revoke old
    success = db.revoke_api_key(key_id, current["client_id"])
    if not success:
        raise HTTPException(status_code=404, detail="API key not found")

    # Generate new
    raw_key = generate_api_key()
    key_hash = hash_api_key(raw_key)
    key_prefix = raw_key[:8] + "..."
    new_id = db.store_api_key(
        client_id=current["client_id"],
        key_hash=key_hash,
        key_prefix=key_prefix,
        label=f"rotated-from-{key_id}",
    )
    return ApiKeyCreateResponse(
        id=new_id,
        raw_key=raw_key,
        key_prefix=key_prefix,
        label=f"rotated-from-{key_id}",
        message="⚠️ Old key revoked. Save this new key — it won't be shown again!",
    )


# ── Subjects ─────────────────────────────────────

@router.get(
    "/subjects",
    response_model=SubjectListResponse,
    summary="View Enrolled Subjects",
    description="View all subjects enrolled under this client account.",
)
async def list_my_subjects(current: dict = Depends(get_current_client)):
    subjects = db.list_subjects(current["client_id"])
    return SubjectListResponse(
        subjects=[SubjectInfo(**s) for s in subjects],
        total=len(subjects),
    )


# ── Usage ────────────────────────────────────────

@router.get(
    "/usage",
    response_model=UsageStats,
    summary="Usage Breakdown",
    description="Daily/monthly usage breakdown with per-endpoint stats.",
)
async def usage_stats(current: dict = Depends(get_current_client)):
    stats = db.get_client_usage_stats(current["client_id"])
    return UsageStats(**stats)
