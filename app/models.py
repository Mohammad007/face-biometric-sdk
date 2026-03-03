"""
Pydantic models for all request/response schemas.
"""

from typing import List, Optional
from pydantic import BaseModel, Field


# ══════════════════════════════════════════════════
#  AUTH / JWT
# ══════════════════════════════════════════════════

class LoginRequest(BaseModel):
    email: str = Field(..., json_schema_extra={"example": "admin@idssoft.com"})
    password: str = Field(..., json_schema_extra={"example": "Admin@123456"})


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    expires_in_hours: int


# ══════════════════════════════════════════════════
#  SUBSCRIPTION PLANS
# ══════════════════════════════════════════════════

class PlanCreateRequest(BaseModel):
    name: str = Field(..., json_schema_extra={"example": "Pro Plus"})
    rate_limit_per_minute: int = Field(100)
    max_subjects: int = Field(10000)
    max_requests_per_month: int = Field(100000)
    price_monthly: float = Field(79.99)


class PlanResponse(BaseModel):
    id: int
    name: str
    rate_limit_per_minute: int
    max_subjects: int
    max_requests_per_month: int
    price_monthly: float
    is_active: int
    created_at: str


# ══════════════════════════════════════════════════
#  CLIENTS
# ══════════════════════════════════════════════════

class ClientCreateRequest(BaseModel):
    company_name: str = Field(..., json_schema_extra={"example": "Acme Corp"})
    email: str = Field(..., json_schema_extra={"example": "client@acme.com"})
    password: str = Field(..., min_length=8, json_schema_extra={"example": "SecurePass123"})
    plan_id: int = Field(..., json_schema_extra={"example": 2})


class ClientUpdateRequest(BaseModel):
    plan_id: Optional[int] = None
    is_active: Optional[int] = None
    company_name: Optional[str] = None


class DemoAccountCreateRequest(BaseModel):
    company_name: str = Field(..., json_schema_extra={"example": "Demo Corp"})
    email: str = Field(..., json_schema_extra={"example": "demo@acme.com"})
    password: str = Field(..., min_length=8, json_schema_extra={"example": "DemoPass123"})
    expires_in_days: int = Field(7, ge=1, le=365, description="Days until API key expires")

class DemoAccountResponse(BaseModel):
    client_id: int
    company_name: str
    email: str
    api_key: str = Field(..., description="Raw API key — viewable ONLY once")
    expires_at: str


class ClientResponse(BaseModel):
    id: int
    company_name: str
    email: str
    is_active: int
    created_at: str
    plan_name: Optional[str] = None
    active_keys: Optional[int] = None
    total_subjects: Optional[int] = None


class ClientListResponse(BaseModel):
    clients: List[ClientResponse]
    total: int


# ══════════════════════════════════════════════════
#  API KEYS
# ══════════════════════════════════════════════════

class ApiKeyCreateRequest(BaseModel):
    label: str = Field("default", json_schema_extra={"example": "production-key"})
    ip_whitelist: Optional[str] = Field(None, description="Comma-separated IPs", json_schema_extra={"example": "192.168.1.1,10.0.0.1"})


class ApiKeyCreateResponse(BaseModel):
    """Returned only once — the raw key is never shown again!"""
    id: int
    raw_key: str = Field(..., description="⚠️ Save this key! It will NOT be shown again.")
    key_prefix: str
    label: str
    message: str


class ApiKeyInfo(BaseModel):
    id: int
    key_prefix: str
    label: str
    ip_whitelist: Optional[str]
    is_active: int
    expires_at: Optional[str]
    created_at: str


# ══════════════════════════════════════════════════
#  USAGE & DASHBOARD
# ══════════════════════════════════════════════════

class UsageStats(BaseModel):
    requests_today: int
    requests_this_month: int
    requests_total: int
    endpoint_breakdown: list


class DashboardResponse(BaseModel):
    client_name: str
    plan_name: str
    max_subjects: int
    max_requests_per_month: int
    current_subjects: int
    usage: UsageStats


class GlobalDashboardResponse(BaseModel):
    total_clients: int
    active_api_keys: int
    total_subjects: int
    requests_this_month: int


# ══════════════════════════════════════════════════
#  BIOMETRIC API (same as before, for Swagger)
# ══════════════════════════════════════════════════

class FaceMatchRequest(BaseModel):
    image1: str = Field(..., description="First face image (base64)")
    image2: str = Field(..., description="Second face image (base64)")


class FaceMatchResponse(BaseModel):
    similarity: float = Field(..., ge=0.0, le=1.0)
    matched: bool
    threshold: float
    message: str


class SubjectCreateRequest(BaseModel):
    subjectName: str = Field(..., min_length=1, max_length=255)


class SubjectAddImageRequest(BaseModel):
    subjectName: str
    imageInBase64: str


class SubjectDeleteRequest(BaseModel):
    subjectName: str


class SubjectInfo(BaseModel):
    id: int
    subject_name: str
    face_count: int
    created_at: str


class SubjectListResponse(BaseModel):
    subjects: List[SubjectInfo]
    total: int


class SubjectResponse(BaseModel):
    success: bool
    message: str
    subject_name: Optional[str] = None


class OneToNRequest(BaseModel):
    image: str = Field(..., description="Probe face image (base64)")


class MatchResult(BaseModel):
    subject_name: str
    similarity: float = Field(..., ge=0.0, le=1.0)
    matched: bool


class OneToNResponse(BaseModel):
    results: List[MatchResult]
    total_subjects_searched: int
    message: str


class ErrorResponse(BaseModel):
    detail: str
