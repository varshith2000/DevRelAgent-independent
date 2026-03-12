# Disabling DevRelAgent

This guide explains how to disable DevRelAgent in various scenarios, from temporary shutdown to complete removal.

## Quick Shutdown

### Emergency Stop

**For immediate shutdown of all DevRelAgent operations:**

```bash
# Stop the backend service
systemctl stop devrelagent
# OR if using Docker
docker stop devrelagent-backend
# OR if running directly
pkill -f "python.*main.py"
```

### Stop Specific Features

**Disable audit logging:**
```bash
# Set environment variable
export AUDIT_ENABLED=false
# Or in .env file
AUDIT_ENABLED=false
```

**Disable tool execution:**
```bash
# Set environment variable
export ENABLE_TOOLS=false
# Or in .env file
ENABLE_TOOLS=false
```

**Disable approvals:**
```bash
# Set environment variable
export APPROVALS_ENABLED=false
# Or in .env file
APPROVALS_ENABLED=false
```

## Configuration-Based Disabling

### Environment Variables

**Complete Feature Disable via Environment Variables:**

```bash
# .env file
# Disable all features
AUDIT_ENABLED=false
ENABLE_TOOLS=false
APPROVALS_ENABLED=false
GUARDRAILS_ENABLED=false
HEALTH_CHECK_ENABLED=false

# Keep only core chat functionality
CHAT_ENABLED=true
```

### Feature Flags

**Disable Specific Features:**

```python
# In apps/backend/main.py or config.py

# Disable audit trail
AUDIT_CONFIG = {
    "enabled": False,
    "storage_path": "data/audit",
    "cache_size": 1000,
}

# Disable approvals
APPROVAL_CONFIG = {
    "enabled": False,
    "timeout_seconds": 300,
}

# Disable guardrails
GUARDRAIL_CONFIG = {
    "input_enabled": False,
    "output_enabled": False,
    "tool_enabled": False,
}

# Disable health checks
HEALTH_CHECK_CONFIG = {
    "enabled": False,
    "interval_minutes": 5,
}
```

## Code-Level Disabling

### Disable Audit Logging

**In `apps/backend/routes/chat.py`:**
```python
# Comment out audit logging
# await audit_logger.log(audit_entry)
```

**In `apps/backend/main.py`:**
```python
# Don't include audit router
# app.include_router(audit_router, tags=["audit"])
```

### Disable Guardrails

**In `apps/backend/agent/loop.py`:**
```python
# Initialize with guardrails disabled
agent = AgentLoop(
    enable_input_guardrails=False,
    enable_output_guardrails=False,
    enable_tool_guardrails=False,
)
```

### Disable Specific Tools

**In `apps/backend/main.py`:**
```python
# Comment out tool registrations
# from tools import browser_tool
# from tools import github_tool
```

**Or modify tool registry:**
```python
# In apps/backend/tools/registry.py
def disable_tool(tool_name: str):
    """Disable a specific tool."""
    tool = registry.get(tool_name)
    if tool:
        tool.metadata.enabled = False
```

## Infrastructure-Level Disabling

### Kubernetes

**Disable Deployment:**
```bash
# Scale to zero
kubectl scale deployment devrelagent --replicas=0

# OR disable service
kubectl patch service devrelagent -p '{"spec":{"selector":{"app":"none"}}}'
```

**Disable Specific Features via ConfigMap:**
```yaml
# configmap.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: devrelagent-config
data:
  AUDIT_ENABLED: "false"
  APPROVALS_ENABLED: "false"
  ENABLE_TOOLS: "false"
```

```bash
kubectl apply -f configmap.yaml
kubectl rollout restart deployment/devrelagent
```

### Docker Compose

**Disable Services:**
```yaml
# docker-compose.yml
services:
  devrelagent:
    # ... other config
    environment:
      - AUDIT_ENABLED=false
      - ENABLE_TOOLS=false
    profiles:
      - disabled  # Requires explicit profile to run
```

```bash
# Stop the service
docker-compose stop devrelagent
# OR scale to zero
docker-compose up -d --scale devrelagent=0
```

### Systemd Service

**Disable Service:**
```bash
# Stop and disable
systemctl stop devrelagent
systemctl disable devrelagent

# Check status
systemctl status devrelagent
```

**Service File (`/etc/systemd/system/devrelagent.service`):**
```ini
[Unit]
Description=DevRelAgent Service
After=network.target

[Service]
Type=simple
User=devrelagent
WorkingDirectory=/opt/devrelagent
ExecStart=/usr/bin/python3 apps/backend/main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

## API-Based Disabling

### Disable via API Endpoints

**Disable audit logging:**
```bash
curl -X POST http://localhost:8000/admin/config/audit \
  -H "Content-Type: application/json" \
  -d '{"enabled": false}'
```

**Disable specific tools:**
```bash
curl -X POST http://localhost:8000/admin/config/tools/clickhouse_query \
  -H "Content-Type: application/json" \
  -d '{"enabled": false}'
```

**Disable approvals:**
```bash
curl -X POST http://localhost:8000/admin/config/approvals \
  -H "Content-Type: application/json" \
  -d '{"enabled": false}'
