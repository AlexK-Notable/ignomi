# Ignomi Services Package
"""
Backend services for the Ignomi launcher.

Services handle business logic, data persistence, and system integration.
"""

from .frecency import FrecencyService, get_frecency_service

__all__ = ["FrecencyService", "get_frecency_service"]
