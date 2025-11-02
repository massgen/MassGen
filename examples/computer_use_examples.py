#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Example scripts for testing the computer use tool.

Run with:
    python examples/computer_use_examples.py
"""

import asyncio
import os

from massgen.tool import computer_use


async def example_1_simple_search():
    """Example 1: Simple Google search"""
    print("\n" + "=" * 80)
    print("Example 1: Simple Google Search")
    print("=" * 80)

    result = await computer_use(
        task="Navigate to Google and search for 'Python asyncio'",
        environment="browser",
        display_width=1920,
        display_height=1080,
        max_iterations=15,
    )

    print(f"\nSuccess: {result.output_blocks[0].data if result.output_blocks else 'No output'}")


async def example_2_with_verification():
    """Example 2: Navigate and verify"""
    print("\n" + "=" * 80)
    print("Example 2: Navigate to Wikipedia and Verify")
    print("=" * 80)

    result = await computer_use(
        task="""
        1. Navigate to en.wikipedia.org
        2. Verify the page loaded by checking the main logo
        3. Search for 'Artificial Intelligence'
        4. Take a screenshot
        """,
        environment="browser",
        max_iterations=20,
    )

    print(f"\nSuccess: {result.output_blocks[0].data if result.output_blocks else 'No output'}")


async def example_3_form_interaction():
    """Example 3: Form interaction"""
    print("\n" + "=" * 80)
    print("Example 3: Form Interaction")
    print("=" * 80)

    result = await computer_use(
        task="""
        Navigate to https://httpbin.org/forms/post
        Fill in the form with test data
        Do NOT submit the form, just fill it in
        """,
        environment="browser",
        max_iterations=25,
    )

    print(f"\nSuccess: {result.output_blocks[0].data if result.output_blocks else 'No output'}")


async def example_4_headless_mode():
    """Example 4: Run in headless mode"""
    print("\n" + "=" * 80)
    print("Example 4: Headless Browser Mode")
    print("=" * 80)

    result = await computer_use(
        task="Go to example.com and extract the main heading text",
        environment="browser",
        environment_config={"headless": True, "browser_type": "chromium"},
        max_iterations=10,
    )

    print(f"\nSuccess: {result.output_blocks[0].data if result.output_blocks else 'No output'}")


async def example_5_multi_step_workflow():
    """Example 5: Multi-step workflow"""
    print("\n" + "=" * 80)
    print("Example 5: Multi-step Workflow")
    print("=" * 80)

    result = await computer_use(
        task="""
        Multi-step task:
        1. Go to GitHub.com
        2. In the search bar, search for 'python automation'
        3. Click on the 'Repositories' tab
        4. Note the name of the first repository
        5. Return the repository name
        """,
        environment="browser",
        display_width=1920,
        display_height=1080,
        max_iterations=30,
    )

    print(f"\nSuccess: {result.output_blocks[0].data if result.output_blocks else 'No output'}")


async def example_6_error_handling():
    """Example 6: Error handling"""
    print("\n" + "=" * 80)
    print("Example 6: Error Handling - Invalid Environment")
    print("=" * 80)

    result = await computer_use(
        task="Test error handling",
        environment="invalid_environment",  # This should fail gracefully
        max_iterations=5,
    )

    print(f"\nResult: {result.output_blocks[0].data if result.output_blocks else 'No output'}")


def check_prerequisites():
    """Check if prerequisites are installed"""
    print("\n" + "=" * 80)
    print("Checking Prerequisites")
    print("=" * 80)

    issues = []

    # Check OpenAI API key
    if not os.getenv("OPENAI_API_KEY"):
        issues.append("❌ OPENAI_API_KEY not set")
    else:
        print("✅ OPENAI_API_KEY is set")

    # Check Playwright
    try:
        import playwright

        print(f"✅ Playwright installed (version {playwright.__version__})")
    except ImportError:
        issues.append("❌ Playwright not installed (pip install playwright)")

    # Check Docker SDK (optional)
    try:
        import docker

        print(f"✅ Docker SDK installed (version {docker.__version__})")
    except ImportError:
        print("⚠️  Docker SDK not installed (optional, for Docker environments)")

    # Check Pillow (optional)
    try:
        import PIL

        print(f"✅ Pillow installed (version {PIL.__version__})")
    except ImportError:
        print("⚠️  Pillow not installed (optional, for image processing)")

    if issues:
        print("\n" + "=" * 80)
        print("Issues Found:")
        for issue in issues:
            print(f"  {issue}")
        print("\nPlease resolve these issues before running examples.")
        print("=" * 80)
        return False

    print("\n✅ All required prerequisites are installed!")
    return True


async def run_all_examples():
    """Run all examples"""
    if not check_prerequisites():
        return

    print("\n" + "=" * 80)
    print("Running Computer Use Tool Examples")
    print("=" * 80)
    print("\nNote: These examples will open browser windows.")
    print("Press Ctrl+C to stop at any time.")
    print("=" * 80)

    examples = [
        ("Simple Search", example_1_simple_search),
        ("Navigate and Verify", example_2_with_verification),
        ("Form Interaction", example_3_form_interaction),
        ("Headless Mode", example_4_headless_mode),
        ("Multi-step Workflow", example_5_multi_step_workflow),
        ("Error Handling", example_6_error_handling),
    ]

    for i, (name, example_func) in enumerate(examples, 1):
        try:
            await example_func()
        except KeyboardInterrupt:
            print("\n\nExecution interrupted by user.")
            break
        except Exception as e:
            print(f"\n❌ Example {i} ({name}) failed with error: {e}")

        if i < len(examples):
            print("\n" + "-" * 80)
            input("Press Enter to continue to the next example...")


async def run_single_example(example_number: int):
    """Run a single example by number"""
    if not check_prerequisites():
        return

    examples = {
        1: ("Simple Search", example_1_simple_search),
        2: ("Navigate and Verify", example_2_with_verification),
        3: ("Form Interaction", example_3_form_interaction),
        4: ("Headless Mode", example_4_headless_mode),
        5: ("Multi-step Workflow", example_5_multi_step_workflow),
        6: ("Error Handling", example_6_error_handling),
    }

    if example_number not in examples:
        print(f"Invalid example number: {example_number}")
        print(f"Available examples: 1-{len(examples)}")
        return

    name, example_func = examples[example_number]
    print(f"\nRunning Example {example_number}: {name}")

    try:
        await example_func()
    except Exception as e:
        print(f"\n❌ Example failed with error: {e}")


def main():
    """Main entry point"""
    import sys

    if len(sys.argv) > 1:
        try:
            example_num = int(sys.argv[1])
            asyncio.run(run_single_example(example_num))
        except ValueError:
            print("Usage: python computer_use_examples.py [example_number]")
            print("Example numbers: 1-6")
    else:
        print("\n" + "=" * 80)
        print("Computer Use Tool Examples")
        print("=" * 80)
        print("\nAvailable examples:")
        print("  1. Simple Google Search")
        print("  2. Navigate to Wikipedia and Verify")
        print("  3. Form Interaction")
        print("  4. Headless Browser Mode")
        print("  5. Multi-step Workflow")
        print("  6. Error Handling")
        print("\nUsage:")
        print("  python computer_use_examples.py        # Run all examples")
        print("  python computer_use_examples.py 1      # Run example 1 only")
        print("=" * 80)

        choice = input("\nRun all examples? (y/n): ").strip().lower()
        if choice == "y":
            asyncio.run(run_all_examples())
        else:
            example_num = input("Enter example number (1-6): ").strip()
            try:
                asyncio.run(run_single_example(int(example_num)))
            except ValueError:
                print("Invalid input. Please enter a number between 1 and 6.")


if __name__ == "__main__":
    main()
