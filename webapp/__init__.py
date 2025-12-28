"""Web application package for the DDNS manager."""

from webapp.models import db
from webapp.routes import bp

__all__ = ["bp", "db"]
