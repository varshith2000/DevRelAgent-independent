"""Central application configuration.

This package is the *only* place in the backend that reads environment
variables. Every other module imports :func:`get_settings` and reads typed
attributes instead of calling ``os.getenv``.
"""

from config.settings import Settings, get_settings, reset_settings_cache

__all__ = ["Settings", "get_settings", "reset_settings_cache"]
