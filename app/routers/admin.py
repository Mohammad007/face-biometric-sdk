"""
Super Admin Panel API routes.

JWT-protected endpoints for managing clients, plans, and viewing global dashboard.
"""

from fastapi import APIRouter, Depends, HTTPException, status

from app.config import settings
from app.database import db
from app.jwt_auth import create_access_token, get_current_admin
from app.models import (
    ClientCreateRequest, ClientListResponse, ClientResponse, ClientUpdateRequest,
    DemoAccountCreateRequest, DemoAccountResponse, ErrorResponse, GlobalDashboardResponse,
    LoginRequest, PlanCreateRequest, PlanResponse, TokenResponse,
)
from app.security import is_locked_out, record_failed_attempt, clear_failed_attempts

router = APIRouter(prefix="/admin", tags=["Super Admin"])


# ── Login ────────────────────────────────────────

@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Super Admin Login",
    description="Authenticate as super admin and receive a JWT token.",
)
async def admin_login(request: LoginRequest):
    if is_locked_out(request.email):
        raise HTTPException(status_code=429, detail="Account locked. Try again later.")

    if (request.email != settings.SUPER_ADMIN_EMAIL or
            not db.verify_client_password(request.email, request.password)):
        record_failed_attempt(request.email)
        raise HTTPException(status_code=401, detail="Invalid credentials")

    clear_failed_attempts(request.email)
    token = create_access_token({"sub": request.email, "role": "super_admin"})
    return TokenResponse(
        access_token=token, role="super_admin",
        expires_in_hours=settings.JWT_EXPIRY_HOURS,
    )


# ── Clients ──────────────────────────────────────

@router.post(
    "/clients",
    response_model=ClientResponse,
    summary="Create Client",
    description="Register a new client with a subscription plan.",
    responses={400: {"model": ErrorResponse}},
)
async def create_client(
    request: ClientCreateRequest,
    admin: dict = Depends(get_current_admin),
):
    plan = db.get_plan(request.plan_id)
    if not plan:
        raise HTTPException(status_code=400, detail=f"Plan ID {request.plan_id} not found")
    try:
        client = db.create_client(
            request.company_name, request.email, request.password, request.plan_id
        )
        return ClientResponse(
            id=client["id"], company_name=client["company_name"],
            email=client["email"], is_active=1,
            created_at=client.get("created_at", ""),
            plan_name=plan["name"],
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post(
    "/demo-account",
    response_model=DemoAccountResponse,
    summary="Create Unlimited Demo Account",
    description="Provision a demo account with unlimited requests but an automatic expiry date. Generates and returns an API key.",
    responses={400: {"model": ErrorResponse}},
)
async def create_demo_account(
    request: DemoAccountCreateRequest,
    admin: dict = Depends(get_current_admin),
):
    from datetime import datetime, timedelta
    from app.security import generate_api_key, hash_api_key
    
    # 1. Ensure "Demo Unlimited" plan exists
    plans = db.list_plans()
    demo_plan = next((p for p in plans if p["name"] == "Demo Unlimited"), None)
    if not demo_plan:
        plan_dict = db.create_plan(
            name="Demo Unlimited",
            rate_limit_per_minute=1000,
            max_subjects=5000,
            max_requests_per_month=-1, # -1 implies unlimited bypass in auth.py
            price_monthly=0.0,
        )
        plan_id = plan_dict["id"]
    else:
        plan_id = demo_plan["id"]

    # 2. Create the client
    try:
        client = db.create_client(
            company_name=request.company_name,
            email=request.email,
            password=request.password,
            plan_id=plan_id
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    # 3. Generate API Key with explicit expiry date
    raw_key = generate_api_key()
    key_hash = hash_api_key(raw_key)
    key_prefix = raw_key[:8] + "..."
    
    expires_at = (datetime.utcnow() + timedelta(days=request.expires_in_days)).isoformat()
    
    db.store_api_key(
        client_id=client["id"],
        key_hash=key_hash,
        key_prefix=key_prefix,
        label=f"demo-key-{request.expires_in_days}-days",
        expires_at=expires_at,
    )

    return DemoAccountResponse(
        client_id=client["id"],
        company_name=client["company_name"],
        email=client["email"],
        api_key=raw_key,
        expires_at=expires_at
    )


@router.get(
    "/clients",
    response_model=ClientListResponse,
    summary="List All Clients",
)
async def list_clients(admin: dict = Depends(get_current_admin)):
    clients = db.list_clients()
    return ClientListResponse(
        clients=[ClientResponse(**c) for c in clients],
        total=len(clients),
    )


@router.get("/clients/{client_id}", summary="Get Client Details")
async def get_client(client_id: int, admin: dict = Depends(get_current_admin)):
    client = db.get_client(client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    usage = db.get_client_usage_stats(client_id)
    return {
        "id": client["id"],
        "company_name": client["company_name"],
        "email": client["email"],
        "plan_name": client["plan_name"],
        "is_active": client["is_active"],
        "max_subjects": client["max_subjects"],
        "max_requests_per_month": client["max_requests_per_month"],
        "usage": usage,
    }


@router.put("/clients/{client_id}", summary="Update Client")
async def update_client(
    client_id: int, request: ClientUpdateRequest,
    admin: dict = Depends(get_current_admin),
):
    updates = request.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    success = db.update_client(client_id, **updates)
    if not success:
        raise HTTPException(status_code=404, detail="Client not found")
    return {"success": True, "message": "Client updated"}


@router.delete("/clients/{client_id}", summary="Delete Client")
async def delete_client(client_id: int, admin: dict = Depends(get_current_admin)):
    success = db.delete_client(client_id)
    if not success:
        raise HTTPException(status_code=404, detail="Client not found")
    return {"success": True, "message": "Client deleted"}


# ── Plans ────────────────────────────────────────

@router.get(
    "/plans",
    response_model=list[PlanResponse],
    summary="List Subscription Plans",
)
async def list_plans(admin: dict = Depends(get_current_admin)):
    return [PlanResponse(**p) for p in db.list_plans()]


@router.post(
    "/plans",
    response_model=PlanResponse,
    summary="Create Subscription Plan",
)
async def create_plan(
    request: PlanCreateRequest,
    admin: dict = Depends(get_current_admin),
):
    try:
        plan = db.create_plan(
            request.name, request.rate_limit_per_minute,
            request.max_subjects, request.max_requests_per_month,
            request.price_monthly,
        )
        created = db.get_plan(plan["id"])
        return PlanResponse(**created)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── Dashboard ────────────────────────────────────

@router.get(
    "/dashboard",
    response_model=GlobalDashboardResponse,
    summary="Global Dashboard",
    description="Overview: total clients, API keys, subjects, monthly requests.",
)
async def admin_dashboard(admin: dict = Depends(get_current_admin)):
    stats = db.get_global_stats()
    return GlobalDashboardResponse(**stats)
