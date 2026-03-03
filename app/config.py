"""
Application configuration and settings.
"""

import os
from typing import List


class Settings:
    """Application settings."""

    APP_TITLE: str = "IDS Soft Biometric SDK"
    APP_DESCRIPTION: str = (
        "Advanced Face Biometric Recognition API powered by TensorFlow."
    )
    APP_VERSION: str = "2.0.0"

    # Database
    DATABASE_PATH: str = os.getenv("DATABASE_PATH", "biometric_data.db")

    # Face engine settings
    FACE_MATCH_THRESHOLD: float = float(os.getenv("FACE_MATCH_THRESHOLD", "0.65"))
    FACE_IMAGE_SIZE: tuple = (160, 160)
    MIN_FACE_CONFIDENCE: float = 0.95

    # Server
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))

    # JWT Settings
    JWT_SECRET_KEY: str = os.getenv(
        "JWT_SECRET_KEY",
        "b7f3c9a1e4d8f2a6c0b5e9d3a7f1c5b8e2d6a0f4c8b2e6d0a4f8c2b6e0d4a8"
    )
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRY_HOURS: int = int(os.getenv("JWT_EXPIRY_HOURS", "24"))

    # Super Admin (initial credentials — change in production!)
    SUPER_ADMIN_EMAIL: str = os.getenv("SUPER_ADMIN_EMAIL", "admin@idssoft.com")
    SUPER_ADMIN_PASSWORD: str = os.getenv("SUPER_ADMIN_PASSWORD", "Admin@123456")

    # Security
    MAX_FAILED_ATTEMPTS: int = 10
    LOCKOUT_MINUTES: int = 5
    API_KEY_LENGTH: int = 48  # bytes → ~64 char urlsafe token

    # Default subscription plans
    DEFAULT_PLANS = [
        {
            "name": "Free",
            "rate_limit_per_minute": 10,
            "max_subjects": 100,
            "max_requests_per_month": 1_000,
            "price_monthly": 0.0,
        },
        {
            "name": "Pro",
            "rate_limit_per_minute": 100,
            "max_subjects": 10_000,
            "max_requests_per_month": 100_000,
            "price_monthly": 49.99,
        },
        {
            "name": "Enterprise",
            "rate_limit_per_minute": 1000,
            "max_subjects": 100_000,
            "max_requests_per_month": 1_000_000,
            "price_monthly": 299.99,
        },
    ]


settings = Settings()
