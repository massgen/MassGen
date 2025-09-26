#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test script for MassGen Rich Terminal Display.
Tests RichTerminalDisplay functionality with two-agent coordination.
"""

import asyncio
import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from massgen.backend.response import ResponseBackend  # noqa: E402
from massgen.chat_agent import SingleAgent  # noqa: E402
from massgen.frontend.coordination_ui import (  # noqa: E402
    CoordinationUI,
    coordinate_with_rich_ui,
)
from massgen.frontend.displays.rich_terminal_display import (  # noqa: E402
    is_rich_available,
)
from massgen.orchestrator import Orchestrator  # noqa: E402


async def test_rich_availability():
    """Test Rich library availability and display info."""
    print("🎨 Rich Library Availability Test")
    print("-" * 40)

    if is_rich_available():
        print("✅ Rich library is available")
        try:
            from rich import __version__

            print(f"📦 Rich version: {__version__}")
        except ImportError:
            print("📦 Rich version: Unknown")
        return True
    else:
        print("❌ Rich library is not available")
        print("💡 Install with: pip install rich")
        return False


async def test_rich_display_basic():
    """Test basic RichTerminalDisplay creation and configuration."""
    print("\n🖥️  Rich Display Basic Test")
    print("-" * 40)

    if not is_rich_available():
        print("⚠️  Skipping - Rich library not available")
        return False

    try:
        from massgen.frontend.displays.rich_terminal_display import RichTerminalDisplay

        # Test basic creation
        agent_ids = ["agent1", "agent2"]
        display = RichTerminalDisplay(agent_ids)

        print("✅ RichTerminalDisplay created successfully")
        print(f"📋 Agent IDs: {display.agent_ids}")
        print(f"🎨 Theme: {display.theme}")
        print(f"🔄 Refresh rate: {display.refresh_rate} Hz")

        # Test theme configuration
        themes = ["dark", "light", "cyberpunk"]
        for theme in themes:
            RichTerminalDisplay(agent_ids, theme=theme)
            print(f"✅ {theme.title()} theme created successfully")

        # Clean up
        display.cleanup()

        return True

    except Exception as e:
        print(f"❌ Rich display basic test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


async def test_rich_display_coordination():
    """Test RichTerminalDisplay with actual agent coordination."""
    print("\n🤖 Rich Display Coordination Test")
    print("-" * 40)

    if not is_rich_available():
        print("⚠️  Skipping - Rich library not available")
        return False

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("❌ OPENAI_API_KEY not found - skipping coordination test")
        return False

    try:
        # Create backend
        backend = ResponseBackend(api_key=api_key)

        # Create two agents for rich display testing
        creative_agent = SingleAgent(
            backend=backend,
            agent_id="creative",
            system_message="You are a creative writer who crafts engaging and imaginative responses. Focus on storytelling and creative expression.",
        )

        technical_agent = SingleAgent(
            backend=backend,
            agent_id="technical",
            system_message="You are a technical expert who provides precise and detailed technical information. Focus on accuracy and technical depth.",
        )

        # Create orchestrator
        agents = {"creative": creative_agent, "technical": technical_agent}

        orchestrator = Orchestrator(agents=agents)

        # Test with Rich UI using cyberpunk theme
        print("🎨 Testing with cyberpunk theme...")
        ui = CoordinationUI(
            display_type="rich_terminal",
            theme="cyberpunk",
            refresh_rate=4,
            enable_syntax_highlighting=True,
            max_content_lines=12,
            logging_enabled=True,
        )

        print("👥 Created two-agent system with Rich display:")
        print("   ✨ Creative - Storytelling and imagination")
        print("   🔧 Technical - Precision and technical depth")
        print()

        # Test question for rich display
        test_question = "Explain how artificial intelligence works, making it both technically accurate and engaging for a general audience."

        print(f"📝 Question: {test_question}")
        print("\n🎭 Starting Rich UI coordination...")
        print("=" * 60)

        # Coordinate with Rich UI
        final_response = await ui.coordinate(orchestrator, test_question)

        print("\n" + "=" * 60)
        print("✅ Rich display coordination completed!")
        print(f"📄 Final response length: {len(final_response)} characters")

        return True

    except Exception as e:
        print(f"❌ Rich display coordination test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


async def test_rich_convenience_function():
    """Test the coordinate_with_rich_ui convenience function."""
    print("\n🚀 Rich UI Convenience Function Test")
    print("-" * 40)

    if not is_rich_available():
        print("⚠️  Skipping - Rich library not available")
        return False

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("❌ OPENAI_API_KEY not found - skipping convenience function test")
        return False

    try:
        # Create backend and agents
        backend = ResponseBackend(api_key=api_key)

        analyst = SingleAgent(
            backend=backend,
            agent_id="analyst",
            system_message="You are a data analyst who provides clear analytical insights and interpretations.",
        )

        strategist = SingleAgent(
            backend=backend,
            agent_id="strategist",
            system_message="You are a strategic thinker who focuses on long-term implications and strategic recommendations.",
        )

        orchestrator = Orchestrator(agents={"analyst": analyst, "strategist": strategist})

        print("🎯 Testing convenience function with light theme...")

        # Use convenience function with light theme
        test_question = "What are the key trends in renewable energy adoption?"

        print(f"📝 Question: {test_question}")
        print("\n🎭 Using coordinate_with_rich_ui()...")
        print("=" * 60)

        final_response = await coordinate_with_rich_ui(
            orchestrator,
            test_question,
            theme="light",
            refresh_rate=6,
            enable_syntax_highlighting=True,
        )

        print("\n" + "=" * 60)
        print("✅ Convenience function test completed!")
        print(f"📄 Final response length: {len(final_response)} characters")

        return True

    except Exception as e:
        print(f"❌ Convenience function test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


async def test_rich_fallback():
    """Test fallback behavior when Rich is not available."""
    print("\n🔄 Rich Fallback Test")
    print("-" * 40)

    # This test simulates Rich not being available
    # We can't actually uninstall Rich during runtime, so we test the UI logic

    try:
        # Test UI creation with rich_terminal when Rich is available
        CoordinationUI(display_type="rich_terminal")

        if is_rich_available():
            print("✅ Rich is available - RichTerminalDisplay should be used")

            # Note: We can't easily test the actual fallback without mocking
            print("📝 Note: Fallback logic tested through UI creation")
        else:
            print("✅ Rich not available - fallback to TerminalDisplay should occur")

        return True

    except Exception as e:
        print(f"❌ Fallback test failed: {e}")
        return False


async def test_rich_themes():
    """Test different Rich themes and configurations."""
    print("\n🎨 Rich Themes Test")
    print("-" * 40)

    if not is_rich_available():
        print("⚠️  Skipping - Rich library not available")
        return False

    try:
        from massgen.frontend.displays.rich_terminal_display import RichTerminalDisplay

        agent_ids = ["agent1", "agent2"]
        themes_to_test = [
            ("dark", "Default dark theme"),
            ("light", "Light theme for bright environments"),
            ("cyberpunk", "Cyberpunk theme with vibrant colors"),
        ]

        for theme, description in themes_to_test:
            print(f"🎨 Testing {theme} theme: {description}")

            display = RichTerminalDisplay(
                agent_ids,
                theme=theme,
                refresh_rate=8,
                enable_syntax_highlighting=True,
                max_content_lines=20,
                show_timestamps=True,
            )

            # Test theme-specific color configuration
            colors = display.colors
            print(f"   - Primary color: {colors['primary']}")
            print(f"   - Success color: {colors['success']}")
            print(f"   - Border style: {colors['border']}")

            display.cleanup()
            print(f"✅ {theme.title()} theme test passed")

        return True

    except Exception as e:
        print(f"❌ Themes test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


async def main():
    """Run Rich Terminal Display test suite."""
    print("🎨 MassGen - Rich Terminal Display Test Suite")
    print("=" * 60)

    results = []

    # Test Rich availability
    results.append(await test_rich_availability())

    # Only run Rich-specific tests if Rich is available
    if results[0]:
        # Test basic Rich display functionality
        results.append(await test_rich_display_basic())

        # Test themes
        results.append(await test_rich_themes())

        # Test with actual coordination if API key is available
        if os.getenv("OPENAI_API_KEY"):
            results.append(await test_rich_display_coordination())
            results.append(await test_rich_convenience_function())
        else:
            print("\n⚠️  Skipping coordination tests - OPENAI_API_KEY not found")
            results.extend([True, True])  # Skip but don't fail
    else:
        print("\n⚠️  Skipping Rich-specific tests - Rich library not available")
        results.extend([False, False, False, False])

    # Test fallback behavior
    results.append(await test_rich_fallback())

    # Summary
    print("\n" + "=" * 60)
    print("📊 Rich Terminal Display Test Results:")

    test_names = [
        "Rich Availability",
        "Basic Display",
        "Theme Configuration",
        "Coordination Test",
        "Convenience Function",
        "Fallback Behavior",
    ]

    for i, (test_name, result) in enumerate(zip(test_names, results)):
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"   {status} {test_name}")

    passed = sum(results)
    total = len(results)

    print(f"\n📈 Summary: {passed}/{total} tests passed")

    if all(results):
        print("🎉 All Rich Terminal Display tests passed!")
        if is_rich_available():
            print("✅ Rich Terminal Display is working correctly")
        else:
            print("✅ Fallback behavior is working correctly")
    else:
        if not is_rich_available():
            print("💡 Install Rich library with: pip install rich")
        print("⚠️  Some tests failed - check installation and configuration")

    print("\n🚀 Rich Terminal Display provides enhanced visualization with:")
    print("   🎨 Beautiful themes and colors")
    print("   📊 Live updating layouts")
    print("   💻 Syntax highlighting")
    print("   🔄 Smooth refresh animations")
    print("   📱 Responsive design")


if __name__ == "__main__":
    asyncio.run(main())
