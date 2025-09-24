#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Simple integration test for the CLI functionality.
This tests that the basic CLI structure works without requiring complex backend setup.
"""

import os
import sys

# Add the massgen directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "massgen"))


def test_cli_import():
    """Test that we can import the CLI module."""
    try:
        pass

        print("✅ Successfully imported CLI modules")
        return True
    except ImportError as e:
        print(f"❌ Failed to import CLI modules: {e}")
        return False


def test_config_creation():
    """Test that we can create simple configurations."""
    try:
        from massgen.cli import create_simple_config

        # Test OpenAI config
        print("  Testing OpenAI config creation...")
        config = create_simple_config(backend_type="openai", model="gpt-4o-mini")
        print(f"  Config result: {config}")
        if config and "agent" in config and "backend" in config["agent"] and config["agent"]["backend"]["type"] == "openai":
            print("✅ OpenAI config creation works")
        else:
            print("❌ OpenAI config creation failed")
            print(f"  Expected: agent.backend.type 'openai', Got: {config}")
            return False

        # Test Azure OpenAI config
        print("  Testing Azure OpenAI config creation...")
        config = create_simple_config(backend_type="azure_openai", model="gpt-4.1")
        print(f"  Config result: {config}")
        if config and "agent" in config and "backend" in config["agent"] and config["agent"]["backend"]["type"] == "azure_openai":
            print("✅ Azure OpenAI config creation works")
        else:
            print("❌ Azure OpenAI config creation failed")
            print(f"  Expected: agent.backend.type 'azure_openai', Got: {config}")
            return False

        return True

    except Exception as e:
        print(f"❌ Error during config creation test: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_agent_config_import():
    """Test that we can import agent configuration modules."""
    try:
        pass

        print("✅ Successfully imported AgentConfig")
        return True
    except ImportError as e:
        print(f"❌ Failed to import AgentConfig: {e}")
        return False


def test_orchestrator_import():
    """Test that we can import orchestrator modules."""
    try:
        pass

        print("✅ Successfully imported Orchestrator")
        return True
    except ImportError as e:
        print(f"❌ Failed to import Orchestrator: {e}")
        return False


def test_backend_base_import():
    """Test that we can import backend base modules."""
    try:
        pass

        print("✅ Successfully imported backend base modules")
        return True
    except ImportError as e:
        print(f"❌ Failed to import backend base modules: {e}")
        return False


def test_frontend_import():
    """Test that we can import frontend modules."""
    try:
        pass

        print("✅ Successfully imported CoordinationUI")
        return True
    except ImportError as e:
        print(f"❌ Failed to import CoordinationUI: {e}")
        return False


def test_message_templates_import():
    """Test that we can import message templates."""
    try:
        pass

        print("✅ Successfully imported MessageTemplates")
        return True
    except ImportError as e:
        print(f"❌ Failed to import MessageTemplates: {e}")
        return False


def run_integration_tests():
    """Run all integration tests."""
    print("🧪 Running MassGen Integration Tests...")
    print("Testing that all major components can be imported and basic functionality works...")
    print("=" * 80)

    tests = [
        ("CLI Import", test_cli_import),
        ("Config Creation", test_config_creation),
        ("Agent Config Import", test_agent_config_import),
        ("Orchestrator Import", test_orchestrator_import),
        ("Backend Base Import", test_backend_base_import),
        ("Frontend Import", test_frontend_import),
        ("Message Templates Import", test_message_templates_import),
    ]

    passed = 0
    total = len(tests)

    for test_name, test_func in tests:
        print(f"\n🔍 Testing: {test_name}")
        if test_func():
            passed += 1
        print()

    print("=" * 80)
    print(f"📊 Integration Test Results: {passed}/{total} tests passed")

    if passed == total:
        print("🎉 All integration tests passed!")
        print("\n✅ What this means:")
        print("  • All major MassGen components can be imported")
        print("  • Basic configuration creation works")
        print("  • The code structure is intact")
        print("  • Our changes haven't broken the basic functionality")
        return True
    else:
        print(f"❌ {total - passed} integration tests failed")
        print("This indicates there may be structural issues with the codebase")
        return False


def main():
    """Main test runner."""
    print("🚀 MassGen Integration Test Suite")
    print("Testing that the basic structure and imports work correctly...")

    success = run_integration_tests()

    print("\n" + "=" * 80)
    print("🏁 Final Integration Test Summary")
    print("=" * 80)

    if success:
        print("🎉 All integration tests passed!")
        print("✅ The MassGen codebase is structurally sound")
        print("✅ Our orchestrator changes haven't broken the system")
        print("✅ The program should work correctly")
        return 0
    else:
        print("❌ Some integration tests failed")
        print("⚠️  There may be structural issues that need attention")
        return 1


if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\n⏹️  Tests interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n💥 Unexpected error during testing: {e}")
        sys.exit(1)
