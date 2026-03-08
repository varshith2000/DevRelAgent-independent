"""
Scheduler Module — Proactive Health Check System

Provides scheduled health checks using APScheduler.
Monitors ClickHouse for error spikes and triggers automatic diagnostics.
"""

from .health_check import HealthCheckScheduler, get_health_scheduler

__all__ = ["HealthCheckScheduler", "get_health_scheduler"]
