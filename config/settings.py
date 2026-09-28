"""
Django settings for the Employee Leave Management backend.

All environment-specific values (secrets, database credentials, hosts) are read
from environment variables, loaded from backend/.env for local development.
See backend/.env.example for the full list.
"""

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")


def env(name: str, default: str | None = None) -> str:
    value = os.environ.get(name, default)
    if value is None or value == "":
        raise ImproperlyConfigured(f"Environment variable {name} is required.")
    return value


def env_bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


SECRET_KEY = env("DJANGO_SECRET_KEY")

DEBUG = env_bool("DJANGO_DEBUG", False)

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")


# Application definition

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "core",
    "accounts",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


# Database — PostgreSQL only.

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("POSTGRES_DB"),
        "USER": env("POSTGRES_USER"),
        "PASSWORD": env("POSTGRES_PASSWORD"),
        "HOST": env("POSTGRES_HOST", "127.0.0.1"),
        "PORT": env("POSTGRES_PORT", "5433"),
        "OPTIONS": {"connect_timeout": 5},
    }
}


# Password validation

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# Internationalization

LANGUAGE_CODE = "en-us"

TIME_ZONE = "Asia/Kolkata"

USE_I18N = True

USE_TZ = True


# Static files

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Email. Without SMTP_HOST, emails (e.g. password reset codes) are printed to the
# runserver console instead of being sent — convenient for local development.

if os.environ.get("SMTP_HOST"):
    MAILERS = {
        "default": {
            "BACKEND": "django.core.mail.backends.smtp.EmailBackend",
            "OPTIONS": {
                "host": env("SMTP_HOST"),
                "port": int(env("SMTP_PORT", "587")),
                "username": os.environ.get("SMTP_USERNAME", ""),
                "password": os.environ.get("SMTP_PASSWORD", ""),
                "use_tls": env_bool("SMTP_USE_TLS", True),
                "use_ssl": env_bool("SMTP_USE_SSL", False),
                "timeout": 10,
            },
        },
    }
else:
    MAILERS = {
        "default": {
            "BACKEND": "django.core.mail.backends.console.EmailBackend",
        },
    }
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", "Employee Leave Management <no-reply@localhost>")


# Django REST Framework

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"]
    + (["rest_framework.renderers.BrowsableAPIRenderer"] if DEBUG else []),
    # Session auth with CSRF; unauthenticated requests get 401, forbidden ones 403.
    "DEFAULT_AUTHENTICATION_CLASSES": ["accounts.authentication.SessionAuthentication"],
    # Every endpoint requires login unless it explicitly opts out (e.g. health, login).
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_THROTTLE_RATES": {
        "login": env("LOGIN_THROTTLE_RATE", "20/minute"),
        "password_reset": env("PASSWORD_RESET_THROTTLE_RATE", "20/hour"),
    },
    # Number of trusted reverse proxies in front of Django. 0 = ignore X-Forwarded-For
    # (clients could otherwise spoof it to dodge the login throttle).
    "NUM_PROXIES": int(env("DRF_NUM_PROXIES", "0")),
}


# CORS — allow the local Next.js dev server to call the API.

CORS_ALLOWED_ORIGINS = env_list(
    "CORS_ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
)
# The frontend sends the session cookie with credentials: "include".
CORS_ALLOW_CREDENTIALS = env_bool("CORS_ALLOW_CREDENTIALS", True)


# Sessions and CSRF — the frontend origin must be trusted for its POSTs to pass
# Django's Origin check.

CSRF_TRUSTED_ORIGINS = env_list(
    "CSRF_TRUSTED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
)
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
# Set both to true in any HTTPS deployment.
SESSION_COOKIE_SECURE = env_bool("SESSION_COOKIE_SECURE", False)
CSRF_COOKIE_SECURE = env_bool("CSRF_COOKIE_SECURE", False)
# Without "Remember me" the cookie ends with the browser session and is capped at
# SESSION_COOKIE_AGE; with it the cookie persists for REMEMBER_ME_SESSION_AGE.
SESSION_COOKIE_AGE = int(env("SESSION_COOKIE_AGE", "28800"))  # 8 hours
REMEMBER_ME_SESSION_AGE = int(env("REMEMBER_ME_SESSION_AGE", "2592000"))  # 30 days


# Forgot password — one-time codes sent by email.

PASSWORD_RESET_CODE_TTL = int(env("PASSWORD_RESET_CODE_TTL", "600"))  # 10 minutes
PASSWORD_RESET_MAX_ATTEMPTS = int(env("PASSWORD_RESET_MAX_ATTEMPTS", "5"))
PASSWORD_RESET_RESEND_COOLDOWN = int(env("PASSWORD_RESET_RESEND_COOLDOWN", "60"))  # seconds
