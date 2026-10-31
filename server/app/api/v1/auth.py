"""Auth routes: ``POST /v1/auth/otp``, ``/v1/auth/verify``, ``/v1/auth/refresh``."""

from fastapi import APIRouter

router = APIRouter(prefix="/auth", tags=["auth"])
