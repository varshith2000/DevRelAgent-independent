@echo off
REM DevRelAgent Complete Setup Script for Windows
REM This script sets up everything you need: ClickHouse, Grafana, OTel Collector

echo ================================================
echo DevRelAgent Complete Setup
echo ================================================
echo.

REM Check if Docker is installed
echo → Checking Docker installation...
docker --version >nul 2>&1
if errorlevel 1 (
    echo ✗ Docker is not installed. Please install Docker Desktop first.
    echo   Visit: https://docs.docker.com/desktop/install/windows-install/
    exit /b 1
)
echo ✓ Docker is installed

REM Check if Docker Compose is installed
echo → Checking Docker Compose...
docker-compose --version >nul 2>&1
if errorlevel 1 (
    docker compose version >nul 2>&1
    if errorlevel 1 (
        echo ✗ Docker Compose is not installed. Please install Docker Compose first.
        exit /b 1
    )
)
echo ✓ Docker Compose is installed

REM Create .env file if it doesn't exist
echo → Checking environment configuration...
if not exist .env (
    echo → Creating .env file from .env.example...
    copy .env.example .env >nul
    echo ✓ Created .env file
    echo → Please edit .env and update the following values:
    echo   - CLICKHOUSE_HOST
    echo   - GRAFANA_API_TOKEN ^(create after Grafana starts^)
    echo.
    pause
) else (
    echo ✓ .env file exists
)

REM Create data directories
echo → Creating data directories...
if not exist data\investigations mkdir data\investigations
if not exist data\audit mkdir data\audit
if not exist data\learning_memory mkdir data\learning_memory
if not exist data\dashboards mkdir data\dashboards
echo ✓ Created data directories

REM Start Docker services
echo → Starting Docker services...
docker-compose up -d
echo ✓ Docker services started

REM Wait for services to be ready
echo → Waiting for services to be ready...
timeout /t 10 /nobreak >nul

REM Check ClickHouse
echo → Checking ClickHouse...
docker exec devrelagent-clickhouse clickhouse-client --query "SELECT 1" >nul 2>&1
if errorlevel 1 (
    echo ✗ ClickHouse is not ready yet. Please check logs: docker-compose logs clickhouse
) else (
    echo ✓ ClickHouse is ready

    REM Initialize ClickHouse tables
    echo → Initializing ClickHouse tables...
    docker exec -i devrelagent-clickhouse clickhouse-client --multiquery < scripts\init_clickhouse.sql
    echo ✓ ClickHouse tables initialized
)

REM Check Grafana
echo → Checking Grafana...
curl -s http://localhost:3000/api/health >nul 2>&1
if errorlevel 1 (
    echo ✗ Grafana is not ready yet. Please check logs: docker-compose logs grafana
) else (
    echo ✓ Grafana is ready
    echo.
    echo → Grafana is running at: http://localhost:3000
    echo   Default credentials: admin / admin
    echo   Please create an API token:
    echo     1. Open http://localhost:3000
    echo     2. Go to Configuration → API Keys
    echo     3. Click 'Add API key'
    echo     4. Name: 'DevRelAgent'
    echo     5. Role: 'Admin'
    echo     6. Copy the token and update GRAFANA_API_TOKEN in .env
)

REM Check OTel Collector
echo → Checking OpenTelemetry Collector...
curl -s http://localhost:8888/metrics >nul 2>&1
if errorlevel 1 (
    echo ✗ OpenTelemetry Collector is not ready yet. Please check logs: docker-compose logs otel-collector
) else (
    echo ✓ OpenTelemetry Collector is ready
    echo → OTel Collector is accepting data at:
    echo   - OTLP gRPC:  localhost:4317
    echo   - OTLP HTTP:  localhost:4318
)

REM Install Python dependencies
echo → Installing Python dependencies...
cd apps\backend
pip install -q -r requirements.txt
if errorlevel 1 (
    echo ✗ Failed to install Python dependencies
) else (
    echo ✓ Python dependencies installed
)
cd ..\..

REM Test DevRelAgent
echo → Testing DevRelAgent...
cd apps\backend
python cli.py status >nul 2>&1
if errorlevel 1 (
    echo ✗ DevRelAgent test failed
) else (
    echo ✓ DevRelAgent is ready
)
cd ..\..

echo.
echo ================================================
echo ✓ Setup Complete!
echo ================================================
echo.
echo Services running:
echo   • ClickHouse:  http://localhost:8123
echo   • Grafana:     http://localhost:3000
echo   • OTel Collector:
echo     - gRPC:  localhost:4317
echo     - HTTP:   localhost:4318
echo.
echo Next steps:
echo   1. Login to Grafana ^(admin/admin^)
echo   2. Create API token and update .env
echo   3. Configure ClickHouse datasource in Grafana
echo   4. Test connection: cd apps\backend ^&^& python cli.py grafana test-connection
echo   5. Create dashboard: python cli.py grafana create-dashboard --service my-api
echo.
echo For more information, see:
echo   • docs\INSTALLATION_SETUP_GUIDE.md
echo   • docs\USER_GUIDE.md
echo.

pause