```

## Graceful Shutdown

### Graceful Shutdown Procedure

**For planned maintenance:**

```bash
# 1. Set maintenance mode
curl -X POST http://localhost:8000/admin/maintenance \
  -H "Content-Type: application/json" \
  -d '{"enabled": true, "message": "System maintenance in progress"}'

# 2. Wait for active requests to complete (monitor logs)
tail -f /var/log/devrelagent/app.log

# 3. Stop accepting new connections
# (Load balancer or reverse proxy configuration)

# 4. Stop the service
systemctl stop devrelagent

# 5. Verify shutdown
ps aux | grep devrelagent
```

### Graceful Shutdown Code

**In `apps/backend/main.py`:**
```python
import signal
import asyncio

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("🚀 DevRelAgent API starting...")

    # Initialize components...

    # Setup signal handlers for graceful shutdown
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, shutting down...")
        # Trigger cleanup

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    yield

    # Cleanup
    logger.info("🛑 DevRelAgent API shutting down...")
    # Save state, close connections, etc.

app = FastAPI(lifespan=lifespan)
```

## Complete Removal

### Uninstall from System

**Remove all DevRelAgent components:**

```bash
# 1. Stop services
systemctl stop devrelagent
systemctl disable devrelagent

# 2. Remove systemd service
rm -f /etc/systemd/system/devrelagent.service
systemctl daemon-reload

# 3. Remove application files
rm -rf /opt/devrelagent

# 4. Remove data directory (optional - backup first!)
rm -rf /var/lib/devrelagent

# 5. Remove configuration
rm -f /etc/devrelagent/config.yaml
rm -f /etc/devrelagent/.env

# 6. Remove user (if created)
userdel devrelagent

# 7. Remove logs (optional - backup first!)
rm -rf /var/log/devrelagent
```

### Docker Removal

**Remove containers and images:**
```bash
# Stop containers
docker stop devrelagent-backend devrelagent-frontend
docker rm devrelagent-backend devrelagent-frontend

# Remove volumes
docker volume rm devrelagent-data devrelagent-logs

# Remove images
docker rmi devrelagent-backend:latest devrelagent-frontend:latest

# Remove network
docker network rm devrelagent-network
```

### Kubernetes Removal

**Remove all resources:**
```bash
# Delete deployment
kubectl delete deployment devrelagent

# Delete service
kubectl delete service devrelagent

# Delete configmaps
kubectl delete configmap devrelagent-config

# Delete secrets
kubectl delete secret devrelagent-secrets

# Delete persistent volumes
kubectl delete pvc devrelagent-data

# Delete namespace (if using dedicated namespace)
kubectl delete namespace devrelagent
```

## Data Backup Before Disabling

### Backup Audit Logs

```bash
# Export audit logs
tar -czf devrelagent-audit-backup-$(date +%Y%m%d).tar.gz data/audit/

# Export to database (if using ClickHouse)
clickhouse-client --query="SELECT * FROM audit_trail INTO OUTFILE 'audit_backup.csv' FORMAT CSVWithNames"
```

### Backup Configuration

```bash
# Backup configuration
cp -r /etc/devrelagent ./devrelagent-config-backup-$(date +%Y%m%d)

# Backup environment variables
env | grep DEVRELAGENT > devrelagent-env-backup-$(date +%Y%m%d).env
```

### Backup Data

```bash
# Backup data directory
tar -czf devrelagent-data-backup-$(date +%Y%m%d).tar.gz data/

# Backup ClickHouse data (if using)
clickhouse-client --query="BACKUP TABLE audit_trail TO Disk('backups', 'audit_backup')"
```

## Verification

### Verify Disabled State

**Check if service is stopped:**
```bash
# Check process
ps aux | grep devrelagent

# Check port
netstat -tlnp | grep 8000

# Check service status
systemctl status devrelagent
```

**Check if features are disabled:**
```bash
# Check audit logs
ls -la data/audit/

# Check API endpoints
curl http://localhost:8000/health | jq .
```

**Check system logs:**
```bash
# Check for errors
journalctl -u devrelagent -n 50 --no-pager

# Check for disabled features
grep "disabled" /var/log/devrelagent/app.log
```

## Re-enabling

### Re-enable Service

```bash
# Systemd
systemctl enable devrelagent
systemctl start devrelagent

# Docker
docker-compose up -d

# Kubernetes
kubectl scale deployment devrelagent --replicas=1
```

### Re-enable Features

```bash
# Update environment variables
export AUDIT_ENABLED=true
export ENABLE_TOOLS=true
export APPROVALS_ENABLED=true

# Restart service
systemctl restart devrelagent
```

## Troubleshooting

### Common Issues

**Service won't stop:**
```bash
# Force kill
pkill -9 -f devrelagent

# Check for processes
ps aux | grep devrelagent

# Check for open ports
lsof -i :8000
```

**Data remains after disabling:**
```bash
# Manually remove data
rm -rf data/audit/*
rm -rf data/investigations/*
rm -rf data/kedb/*
```

**Features still active after disabling:**
```bash
# Check for cached configurations
rm -rf .pytest_cache/__pycache__/
rm -rf apps/backend/__pycache__/

# Restart service
systemctl restart devrelagent
```

## Support

For assistance with disabling DevRelAgent:
- **Documentation**: [Project Wiki]
- **Issues**: [GitHub Issues]
- **Support**: support@example.com
- **Emergency**: emergency@example.com
