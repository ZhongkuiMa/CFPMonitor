"""Static website builder for CFPMonitor.

Provides website generation from structured conference data.
"""

from .build import build_site
from .renderer import PageRenderer

__all__ = ["build_site", "PageRenderer"]
