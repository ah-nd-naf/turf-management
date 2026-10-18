"""
Production settings for Turf Management project.
"""

from .base import *

DEBUG = False

# Strict production requirement: SECRET_KEY must be supplied via environment
SECRET_KEY = env('SECRET_KEY')

# Production Security Configurations
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_SSL_REDIRECT = env.bool('SECURE_SSL_REDIRECT', default=True)
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
