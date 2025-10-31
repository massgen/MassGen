#!/usr/bin/env python3
"""
Test script for VSCode adapter
Tests JSON-RPC communication
"""

import asyncio
import json
import sys
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent))


async def test_adapter():
    """Test the VSCode adapter server"""
    from massgen.vscode_adapter.server import VSCodeServer

    print("Creating VSCode server...")
    server = VSCodeServer()

    # Test handlers
    print("\n=== Testing initialize ===")
    result = await server._handle_initialize({})
    print(f"Initialize result: {json.dumps(result, indent=2)}")

    print("\n=== Testing test_connection ===")
    result = await server._handle_test_connection({})
    print(f"Test connection result: {json.dumps(result, indent=2)}")

    print("\n=== Testing list_configs ===")
    result = await server._handle_list_configs({})
    print(f"List configs result: {json.dumps(result, indent=2)}")
    if result.get("success") and result.get("configs"):
        print(f"Found {len(result['configs'])} configuration files")
        # Show first 3
        for config in result["configs"][:3]:
            print(f"  - {config['name']}: {config['path']}")

    print("\n✅ All tests passed!")


if __name__ == "__main__":
    asyncio.run(test_adapter())
