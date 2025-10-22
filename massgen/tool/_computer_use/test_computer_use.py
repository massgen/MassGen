#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test script for Computer Use Tool

This script provides a simple way to test the computer_use tool
with various examples.

Usage:
    python test_computer_use.py
"""

import asyncio
import json
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from massgen.tool._computer_use import computer_use


async def test_basic_browser():
    """Test basic browser automation."""
    print("=" * 60)
    print("Test 1: Basic Browser Navigation")
    print("=" * 60)

    result = await computer_use(
        task="Go to example.com",
        environment="browser",
        display_width=1280,
        display_height=720,
        max_iterations=10,
        include_reasoning=True,
    )

    print("\nResult:")
    for block in result.output_blocks:
        if block.block_type == "text":
            data = json.loads(block.data)
            print(json.dumps(data, indent=2))
        elif block.block_type == "image":
            print(f"[Screenshot captured: {len(block.data)} bytes]")

    return result


async def test_web_search():
    """Test web search functionality."""
    print("\n" + "=" * 60)
    print("Test 2: Web Search")
    print("=" * 60)

    result = await computer_use(
        task="Search for 'Python programming' on Google",
        environment="browser",
        display_width=1280,
        display_height=720,
        max_iterations=20,
        include_reasoning=True,
        environment_config={
            "initial_url": "https://www.google.com"
        }
    )

    print("\nResult:")
    for block in result.output_blocks:
        if block.block_type == "text":
            data = json.loads(block.data)
            print(f"Success: {data.get('success')}")
            print(f"Iterations: {data.get('iterations')}")
            print(f"Actions taken: {len(data.get('actions_taken', []))}")

            if data.get('reasoning'):
                print("\nReasoning steps:")
                for step in data['reasoning']:
                    print(f"  {step['iteration']}: {step['summary']}")

    return result


async def test_docker_environment():
    """Test Docker environment (requires Docker container running)."""
    print("\n" + "=" * 60)
    print("Test 3: Docker Environment")
    print("=" * 60)
    print("Note: This requires a running Docker container named 'cua-container'")
    print("Skip this test if you don't have Docker set up.")

    try:
        result = await computer_use(
            task="Move the mouse cursor in a circle",
            environment="ubuntu",
            display_width=1280,
            display_height=800,
            max_iterations=15,
            include_reasoning=True,
            environment_config={
                "container_name": "cua-container",
                "display": ":99"
            }
        )

        print("\nResult:")
        for block in result.output_blocks:
            if block.block_type == "text":
                data = json.loads(block.data)
                print(json.dumps(data, indent=2))

        return result

    except Exception as e:
        print(f"\nDocker test skipped: {str(e)}")
        return None


async def main():
    """Run all tests."""
    print("\n🤖 Computer Use Tool - Test Suite\n")

    tests = [
        ("Basic Browser", test_basic_browser),
        ("Web Search", test_web_search),
        # Uncomment to test Docker (requires setup)
        # ("Docker Environment", test_docker_environment),
    ]

    results = []

    for test_name, test_func in tests:
        try:
            print(f"\n▶ Running: {test_name}")
            result = await test_func()
            results.append((test_name, "PASSED", result))
        except Exception as e:
            print(f"\n❌ Test failed: {str(e)}")
            results.append((test_name, "FAILED", str(e)))

    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)

    for test_name, status, _ in results:
        emoji = "✅" if status == "PASSED" else "❌"
        print(f"{emoji} {test_name}: {status}")

    print("\n✨ Testing complete!\n")


if __name__ == "__main__":
    asyncio.run(main())
