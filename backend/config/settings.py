"""
Django settings for the Insurance Claim Processing & Fraud Detection Platform.

All secrets and environment-specific values come from environment variables
(loaded from the repository-level `.env` file). Nothing secret is hard-coded.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent          # backend/
REPO_DIR = BASE_DIR.parent
load_dotenv(REPO_DIR / ".env")
load_dotenv(BASE_DIR / ".env")


def env(name, default=None):
    return os.environ.get(name, default)


def env_bool(name, default=False):
    return str(env(name, str(default))).lower() in {"1", "true", "yes", "on"}


def env_int(name, default):
    return int(env(name, default))


SECRET_KEY = env("SECRET_KEY")
DEBUG = env_bool("DEBUG", False)
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = "dev-only-insecure-key-change-me"
    else:
        raise RuntimeError("SECRET_KEY must be set when DEBUG is false (see .env.example)")

ALLOWED_HOSTS = [h.strip() for h in env("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h.strip()]

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "corsheaders",
    # project apps
    "apps.core",
    "apps.audit",
    "apps.accounts",
    "apps.vehicles",
    "apps.policies",
    "apps.claims",
    "apps.documents",
    "apps.fraud",
    "apps.investigations",
    "apps.notifications",
    "apps.reports",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.accounts.middleware.InactivityTimeoutMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": [
            "django.template.context_processors.request",
            "django.contrib.auth.context_processors.auth",
            "django.contrib.messages.context_processors.messages",
        ]},
    }
]
WSGI_APPLICATION = "config.wsgi.application"

# --------------------------------------------------------------------------- database (MySQL)
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": env("DB_NAME", "insurance_claims"),
        "USER": env("DB_USER", "claims_user"),
        "PASSWORD": env("DB_PASSWORD", ""),
        "HOST": env("DB_HOST", "127.0.0.1"),
        "PORT": env("DB_PORT", "3306"),
        "OPTIONS": {
            "charset": "utf8mb4",
            "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
        },
        "ATOMIC_REQUESTS": False,  # transactions are opened explicitly in the service layer
        "TEST": {"NAME": env("DB_TEST_NAME", "test_insurance_claims"), "CHARSET": "utf8mb4"},
    }
}
# Quick local demo without MySQL: set DB_ENGINE=sqlite in .env (the project's target database remains MySQL).
if env("DB_ENGINE", "mysql").lower() == "sqlite":
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "demo.sqlite3"}}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "accounts.User"

# --------------------------------------------------------------------------- passwords (REQ-AUTH-004/010)
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",  # salted PBKDF2-SHA256, 1M+ iterations
]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "apps.accounts.validators.ComplexityValidator"},
]

# --------------------------------------------------------------------------- security policy (SRS §5.3)
LOGIN_MAX_FAILED_ATTEMPTS = env_int("LOGIN_MAX_FAILED_ATTEMPTS", 4)       # REQ-AUTH-005
ACCOUNT_LOCK_MINUTES = env_int("ACCOUNT_LOCK_MINUTES", 20)               # REQ-AUTH-005
SESSION_INACTIVITY_MINUTES = env_int("SESSION_INACTIVITY_MINUTES", 30)   # REQ-AUTH-006
EMAIL_VERIFICATION_MAX_AGE_HOURS = env_int("EMAIL_VERIFICATION_MAX_AGE_HOURS", 48)

# Business configuration
CLAIM_EDIT_WINDOW_MINUTES = env_int("CLAIM_EDIT_WINDOW_MINUTES", 30)     # REQ-CLM-006
APPEAL_WINDOW_DAYS = env_int("APPEAL_WINDOW_DAYS", 30)
MAX_UPLOAD_SIZE_BYTES = env_int("MAX_UPLOAD_SIZE_MB", 10) * 1024 * 1024  # REQ-DOC-003

# Sessions: server-side (DB) sessions. The absolute lifetime is long; the 30-minute *inactivity*
# timeout is enforced by InactivityTimeoutMiddleware so that background polling does not count as activity.
SESSION_ENGINE = "django.contrib.sessions.backends.db"
SESSION_COOKIE_AGE = 60 * 60 * 12
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_HTTPONLY = False  # the SPA must read it to send X-CSRFToken (standard Django SPA pattern)
SECURE_COOKIES = env_bool("SECURE_COOKIES", not DEBUG)
SESSION_COOKIE_SECURE = SECURE_COOKIES
CSRF_COOKIE_SECURE = SECURE_COOKIES
SESSION_COOKIE_NAME = "icp_session"
CSRF_TRUSTED_ORIGINS = [o.strip() for o in env("CSRF_TRUSTED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if o.strip()]
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
if env_bool("ENABLE_HTTPS", False):  # REQ-SEC-015 when deployed
    SECURE_SSL_REDIRECT = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

CORS_ALLOWED_ORIGINS = CSRF_TRUSTED_ORIGINS
CORS_ALLOW_CREDENTIALS = True

# --------------------------------------------------------------------------- DRF
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["apps.accounts.authentication.CsrfEnforcedSessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_PAGINATION_CLASS": "apps.core.pagination.StandardPagination",
    "PAGE_SIZE": 20,
    "EXCEPTION_HANDLER": "apps.core.exceptions.api_exception_handler",
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "URL_FORMAT_OVERRIDE": None,  # ?format= is used by report exports (csv|xlsx|pdf)
    "DEFAULT_THROTTLE_RATES": {
        "login": env("THROTTLE_LOGIN", "20/min"),
        "register": env("THROTTLE_REGISTER", "10/hour"),
        "password_reset": env("THROTTLE_PASSWORD_RESET", "10/hour"),
        "verification": env("THROTTLE_VERIFICATION", "10/hour"),
    },
}
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

# --------------------------------------------------------------------------- files
MEDIA_ROOT = Path(env("MEDIA_ROOT", str(BASE_DIR / "media")))
MEDIA_URL = "/media-not-public/"  # documents are NEVER served directly; only via the authorised download API
DATA_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# --------------------------------------------------------------------------- email (REQ-BR-022)
EMAIL_BACKEND = env("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = env("EMAIL_HOST", "localhost")
EMAIL_PORT = env_int("EMAIL_PORT", 587)
EMAIL_HOST_USER = env("EMAIL_USER", "")
EMAIL_HOST_PASSWORD = env("EMAIL_PASSWORD", "")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
EMAIL_TIMEOUT = env_int("EMAIL_TIMEOUT", 10)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", "Insurance Claims <no-reply@claims.local>")
FRONTEND_URL = env("FRONTEND_URL", "http://localhost:5173").rstrip("/")

# --------------------------------------------------------------------------- fraud service (Flask)
FRAUD_SERVICE_URL = env("FRAUD_SERVICE_URL", "http://127.0.0.1:5001").rstrip("/")
FRAUD_SERVICE_API_KEY = env("FRAUD_SERVICE_API_KEY", "")
FRAUD_SERVICE_TIMEOUT_SECONDS = float(env("FRAUD_SERVICE_TIMEOUT_SECONDS", "10"))  # REQ-PER-003

LANGUAGE_CODE = "en-us"
TIME_ZONE = env("TIME_ZONE", "Asia/Kolkata")
USE_I18N = True
USE_TZ = True

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"plain": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "plain"}},
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", "INFO")},
    "loggers": {"django.db.backends": {"level": "WARNING"}},
}

# --------------------------------------------------------------------------- automated tests
import sys  # noqa: E402
import tempfile  # noqa: E402

TESTING = len(sys.argv) > 1 and sys.argv[1] == "test"
if TESTING:
    MEDIA_ROOT = Path(tempfile.mkdtemp(prefix="claims-test-media-"))
    EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]  # speed only; production uses PBKDF2
    REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"] = {k: "1000/min" for k in REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]}
    SECURE_COOKIES = SESSION_COOKIE_SECURE = CSRF_COOKIE_SECURE = False
    LOGGING["root"]["level"] = "ERROR"
