import os

from .base import *  # noqa: F403

DEBUG = False

# Hosts & CORS/CSRF
ALLOWED_HOSTS = [h.strip() for h in os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h.strip()]
CORS_ALLOW_ALL_ORIGINS = False
cors_origins = os.environ.get("CORS_ALLOWED_ORIGINS", "")
if cors_origins:
    CORS_ALLOWED_ORIGINS = [orig.strip() for orig in cors_origins.split(",") if orig.strip()]
else:
    CORS_ALLOWED_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:80"]

csrf_origins = os.environ.get("CSRF_TRUSTED_ORIGINS", "")
if csrf_origins:
    CSRF_TRUSTED_ORIGINS = [orig.strip() for orig in csrf_origins.split(",") if orig.strip()]

# Security headers (§3.1 Hardening)
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

# Production cookie security if HTTPS is enabled
if os.environ.get("ENABLE_HTTPS", "false").lower() in ("true", "1"):
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

