#!/usr/bin/env python3
"""
Simple validation script to check computer_use_tool.py syntax and structure.
"""

import ast
import sys
from pathlib import Path


def validate_python_file(filepath):
    """Validate Python file syntax and structure."""
    print(f"Validating: {filepath}")

    try:
        with open(filepath, "r") as f:
            content = f.read()

        # Parse the file to check syntax
        tree = ast.parse(content)

        # Count functions
        functions = [node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]
        classes = [node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]

        print(f"✅ Syntax valid")
        print(f"   Functions: {len(functions)}")
        print(f"   Classes: {len(classes)}")

        # Check for main function
        if "computer_use" in functions:
            print(f"✅ Main function 'computer_use' found")
        else:
            print(f"❌ Main function 'computer_use' not found")
            return False

        # Check for key functions
        expected_functions = [
            "computer_use",
            "run_computer_use_loop",
            "execute_browser_action",
            "execute_docker_action",
            "get_screenshot_browser",
            "get_screenshot_docker",
        ]

        found_functions = set(functions) & set(expected_functions)
        print(f"✅ Found {len(found_functions)}/{len(expected_functions)} expected functions:")
        for func in found_functions:
            print(f"   - {func}")

        # Check for exception classes
        if classes:
            print(f"✅ Exception classes defined: {', '.join(classes)}")

        return True

    except SyntaxError as e:
        print(f"❌ Syntax error: {e}")
        return False
    except Exception as e:
        print(f"❌ Validation error: {e}")
        return False


def main():
    """Main validation."""
    print("=" * 80)
    print("Computer Use Tool Validation")
    print("=" * 80)

    # Validate main implementation
    tool_path = Path(__file__).parent / "massgen" / "tool" / "_computer_use" / "computer_use_tool.py"

    if not tool_path.exists():
        print(f"❌ File not found: {tool_path}")
        sys.exit(1)

    success = validate_python_file(tool_path)

    # Validate init file
    init_path = tool_path.parent / "__init__.py"
    if init_path.exists():
        print("\n" + "=" * 80)
        success = validate_python_file(init_path) and success

    # Check YAML configs
    print("\n" + "=" * 80)
    print("Checking YAML configurations...")
    configs_dir = Path(__file__).parent / "massgen" / "configs" / "tools" / "custom_tools"

    yaml_files = [
        "computer_use_example.yaml",
        "computer_use_browser_example.yaml",
        "computer_use_docker_example.yaml",
        "computer_use_with_vision.yaml",
        "gemini_computer_use_example.yaml",
    ]

    for yaml_file in yaml_files:
        yaml_path = configs_dir / yaml_file
        if yaml_path.exists():
            print(f"✅ {yaml_file} exists")
        else:
            print(f"❌ {yaml_file} not found")
            success = False

    # Check documentation
    print("\n" + "=" * 80)
    print("Checking documentation...")

    doc_files = {
        "README.md": tool_path.parent / "README.md",
        "QUICKSTART.md": tool_path.parent / "QUICKSTART.md",
        "IMPLEMENTATION.md": Path(__file__).parent / "COMPUTER_USE_IMPLEMENTATION.md",
    }

    for name, doc_path in doc_files.items():
        if doc_path.exists():
            size = doc_path.stat().st_size
            print(f"✅ {name} exists ({size:,} bytes)")
        else:
            print(f"❌ {name} not found")
            success = False

    # Check examples
    print("\n" + "=" * 80)
    print("Checking examples...")

    examples_path = Path(__file__).parent / "examples" / "computer_use_examples.py"
    if examples_path.exists():
        print(f"✅ computer_use_examples.py exists")
        success = validate_python_file(examples_path) and success
    else:
        print(f"❌ computer_use_examples.py not found")
        success = False

    # Summary
    print("\n" + "=" * 80)
    if success:
        print("✅ All validations passed!")
        print("=" * 80)
        sys.exit(0)
    else:
        print("❌ Some validations failed!")
        print("=" * 80)
        sys.exit(1)


if __name__ == "__main__":
    main()
