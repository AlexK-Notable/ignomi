# Ignomi Services Package
"""
Backend services for the Ignomi launcher.

Services handle business logic, data persistence, and system integration.
"""

from .frecency import FrecencyService

__all__ = ["FrecencyService"]
