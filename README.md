# Ratatoskr MCP Server

MCP Server for GNOME integration, providing access to GNOME desktop information and system details via the Model Context Protocol.

## Features

- **GNOME Desktop Information**: Query GNOME Shell version, mode, overview state, and GTK version via D-Bus
- **Distribution Information**: Access OS distribution details from `/etc/os-release`
- **Extensible Architecture**: Modular provider system for adding new data sources

## Requirements

- Python 3.9 - 3.13 (Python 3.14+ not yet supported due to pydantic-core compatibility)
- GNOME desktop environment (for GNOME-specific features)
- D-Bus session bus

## Installation

```bash
python3.13 -m venv .venv
source .venv/bin/activate
pip install -e .
```

**Note:**
- Use Python 3.13 or earlier (Python 3.14+ not yet supported due to pydantic-core compatibility)
- This server requires D-Bus access to query GNOME, so it must run directly on the host system, not in containers

## Usage

### Running the Server

**Direct execution:**
```bash
python3.13 src/ratatoskr_mcp_server/server.py
```

**Or use the installed command:**
```bash
ratatoskr-mcp-server
```

### Using with MCP Clients

Configure your MCP client to run the server:

```json
{
  "mcpServers": {
    "ratatoskr": {
      "command": "python",
      "args": ["/path/to/ratatoskr-mcp-server/src/ratatoskr_mcp_server/server.py"]
    }
  }
}
```

### Testing with MCP Inspector

```bash
npx @modelcontextprotocol/inspector python src/ratatoskr_mcp_server/server.py
```

## Development

### Running Tests

```bash
pip install -e ".[dev]"
pytest tests/
```

### Project Structure

```
src/ratatoskr_mcp_server/
├── __init__.py
├── server.py              # Main MCP server
└── dbus_providers/        # D-Bus data providers
    ├── __init__.py
    ├── base.py            # Base D-Bus provider class
    └── gnome_shell.py     # GNOME Shell provider
```

## Available Resources

- `ratatoskr://gnome/desktop` - GNOME desktop environment information
- `ratatoskr://distro/osinfo` - Distribution information

## Available Tools

- `get_desktop_info` - Get GNOME desktop information

## License

MIT
