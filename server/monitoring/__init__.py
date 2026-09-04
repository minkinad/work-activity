"""Work Activity Monitor server package."""

from .api import create_app
from .config import Settings

__all__ = ["Settings", "create_app"]
