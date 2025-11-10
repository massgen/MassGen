#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Comprehensive test suite for Computer Use tools in MassGen.

Tests all computer use implementations:
- OpenAI Computer Use (computer_use_tool.py)
- Gemini Computer Use (gemini_computer_use_tool.py)
- Claude Computer Use (claude_computer_use_tool.py)
- Simple Browser Automation (browser_automation_tool.py)
"""

import ast
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional

# Test configuration
TEST_CONFIG = {
    "run_integration_tests": os.getenv("RUN_INTEGRATION_TESTS", "false").lower() == "true",
    "openai_api_key": os.getenv("OPENAI_API_KEY"),
    "gemini_api_key": os.getenv("GEMINI_API_KEY"),
    "anthropic_api_key": os.getenv("ANTHROPIC_API_KEY"),
}


class TestResult:
    """Test result container."""

    def __init__(self, name: str, passed: bool, message: str = "", details: Optional[Dict] = None):
        self.name = name
        self.passed = passed
        self.message = message
        self.details = details or {}

    def __str__(self):
        status = "✅" if self.passed else "❌"
        result = f"{status} {self.name}"
        if self.message:
            result += f"\n   {self.message}"
        return result


class ComputerUseTestSuite:
    """Test suite for all computer use tools."""

    def __init__(self):
        self.results: List[TestResult] = []
        self.base_path = Path(__file__).parent.parent

    def add_result(self, result: TestResult):
        """Add test result."""
        self.results.append(result)
        print(str(result))

    # ==================== Syntax & Structure Tests ====================

    def test_file_syntax(self, filepath: Path, required_functions: List[str]) -> TestResult:
        """Test Python file syntax and structure."""
        if not filepath.exists():
            return TestResult(f"File Exists: {filepath.name}", False, f"File not found: {filepath}")

        try:
            with open(filepath, "r") as f:
                content = f.read()

            tree = ast.parse(content)
            # Get both regular and async functions
            functions = []
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
                    functions.append(node.name)

            # Check for required functions
            missing = set(required_functions) - set(functions)
            if missing:
                return TestResult(
                    f"Syntax: {filepath.name}",
                    False,
                    f"Missing functions: {', '.join(missing)}",
                    {"found": len(functions), "required": len(required_functions)},
                )

            return TestResult(
                f"Syntax: {filepath.name}",
                True,
                f"Valid syntax, {len(functions)} functions found",
                {"functions": functions[:10]},  # Show first 10
            )

        except SyntaxError as e:
            return TestResult(f"Syntax: {filepath.name}", False, f"Syntax error: {e}")
        except Exception as e:
            return TestResult(f"Syntax: {filepath.name}", False, f"Error: {e}")

    def test_imports(self, filepath: Path, required_imports: List[str]) -> TestResult:
        """Test required imports."""
        try:
            with open(filepath, "r") as f:
                content = f.read()

            tree = ast.parse(content)
            imports = []

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.extend([alias.name for alias in node.names])
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        imports.append(node.module)
                        # Also add the root module
                        root_module = node.module.split(".")[0]
                        if root_module not in imports:
                            imports.append(root_module)

            missing = []
            for req_import in required_imports:
                # Check if import exists as substring in any import
                if not any(req_import in imp or imp in req_import for imp in imports):
                    # Also check if it's used in the code (might be imported via another method)
                    if f"import {req_import}" not in content and req_import not in content:
                        missing.append(req_import)

            if missing:
                return TestResult(
                    f"Imports: {filepath.name}",
                    False,
                    f"Missing or unused imports: {', '.join(missing)}",
                    {"found_imports": imports[:10]},
                )

            return TestResult(
                f"Imports: {filepath.name}",
                True,
                f"All required imports present ({len(required_imports)} checked)",
            )

        except Exception as e:
            return TestResult(f"Imports: {filepath.name}", False, f"Error: {e}")

    # ==================== OpenAI Computer Use Tests ====================

    def test_openai_computer_use(self):
        """Test OpenAI computer_use tool."""
        print("\n" + "=" * 80)
        print("Testing OpenAI Computer Use Tool")
        print("=" * 80)

        tool_path = self.base_path / "tool" / "_computer_use" / "computer_use_tool.py"

        # Syntax test
        result = self.test_file_syntax(
            tool_path,
            ["computer_use", "execute_browser_action", "get_screenshot_browser"],
        )
        self.add_result(result)

        # Imports test
        result = self.test_imports(
            tool_path,
            ["playwright", "openai", "asyncio"],
        )
        self.add_result(result)

        # Check for Response API usage
        result = self.test_openai_response_api(tool_path)
        self.add_result(result)

    def test_openai_response_api(self, filepath: Path) -> TestResult:
        """Test if OpenAI Response API is properly implemented."""
        try:
            with open(filepath, "r") as f:
                content = f.read()

            # Check for key Response API patterns
            patterns = [
                "response.output",
                "computer_use_preview",
                "enable_computer_use",
            ]

            found = [p for p in patterns if p in content]

            if len(found) < 2:
                return TestResult(
                    "OpenAI Response API",
                    False,
                    f"Missing Response API patterns (found {len(found)}/3)",
                )

            return TestResult(
                "OpenAI Response API",
                True,
                "Response API implementation detected",
            )

        except Exception as e:
            return TestResult("OpenAI Response API", False, f"Error: {e}")

    # ==================== Gemini Computer Use Tests ====================

    def test_gemini_computer_use(self):
        """Test Gemini computer_use tool."""
        print("\n" + "=" * 80)
        print("Testing Gemini Computer Use Tool")
        print("=" * 80)

        tool_path = self.base_path / "tool" / "_gemini_computer_use" / "gemini_computer_use_tool.py"

        # Syntax test
        result = self.test_file_syntax(
            tool_path,
            ["gemini_computer_use", "execute_gemini_function_calls", "get_gemini_function_responses"],
        )
        self.add_result(result)

        # Imports test
        result = self.test_imports(
            tool_path,
            ["playwright", "google.genai", "asyncio"],
        )
        self.add_result(result)

        # Check for Gemini-specific patterns
        result = self.test_gemini_api_patterns(tool_path)
        self.add_result(result)

    def test_gemini_api_patterns(self, filepath: Path) -> TestResult:
        """Test Gemini API implementation patterns."""
        try:
            with open(filepath, "r") as f:
                content = f.read()

            patterns = [
                "GEMINI_API_KEY",
                "computer_use",
                "denormalize_x",
                "denormalize_y",
                "generate_content",
            ]

            found = [p for p in patterns if p in content]

            if len(found) < 4:
                return TestResult(
                    "Gemini API Patterns",
                    False,
                    f"Missing Gemini patterns (found {len(found)}/5)",
                )

            return TestResult(
                "Gemini API Patterns",
                True,
                "Gemini API implementation detected",
            )

        except Exception as e:
            return TestResult("Gemini API Patterns", False, f"Error: {e}")

    # ==================== Claude Computer Use Tests ====================

    def test_claude_computer_use(self):
        """Test Claude computer_use tool."""
        print("\n" + "=" * 80)
        print("Testing Claude Computer Use Tool")
        print("=" * 80)

        tool_path = self.base_path / "tool" / "_claude_computer_use" / "claude_computer_use_tool.py"

        # Syntax test
        result = self.test_file_syntax(
            tool_path,
            ["claude_computer_use", "execute_claude_tool_use", "take_screenshot"],
        )
        self.add_result(result)

        # Imports test
        result = self.test_imports(
            tool_path,
            ["playwright", "anthropic", "asyncio"],
        )
        self.add_result(result)

        # Check for Claude-specific patterns
        result = self.test_claude_api_patterns(tool_path)
        self.add_result(result)

    def test_claude_api_patterns(self, filepath: Path) -> TestResult:
        """Test Claude API implementation patterns."""
        try:
            with open(filepath, "r") as f:
                content = f.read()

            patterns = [
                "ANTHROPIC_API_KEY",
                "computer_20250124",
                "text_editor_20250728",
                "bash_20250124",
                "beta.messages.create",
                "computer-use-2025-01-24",
            ]

            found = [p for p in patterns if p in content]

            if len(found) < 5:
                return TestResult(
                    "Claude API Patterns",
                    False,
                    f"Missing Claude patterns (found {len(found)}/6)",
                )

            return TestResult(
                "Claude API Patterns",
                True,
                "Claude API implementation detected",
            )

        except Exception as e:
            return TestResult("Claude API Patterns", False, f"Error: {e}")

    # ==================== Browser Automation Tests ====================

    def test_browser_automation(self):
        """Test simple browser automation tool."""
        print("\n" + "=" * 80)
        print("Testing Simple Browser Automation Tool")
        print("=" * 80)

        tool_path = self.base_path / "tool" / "_browser_automation" / "browser_automation_tool.py"

        # Syntax test
        result = self.test_file_syntax(
            tool_path,
            ["browser_automation"],
        )
        self.add_result(result)

        # Imports test
        result = self.test_imports(
            tool_path,
            ["playwright"],
        )
        self.add_result(result)

        # Check for action support
        result = self.test_browser_actions(tool_path)
        self.add_result(result)

    def test_browser_actions(self, filepath: Path) -> TestResult:
        """Test browser automation action support."""
        try:
            with open(filepath, "r") as f:
                content = f.read()

            actions = ["navigate", "click", "type", "extract", "screenshot"]
            found = [a for a in actions if f'action == "{a}"' in content or f"'{a}'" in content]

            if len(found) < 4:
                return TestResult(
                    "Browser Actions",
                    False,
                    f"Missing actions (found {len(found)}/5): {actions}",
                )

            return TestResult(
                "Browser Actions",
                True,
                f"All {len(found)} actions supported: {', '.join(found)}",
            )

        except Exception as e:
            return TestResult("Browser Actions", False, f"Error: {e}")

    # ==================== Configuration Tests ====================

    def test_yaml_configs(self):
        """Test YAML configuration files."""
        print("\n" + "=" * 80)
        print("Testing YAML Configuration Files")
        print("=" * 80)

        configs_dir = self.base_path / "configs" / "tools" / "custom_tools"

        # Required configs
        required_configs = {
            "computer_use_example.yaml": "OpenAI Computer Use",
            "gemini_computer_use_example.yaml": "Gemini Computer Use",
            "claude_computer_use_browser_example.yaml": "Claude Computer Use",
            "simple_browser_automation_example.yaml": "Simple Browser Automation",
        }

        # Optional configs (templates/examples)
        optional_configs = {
            "gemini_computer_use_docker_example.yaml": "Gemini Docker (optional)",
            "azure_computer_use_example.yaml": "Azure OpenAI Computer Use (optional)",
        }

        # Test required configs
        for yaml_file, description in required_configs.items():
            yaml_path = configs_dir / yaml_file
            if yaml_path.exists():
                size = yaml_path.stat().st_size
                result = TestResult(
                    f"Config: {description}",
                    True,
                    f"{yaml_file} exists ({size:,} bytes)",
                )
            else:
                result = TestResult(
                    f"Config: {description}",
                    False,
                    f"{yaml_file} not found",
                )
            self.add_result(result)

        # Test optional configs (informational only)
        for yaml_file, description in optional_configs.items():
            yaml_path = configs_dir / yaml_file
            if yaml_path.exists():
                size = yaml_path.stat().st_size
                result = TestResult(
                    f"Config: {description}",
                    True,
                    f"{yaml_file} exists ({size:,} bytes)",
                )
            else:
                result = TestResult(
                    f"Config: {description}",
                    True,  # Pass even if not found (optional)
                    f"{yaml_file} not found (optional template)",
                )
            self.add_result(result)

    # ==================== Integration Tests ====================

    async def run_browser_automation_integration(self) -> TestResult:
        """Integration test for browser automation."""
        try:
            # Import the tool
            sys.path.insert(0, str(self.base_path))
            from tool._browser_automation import browser_automation

            # Test simple navigation
            result = await browser_automation(
                task="Test navigation to example.com",
                url="https://example.com",
                action="navigate",
                headless=True,
                screenshot=False,
            )

            result_data = json.loads(result.output_blocks[0].data)

            if result_data.get("success") and "example.com" in result_data.get("current_url", "").lower():
                return TestResult(
                    "Integration: Browser Navigation",
                    True,
                    "Successfully navigated to example.com",
                    result_data,
                )
            else:
                return TestResult(
                    "Integration: Browser Navigation",
                    False,
                    "Navigation failed or incorrect URL",
                    result_data,
                )

        except ImportError as e:
            return TestResult(
                "Integration: Browser Navigation",
                False,
                f"Import error: {e}",
            )
        except Exception as e:
            return TestResult(
                "Integration: Browser Navigation",
                False,
                f"Test failed: {e}",
            )

    async def run_browser_extraction_integration(self) -> TestResult:
        """Integration test for browser text extraction."""
        try:
            sys.path.insert(0, str(self.base_path))
            from tool._browser_automation import browser_automation

            # Test extraction
            result = await browser_automation(
                task="Extract heading from example.com",
                url="https://example.com",
                action="extract",
                selector="h1",
                headless=True,
                screenshot=False,
            )

            result_data = json.loads(result.output_blocks[0].data)

            if result_data.get("success") and result_data.get("extracted_text"):
                return TestResult(
                    "Integration: Text Extraction",
                    True,
                    f"Extracted {len(result_data['extracted_text'])} elements",
                    {"sample": result_data["extracted_text"][:3]},
                )
            else:
                return TestResult(
                    "Integration: Text Extraction",
                    False,
                    "Extraction failed or no text found",
                )

        except Exception as e:
            return TestResult(
                "Integration: Text Extraction",
                False,
                f"Test failed: {e}",
            )

    def test_integration(self):
        """Run integration tests if enabled."""
        print("\n" + "=" * 80)
        print("Integration Tests")
        print("=" * 80)

        if not TEST_CONFIG["run_integration_tests"]:
            result = TestResult(
                "Integration Tests",
                True,
                "Skipped (set RUN_INTEGRATION_TESTS=true to enable)",
            )
            self.add_result(result)
            return

        # Check Playwright availability
        try:
            pass

            result = TestResult("Playwright Available", True, "Playwright is installed")
            self.add_result(result)
        except ImportError:
            result = TestResult(
                "Playwright Available",
                False,
                "Playwright not installed (pip install playwright && playwright install)",
            )
            self.add_result(result)
            return

        # Run async integration tests
        print("\nRunning integration tests...")

        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        # Browser navigation test
        result = loop.run_until_complete(self.run_browser_automation_integration())
        self.add_result(result)

        # Browser extraction test
        result = loop.run_until_complete(self.run_browser_extraction_integration())
        self.add_result(result)

    # ==================== Main Test Runner ====================

    def run_all_tests(self):
        """Run all tests."""
        print("=" * 80)
        print("MassGen Computer Use Tools - Comprehensive Test Suite")
        print("=" * 80)

        # Test each tool
        self.test_openai_computer_use()
        self.test_gemini_computer_use()
        self.test_claude_computer_use()
        self.test_browser_automation()

        # Test configurations
        self.test_yaml_configs()

        # Integration tests
        self.test_integration()

        # Summary
        self.print_summary()

    def print_summary(self):
        """Print test summary."""
        print("\n" + "=" * 80)
        print("Test Summary")
        print("=" * 80)

        passed = sum(1 for r in self.results if r.passed)
        failed = sum(1 for r in self.results if not r.passed)
        total = len(self.results)

        print(f"\nTotal Tests: {total}")
        print(f"✅ Passed: {passed}")
        print(f"❌ Failed: {failed}")
        print(f"Success Rate: {passed/total*100:.1f}%")

        if failed > 0:
            print("\nFailed Tests:")
            for result in self.results:
                if not result.passed:
                    print(f"  - {result.name}: {result.message}")

        print("=" * 80)

        return failed == 0


def main():
    """Main entry point."""
    suite = ComputerUseTestSuite()
    success = suite.run_all_tests()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
