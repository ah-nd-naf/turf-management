"""
Development settings for Turf Management project.
"""

from .base import *

DEBUG = env.bool('DEBUG', default=True)

# Use console backend for email testing during development
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
