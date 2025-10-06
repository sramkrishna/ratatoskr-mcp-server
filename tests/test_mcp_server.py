"""Integration tests for ratatoskr-mcp-server"""

import json
import os

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def create_session():
    """Helper to create an MCP client session."""
    server_params = StdioServerParameters(
        command="python3.13",
        args=["src/ratatoskr_mcp_server/server.py"],
        env=dict(os.environ),
    )

    client = stdio_client(server_params)
    read, write = await client.__aenter__()
    session = ClientSession(read, write)
    await session.__aenter__()
    await session.initialize()
    return session, client


@pytest.mark.asyncio
async def test_list_resources():
    """Test that the server lists expected resources."""
    session, client = await create_session()

    resources = await session.list_resources()

    assert len(resources.resources) == 2

    # Check GNOME desktop resource
    gnome_resource = resources.resources[0]
    assert str(gnome_resource.uri) == "ratatoskr://gnome/desktop"
    assert gnome_resource.name == "GNOME Desktop Environment"
    assert "GNOME desktop" in gnome_resource.description

    # Check distro info resource
    distro_resource = resources.resources[1]
    assert str(distro_resource.uri) == "ratatoskr://distro/osinfo"
    assert distro_resource.name == "Distribution Info"
    assert "distro" in distro_resource.description.lower()


@pytest.mark.asyncio
async def test_read_gnome_desktop_resource():
    """Test reading GNOME desktop information."""
    session, client = await create_session()

    result = await session.read_resource("ratatoskr://gnome/desktop")

    assert len(result.contents) == 1
    content = result.contents[0]

    # Parse the JSON response
    data = json.loads(content.text)

    # Check required fields exist
    assert "desktop_environment" in data
    assert "gnome_shell_version" in data
    assert "gnome_shell_mode" in data
    assert "overview_visible" in data
    assert "gtk_version" in data
    assert "desktop_session" in data
    assert "xdg_current_desktop" in data
    assert "is_gnome_session" in data

    # Check types
    assert isinstance(data["gnome_shell_version"], str)
    assert isinstance(data["overview_visible"], bool)
    assert isinstance(data["is_gnome_session"], bool)


@pytest.mark.asyncio
async def test_read_distro_info_resource():
    """Test reading distribution information."""
    session, client = await create_session()

    result = await session.read_resource("ratatoskr://distro/osinfo")

    assert len(result.contents) == 1
    content = result.contents[0]

    # Parse the JSON response
    data = json.loads(content.text)

    # Check required fields exist
    assert "name" in data
    assert "version" in data
    assert "version_id" in data
    assert "pretty_name" in data
    assert "id" in data

    # Check types
    assert isinstance(data["name"], str)
    assert isinstance(data["version"], str)


@pytest.mark.asyncio
async def test_list_tools():
    """Test that the server lists expected tools."""
    session, client = await create_session()

    tools = await session.list_tools()

    assert len(tools.tools) == 1

    tool = tools.tools[0]
    assert tool.name == "get_desktop_info"
    assert "desktop" in tool.description.lower()


@pytest.mark.asyncio
async def test_call_get_desktop_info_tool():
    """Test calling the get_desktop_info tool."""
    session, client = await create_session()

    result = await session.call_tool("get_desktop_info", {})

    assert len(result.content) == 1
    content = result.content[0]

    # The tool returns JSON-formatted desktop info
    data = json.loads(content.text)

    # Should have the same fields as the GNOME desktop resource
    assert "desktop_environment" in data
    assert "gnome_shell_version" in data


@pytest.mark.asyncio
async def test_invalid_resource():
    """Test that requesting an invalid resource returns an error."""
    session, client = await create_session()

    with pytest.raises(Exception):  # MCP will raise an error
        await session.read_resource("ratatoskr://invalid/resource")
