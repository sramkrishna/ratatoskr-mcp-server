# Ratatoskr MCP Server - justfile
# GNOME Desktop integration (email, calendar, contacts, notifications)

# Python to use (prefer 3.13+, fallback to system Python 3.14)
python := `which python3.13 || which python3.14 || which python3`

# Default recipe
default:
    @just --list

# Setup virtual environment and install dependencies
setup:
    @echo "🔧 Setting up Ratatoskr MCP Server (GNOME integration)..."
    @echo "Using Python: {{python}}"
    {{python}} -m venv .venv --system-site-packages
    .venv/bin/pip install --upgrade pip
    .venv/bin/pip install -e .
    @echo ""
    @echo "Installing system packages that can't be pip-installed..."
    .venv/bin/pip install --force-reinstall --no-deps dbus-python || echo "⚠️  dbus-python needs system packages"
    @echo "✅ Ratatoskr setup complete!"
    @echo ""
    @echo "Dependencies:"
    @echo "  - dbus-python (system D-Bus bindings)"
    @echo "  - python-dateutil (date/time handling)"
    @echo "  - icalendar (calendar format support)"
    @echo "  - Evolution (for email/calendar access)"

# Clean virtual environment
clean:
    @echo "🧹 Cleaning Ratatoskr virtual environment..."
    rm -rf .venv
    rm -rf *.egg-info
    rm -rf build dist
    find . -type d -name __pycache__ -exec rm -rf {} +
    @echo "✅ Clean complete"

# Run Ratatoskr server standalone (for testing)
run:
    .venv/bin/python -m ratatoskr_mcp_server.server

# Run tests
test:
    .venv/bin/pytest tests/ -v || echo "No tests defined yet"

# Install development dependencies
dev:
    .venv/bin/pip install -e ".[dev]"

# Check if Evolution is configured
check-evolution:
    @echo "Checking Evolution setup..."
    @test -d ~/.var/app/org.gnome.Evolution/cache/evolution/mail && echo "✅ Evolution mail cache found" || echo "❌ Evolution not configured"
    @test -d ~/.var/app/org.gnome.Evolution/config/evolution/sources && echo "✅ Evolution sources found" || echo "❌ Evolution sources not found"

# List available tools
tools:
    @echo "Ratatoskr MCP Tools:"
    @echo "  - query_emails (fast SQLite-based email search)"
    @echo "  - get_email_content (read email bodies)"
    @echo "  - compose_email (open email composer)"
    @echo "  - query_calendar (search calendar events)"
    @echo "  - create_calendar_event (create new events)"
    @echo "  - get_contacts (search Evolution contacts)"
    @echo "  - send_notification (GNOME notifications)"
