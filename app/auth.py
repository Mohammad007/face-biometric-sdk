"""
API Key authentication dependency — multi-tenant with usage logging.
Validates key against DB (SHA-256 hash), checks expiry, rate limits, and logs usage.
"""

from datetime import datetime
from fastapi import Header, HTTPException, Request, status

from app.database import db
from app.security import hash_api_key, is_locked_out, record_failed_attempt, clear_failed_attempts


async def verify_api_key(request: Request, x_api_key: str = Header(..., alias="x-api-key")):
    """
    Validate x-api-key: hash lookup → active check → expiry → rate limit → log usage.
    Returns the API key record (includes client_id, plan info).
    """
    client_ip = request.client.host if request.client else "unknown"

    # Brute-force check
    if is_locked_out(client_ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed attempts. Try again later.",
        )

    # Hash and lookup
    key_hash = hash_api_key(x_api_key)
    key_record = db.get_api_key_by_hash(key_hash)

    if not key_record:
        record_failed_attempt(client_ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )

    # Check key is active
    if not key_record["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key has been revoked",
        )

    # Check client is active
    if not key_record["client_active"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Client account is suspended",
        )

    # Check expiry
    if key_record["expires_at"]:
        expires = datetime.fromisoformat(key_record["expires_at"])
        if datetime.utcnow() > expires:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API key has expired",
            )

    # Check IP whitelist
    if key_record["ip_whitelist"]:
        allowed_ips = [ip.strip() for ip in key_record["ip_whitelist"].split(",")]
        if client_ip not in allowed_ips:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Request from unauthorized IP address",
            )

    # Check monthly quota (-1 means unlimited)
    if key_record["max_requests_per_month"] != -1:
        monthly_usage = db.get_monthly_usage(key_record["client_id"])
        if monthly_usage >= key_record["max_requests_per_month"]:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Monthly request quota exceeded. Please upgrade your subscription.",
            )

    # Clear failed attempts on success
    clear_failed_attempts(client_ip)

    # Log usage
    db.log_usage(
        api_key_id=key_record["id"],
        client_id=key_record["client_id"],
        endpoint=request.url.path,
        method=request.method,
    )

    return key_record
