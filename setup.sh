#!/bin/bash
# DevRelAgent Complete Setup Script
# This script sets up everything you need: ClickHouse, Grafana, OTel Collector

set -e

echo "================================================"
echo "DevRelAgent Complete Setup"
echo "================================================"
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_info() {
    echo -e "${YELLOW}→ $1${NC}"
}

# Check if Docker is installed
print_info "Checking Docker installation..."
if ! command -v docker &> /dev/null; then
    print_error "Docker is not installed. Please install Docker first."
    echo "  Visit: https://docs.docker.com/get-docker/"
    exit 1
fi
print_success "Docker is installed"

# Check if Docker Compose is installed
print_info "Checking Docker Compose..."
if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    print_error "Docker Compose is not installed. Please install Docker Compose first."
    echo "  Visit: https://docs.docker.com/compose/install/"
    exit 1
fi
print_success "Docker Compose is installed"

# Create .env file if it doesn't exist
print_info "Checking environment configuration..."
if [ ! -f .env ]; then
    print_info "Creating .env file from .env.example..."
    cp .env.example .env
    print_success "Created .env file"
    print_info "Please edit .env and update the following values:"
    echo "  - CLICKHOUSE_HOST"
    echo "  - GRAFANA_API_TOKEN (create after Grafana starts)"
    echo ""
    read -p "Press Enter to continue after updating .env..."
else
    print_success ".env file exists"
fi

# Create data directories
print_info "Creating data directories..."
mkdir -p data/investigations
mkdir -p data/audit
mkdir -p data/learning_memory
mkdir -p data/dashboards
print_success "Created data directories"

# Start Docker services
print_info "Starting Docker services..."
if docker-compose version &> /dev/null; then
    docker-compose up -d
else
    docker compose up -d
fi
print_success "Docker services started"

# Wait for services to be ready
print_info "Waiting for services to be ready..."
sleep 10

# Check ClickHouse
print_info "Checking ClickHouse..."
if docker exec devrelagent-clickhouse clickhouse-client --query "SELECT 1" &> /dev/null; then
    print_success "ClickHouse is ready"

    # Initialize ClickHouse tables
    print_info "Initializing ClickHouse tables..."
    docker exec -i devrelagent-clickhouse clickhouse-client --multiquery < scripts/init_clickhouse.sql
    print_success "ClickHouse tables initialized"
else
    print_error "ClickHouse is not ready yet. Please check logs: docker-compose logs clickhouse"
fi

# Check Grafana
print_info "Checking Grafana..."
if curl -s http://localhost:3000/api/health &> /dev/null; then
    print_success "Grafana is ready"
    echo ""
    print_info "Grafana is running at: http://localhost:3000"
    echo "  Default credentials: admin / admin"
    echo "  Please create an API token:"
    echo "    1. Open http://localhost:3000"
    echo "    2. Go to Configuration → API Keys"
    echo "    3. Click 'Add API key'"
    echo "    4. Name: 'DevRelAgent'"
    echo "    5. Role: 'Admin'"
    echo "    6. Copy the token and update GRAFANA_API_TOKEN in .env"
else
    print_error "Grafana is not ready yet. Please check logs: docker-compose logs grafana"
fi

# Check OTel Collector
print_info "Checking OpenTelemetry Collector..."
if curl -s http://localhost:8888/metrics &> /dev/null; then
    print_success "OpenTelemetry Collector is ready"
    print_info "OTel Collector is accepting data at:"
    echo "  OTLP gRPC:  localhost:4317"
    echo "  OTLP HTTP:  localhost:4318"
else
    print_error "OpenTelemetry Collector is not ready yet. Please check logs: docker-compose logs otel-collector"
fi

# Install Python dependencies
print_info "Installing Python dependencies..."
cd apps/backend
pip install -q -r requirements.txt
print_success "Python dependencies installed"
cd ../..

# Test DevRelAgent
print_info "Testing DevRelAgent..."
cd apps/backend
if python cli.py status &> /dev/null; then
    print_success "DevRelAgent is ready"
else
    print_error "DevRelAgent test failed"
fi
cd ../..

echo ""
echo "================================================"
print_success "Setup Complete!"
echo "================================================"
echo ""
echo "Services running:"
echo "  • ClickHouse:  http://localhost:8123"
echo "  • Grafana:     http://localhost:3000"
echo "  • OTel Collector:"
echo "    - gRPC:  localhost:4317"
echo "    - HTTP:   localhost:4318"
echo ""
echo "Next steps:"
echo "  1. Login to Grafana (admin/admin)"
echo "  2. Create API token and update .env"
echo "  3. Configure ClickHouse datasource in Grafana"
echo "  4. Test connection: cd apps/backend && python cli.py grafana test-connection"
echo "  5. Create dashboard: python cli.py grafana create-dashboard --service my-api"
echo ""
echo "For more information, see:"
echo "  • docs/INSTALLATION_SETUP_GUIDE.md"
echo "  • docs/USER_GUIDE.md"
echo ""
