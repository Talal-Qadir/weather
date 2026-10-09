import os
from pathlib import Path
from dotenv import load_dotenv
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "dev-only-change-me")
DEBUG = os.getenv("DJANGO_DEBUG", "False").lower() == "true"
if not DEBUG and (SECRET_KEY == "dev-only-change-me" or SECRET_KEY.startswith("replace-") or len(SECRET_KEY) < 50):
    raise RuntimeError("Set DJANGO_SECRET_KEY to a strong random value when DEBUG is disabled.")
ALLOWED_HOSTS = [v.strip() for v in os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if v.strip()]
INSTALLED_APPS = ["django.contrib.contenttypes", "django.contrib.staticfiles", "rest_framework", "corsheaders", "routing", "weather", "risk_engine"]
MIDDLEWARE = ["django.middleware.security.SecurityMiddleware", "corsheaders.middleware.CorsMiddleware", "django.middleware.common.CommonMiddleware", "django.middleware.csrf.CsrfViewMiddleware", "django.middleware.clickjacking.XFrameOptionsMiddleware"]
ROOT_URLCONF = "config.urls"
TEMPLATES = []
WSGI_APPLICATION = "config.wsgi.application"
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if DATABASE_URL:
    import dj_database_url
    DATABASES = {"default": dj_database_url.parse(DATABASE_URL, conn_max_age=600, conn_health_checks=True)}
    if not DEBUG and DATABASE_URL.startswith(("postgres://", "postgresql://")):
        DATABASES["default"].setdefault("OPTIONS", {})["sslmode"] = "require"
else:
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_TZ = True
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
CORS_ALLOWED_ORIGINS = [os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")]
CSRF_TRUSTED_ORIGINS = [v for v in os.getenv("CSRF_TRUSTED_ORIGINS", "").split(",") if v]
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
if not DEBUG:
    SECURE_SSL_REDIRECT = os.getenv("SECURE_SSL_REDIRECT", "True").lower() == "true"
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = int(os.getenv("SECURE_HSTS_SECONDS", "31536000"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
REST_FRAMEWORK = {"DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"], "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.AnonRateThrottle"], "DEFAULT_THROTTLE_RATES": {"anon": "60/hour"}, "UNAUTHENTICATED_USER": None}
