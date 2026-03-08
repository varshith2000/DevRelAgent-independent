"""
Health Check Scheduler — Proactive Monitoring

Cron-based health checks that:
1. Query ClickHouse for error spikes
2. Detect anomalies (>5% error rate threshold)
3. Auto-run DiagnoseErrorSkill on anomalies
4. Post alerts to dashboard API
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Literal
from dataclasses import dataclass

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)


@dataclass
class HealthAlert:
    """Health alert data structure."""
    id: str
    type: Literal["error_spike", "health_check", "anomaly"]
    severity: Literal["critical", "warning", "info"]
    service: str
    message: str
    error_rate: Optional[float] = None
    timestamp: datetime = None
    metadata: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for SSE emission."""
        return {
            "id": self.id,
            "type": self.type,
            "severity": self.severity,
            "service": self.service,
            "message": self.message,
            "error_rate": self.error_rate,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata or {}
        }


class HealthCheckScheduler:
    """
    Proactive health check scheduler using APScheduler.

    Features:
    - Cron-based health checks
    - Error spike detection
    - Automatic diagnosis using DiagnoseErrorSkill
    - Dashboard alert posting via SSE
    - Configurable thresholds and intervals
    """

    def __init__(
        self,
        clickhouse_client=None,
        tool_registry=None,
        interval_minutes: int = 5,
        error_threshold: float = 5.0
    ):
        """
        Initialize the health check scheduler.

        Args:
            clickhouse_client: ClickHouse client for queries
            tool_registry: Tool registry for running skills
            interval_minutes: Health check interval (default: 5 minutes)
            error_threshold: Error rate threshold % (default: 5%)
        """
        self.ch_client = clickhouse_client
        self.registry = tool_registry
        self.interval_minutes = interval_minutes
        self.error_threshold = error_threshold

        # APScheduler instance
        self.scheduler = AsyncIOScheduler()

        # Alert queue for SSE streaming
        self.alert_queue: Optional[asyncio.Queue] = None

        # Alert history
        self.alert_history: List[HealthAlert] = []

        # Service status tracking
        self.service_status: Dict[str, Literal["green", "yellow", "red"]] = {}

        logger.info(
            f"📊 HealthCheckScheduler initialized: "
            f"interval={interval_minutes}m, threshold={error_threshold}%"
        )

    def start(self):
        """Start the scheduler."""
        try:
            # Add health check job
            self.scheduler.add_job(
                self._run_health_check,
                trigger=IntervalTrigger(minutes=self.interval_minutes),
                id="health_check",
                name="Health Check",
                replace_existing=True
            )

            # Start scheduler
            self.scheduler.start()
            logger.info("✅ HealthCheckScheduler started")

        except Exception as e:
            logger.error(f"❌ Failed to start HealthCheckScheduler: {e}")
            raise

    def stop(self):
        """Stop the scheduler."""
        try:
            self.scheduler.shutdown()
            logger.info("🛑 HealthCheckScheduler stopped")
        except Exception as e:
            logger.error(f"❌ Failed to stop HealthCheckScheduler: {e}")

    def set_alert_queue(self, queue: asyncio.Queue):
        """
        Set the SSE queue for emitting alerts.

        Args:
            queue: Async queue for SSE events
        """
        self.alert_queue = queue
        logger.info("📡 Alert queue connected to HealthCheckScheduler")

    async def _run_health_check(self):
        """
        Main health check job.

        Called periodically by APScheduler to:
        1. Query ClickHouse for error rates
        2. Detect spikes above threshold
        3. Generate alerts for anomalies
        4. Auto-run diagnosis on critical issues
        """
        logger.info("🔍 Running health check...")

        try:
            # Query error rates from ClickHouse
            error_rates = await self._query_error_rates()

            if not error_rates:
                logger.info("✅ No errors detected in health check")
                return

            # Check for error spikes
            for service, rate in error_rates.items():
                if rate >= self.error_threshold:
                    # Error spike detected
                    severity = "critical" if rate >= self.error_threshold * 2 else "warning"

                    alert = HealthAlert(
                        id=self._generate_alert_id(),
                        type="error_spike",
                        severity=severity,
                        service=service,
                        message=f"Error rate spike detected: {rate:.1f}% (threshold: {self.error_threshold}%)",
                        error_rate=rate
                    )

                    # Emit alert
                    await self._emit_alert(alert)

                    # Update service status
                    self.service_status[service] = "red" if severity == "critical" else "yellow"

                    # Auto-run diagnosis for critical errors
                    if severity == "critical":
                        await self._auto_diagnose(alert)

                else:
                    # Service is healthy
                    self.service_status[service] = "green"

            logger.info(f"✅ Health check completed. Checked {len(error_rates)} services")

        except Exception as e:
            logger.error(f"❌ Health check failed: {e}")

    async def _query_error_rates(self) -> Dict[str, float]:
        """
        Query ClickHouse for recent error rates by service.

        Returns:
            Dictionary mapping service names to error rates (%)
        """
        if not self.ch_client:
            logger.warning("⚠️ ClickHouse client not available, skipping error rate query")
            return {}

        try:
            # Calculate time range (last N minutes)
            time_range = f"now() - INTERVAL {self.interval_minutes} MINUTE"

            # Query error logs and calculate error rate
            query = f"""
            SELECT
                service,
                countIf(level = 'ERROR') AS errors,
                count() AS total,
                round((errors / total) * 100, 2) AS error_rate
            FROM logs
            WHERE timestamp >= {time_range}
            GROUP BY service
            HAVING error_rate > 0
            ORDER BY error_rate DESC
            """

            result = self.ch_client.execute_query(query)

            error_rates = {}
            for row in result:
                service = row[0]
                error_rate = float(row[3])
                error_rates[service] = error_rate

            return error_rates

        except Exception as e:
            logger.error(f"❌ Failed to query error rates: {e}")
            return {}

    async def _auto_diagnose(self, alert: HealthAlert):
        """
        Auto-run DiagnoseErrorSkill on critical alerts.

        Args:
            alert: Health alert that triggered auto-diagnosis
        """
        logger.info(f"🔬 Auto-diagnosing: {alert.service}")

        try:
            # Get DiagnoseErrorSkill from registry
            if not self.registry:
                logger.warning("⚠️ Tool registry not available, skipping auto-diagnosis")
                return

            # Execute DiagnoseErrorSkill
            from skills import get_skill_registry
            skill_registry = get_skill_registry()
            skill = skill_registry.get("diagnose_error")

            if not skill:
                logger.warning("⚠️ DiagnoseErrorSkill not found, skipping auto-diagnosis")
                return

            # Build context
            context = {
                "tool_registry": self.registry,
                "alert": alert.to_dict()
            }

            # Execute skill
            result = await skill.execute(
                context,
                error_description=alert.message,
                service_name=alert.service,
                time_range=f"{self.interval_minutes}m"
            )

            if result.success:
                # Create diagnosis alert
                diagnosis_alert = HealthAlert(
                    id=self._generate_alert_id(),
                    type="health_check",
                    severity="info",
                    service=alert.service,
                    message=f"Auto-diagnosis completed: {result.result.get('summary', 'No specific findings')}",
                    metadata={
                        "original_alert_id": alert.id,
                        "diagnosis": result.result
                    }
                )

                await self._emit_alert(diagnosis_alert)
                logger.info(f"✅ Auto-diagnosis completed for {alert.service}")

            else:
                logger.error(f"❌ Auto-diagnosis failed for {alert.service}: {result.error}")

        except Exception as e:
            logger.error(f"❌ Auto-diagnosis error: {e}")

    async def _emit_alert(self, alert: HealthAlert):
        """
        Emit alert via SSE queue and store in history.

        Args:
            alert: Health alert to emit
        """
        # Store in history
        self.alert_history.append(alert)

        # Keep history manageable
        if len(self.alert_history) > 1000:
            self.alert_history = self.alert_history[-1000:]

        # Emit via SSE
        if self.alert_queue:
            try:
                await self.alert_queue.put({"type": "alert", "data": alert.to_dict()})
                logger.info(f"📤 Alert emitted: {alert.id}")
            except Exception as e:
                logger.error(f"❌ Failed to emit alert: {e}")
        else:
            logger.warning("⚠️ Alert queue not set, alert not emitted")

    def _generate_alert_id(self) -> str:
        """Generate unique alert ID."""
        from datetime import datetime
        return f"alert-{datetime.now().strftime('%Y%m%d%H%M%S')}-{hex(id(self))[:8]}"

    def get_service_status(self) -> Dict[str, Literal["green", "yellow", "red"]]:
        """
        Get current status of all monitored services.

        Returns:
            Dictionary mapping service names to status colors
        """
        return self.service_status.copy()

    def get_alert_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get alert history.

        Args:
            limit: Maximum number of alerts to return

        Returns:
            List of alert dictionaries
        """
        history = [alert.to_dict() for alert in self.alert_history]
        return list(reversed(history[-limit:]))


# Global singleton instance
_health_scheduler: Optional[HealthCheckScheduler] = None


def get_health_scheduler() -> Optional[HealthCheckScheduler]:
    """
    Get the global HealthCheckScheduler instance.

    Returns:
        The singleton HealthCheckScheduler instance or None
    """
    return _health_scheduler


def set_health_scheduler(scheduler: HealthCheckScheduler):
    """
    Set the global HealthCheckScheduler instance.

    Args:
        scheduler: HealthCheckScheduler instance
    """
    global _health_scheduler
    _health_scheduler = scheduler
