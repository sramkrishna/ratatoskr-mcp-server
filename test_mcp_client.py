#!/usr/bin/env python3
"""
Simple test client to verify MCP server works correctly.
"""
import asyncio
import json
import os
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def test_server():
    """Test the MCP server resources and tools."""
    server_params = StdioServerParameters(
        command="python3.13",
        args=["src/ratatoskr_mcp_server/server.py"],
        env=dict(os.environ),  # Pass current environment to subprocess
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            # Initialize
            await session.initialize()

            # List available resources
            print("=" * 60)
            print("AVAILABLE RESOURCES")
            print("=" * 60)
            resources = await session.list_resources()
            for resource in resources.resources:
                print(f"- {resource.name}")
                print(f"  URI: {resource.uri}")
                print(f"  Description: {resource.description}")
                print()

            # Read GNOME desktop resource
            print("=" * 60)
            print("READING GNOME DESKTOP RESOURCE")
            print("=" * 60)
            result = await session.read_resource("ratatoskr://gnome/desktop")
            for content in result.contents:
                print(content.text)
            print()

            # Read distro info resource
            print("=" * 60)
            print("READING DISTRO INFO RESOURCE")
            print("=" * 60)
            result = await session.read_resource("ratatoskr://distro/osinfo")
            for content in result.contents:
                print(content.text)
            print()

            # List available tools
            print("=" * 60)
            print("AVAILABLE TOOLS")
            print("=" * 60)
            tools = await session.list_tools()
            for tool in tools.tools:
                print(f"- {tool.name}: {tool.description}")
            print()


if __name__ == "__main__":
    asyncio.run(test_server())
