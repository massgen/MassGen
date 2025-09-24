#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Presentation builder that assembles modular components extracted from working presentations.
"""

import sys
from pathlib import Path


def load_component(component_name):
    """Load a component file from the components directory."""
    component_path = Path(__file__).parent / "components" / f"{component_name}.html"
    if component_path.exists():
        return component_path.read_text()
    else:
        print(f"Warning: Component {component_name} not found")
        return ""


def build_presentation(presentation_name):
    """Build a complete presentation from extracted components."""

    # Define slide titles for navigation
    slide_titles = {
        "m2l": [
            "Title - M2L Summer School",
            "Problem - Single-Agent Limitation",
            "Solution - Multi-Agent Collaboration",
            "AG2 - Research Foundation",
            "Evidence - Performance Gains",
            "Architecture - System Design",
            "Features & Capabilities",
            "Tech - Async Streaming",
            "Tech - Backend Challenges",
            "Tech - Binary Decision Framework",
            "Context Sharing - Challenge",
            "Context Sharing - Solution v0.0.12",
            "Context Sharing - In Action",
            "Benchmarking - Preliminary Results",
            "Case Study - Success Through Collaboration",
            "Case Study - When Coordination Fails",
            "Coordination Psychology - Voting Behavior",
            "Evolution",
            "Early Adopters - Community Growth",
            "Demo - Live Examples",
            "Applications",
            "Getting Started - 60 Seconds",
            "Vision - Exponential Intelligence",
            "Call to Action - Join Revolution",
        ],
        "recsys": [
            "Title - RecSys'25 Tutorial",
            "Problem - AI Scaling Challenges",
            "Solution - Multi-Agent Collaboration",
            "AG2 - Research Foundation",
            "Evidence - Performance Gains",
            "Architecture - System Design",
            "Features & Capabilities",
            "Tech - Async Streaming",
            "Tech - Backend Challenges",
            "Tech - Binary Decision Framework",
            "Context Sharing - Challenge",
            "Context Sharing - Solution",
            "Additional Context Paths",
            "Context Sharing - In Action",
            "Benchmarking - Preliminary Results",
            "Case Study - Success Through Collaboration",
            "Case Study - When Coordination Fails",
            "Coordination Psychology - Voting Behavior",
            "Evolution",
            "Early Adopters - Community Growth",
            "Demo - Live Examples",
            "Agentic Recommendation Applications",
            "Getting Started - 60 Seconds",
            "Vision - Exponential Intelligence",
            "Call to Action - Build Agentic RecSys",
        ],
        "recsys-short": [
            "Title - RecSys'25 Tutorial",
            "Problem - AI Scaling Challenges",
            "Solution - Multi-Agent Collaboration",
            "Evidence - Performance Gains",
            "Architecture - System Design",
            "Features & Capabilities",
            "Tech - Message Passing Protocols",
            "Tech - RecSys Architecture Deep Dive",
            "Case Study - Success Through Collaboration",
            "Benchmarking - Preliminary Results",
            "Agentic Recommendation Applications",
            "Demo - Live Examples",
            "Getting Started - 60 Seconds",
            "Call to Action - Build Agentic RecSys",
        ],
        "columbia": [
            "Title - Columbia University",
            "Problem - Single-Agent Limitation",
            "Solution - Multi-Agent Collaboration",
            "AG2 - Research Foundation",
            "Evidence - Performance Gains",
            "Architecture - System Design",
            "Features & Capabilities",
            "Tech - Async Streaming",
            "Tech - Backend Challenges",
            "Tech - Binary Decision Framework",
            "Context Sharing - Challenge",
            "Context Sharing - Solution v0.0.12",
            "Context Sharing - In Action",
            "Benchmarking - Preliminary Results",
            "Case Study - Success Through Collaboration",
            "Case Study - When Coordination Fails",
            "Coordination Psychology - Voting Behavior",
            "Evolution",
            "Early Adopters - Community Growth",
            "Demo - Live Examples",
            "Columbia Research Applications",
            "Getting Started - 60 Seconds",
            "Vision - Exponential Intelligence",
            "Call to Action - Join Revolution",
        ],
        "aibuilders": [
            "Title - AI Builders",
            "Problem - Single-Agent Limitation",
            "Solution - Multi-Agent Collaboration",
            "AG2 - Research Foundation",
            "Evidence - Performance Gains",
            "Architecture - System Design",
            "Features & Capabilities",
            "Tech - Async Streaming",
            "Tech - Backend Challenges",
            "Tech - Binary Decision Framework",
            "Context Sharing - Challenge",
            "Context Sharing - Solution v0.0.12",
            "Context Sharing - In Action",
            "Benchmarking - Preliminary Results",
            "Case Study - Success Through Collaboration",
            "Case Study - When Coordination Fails",
            "Coordination Psychology - Voting Behavior",
            "Evolution",
            "Early Adopters - Community Growth",
            "Demo - Live Examples",
            "Applications",
            "Getting Started - 60 Seconds",
            "Vision - Exponential Intelligence",
            "Call to Action - Join Revolution",
        ],
    }

    # Define the slide order for each presentation type (using extracted component names)
    slide_configs = {
        "m2l": [
            "slide-title-m2l",
            "slide-the-problem",
            "slide-the-solution-multi-agent-collaboration",
            "slide-ag2-research-foundation",
            "slide-evidence-performance-gains",
            "slide-architecture",
            "slide-key-features-capabilities",
            "slide-tech-deep-dive-async-streaming-architecture",
            "slide-tech-deep-dive-backend-abstraction-challenges",
            "slide-tech-deep-dive-binary-decision-framework-solution",
            "slide-context-sharing-challenge",
            "slide-context-sharing-solution",
            "slide-context-sharing-in-action",
            "slide-benchmarking-results",
            "slide-case-study-success-through-collaboration",
            "slide-case-study-when-coordination-fails",
            "slide-coordination-strategy-research",
            "slide-evolution-from-v001",
            "slide-early-adopters",
            "slide-live-demo-examples",
            "slide-applications",  # Generic applications
            "slide-getting-started",
            "slide-roadmap-vision",
            "slide-call-to-action-m2l",
        ],
        "columbia": [
            "slide-title-columbia",  # Columbia-specific title
            "slide-the-problem",
            "slide-the-solution-multi-agent-collaboration",
            "slide-ag2-research-foundation",
            "slide-evidence-performance-gains",
            "slide-architecture",
            "slide-key-features-capabilities",
            "slide-tech-deep-dive-async-streaming-architecture",
            "slide-tech-deep-dive-backend-abstraction-challenges",
            "slide-tech-deep-dive-binary-decision-framework-solution",
            "slide-context-sharing-challenge",
            "slide-context-sharing-solution",
            "slide-context-sharing-in-action",
            "slide-benchmarking-results",
            "slide-case-study-success-through-collaboration",
            "slide-case-study-when-coordination-fails",
            "slide-coordination-strategy-research",
            "slide-evolution-from-v001",
            "slide-early-adopters",
            "slide-live-demo-examples",
            "slide-columbia-research-applications",  # Columbia-specific research
            "slide-getting-started",
            "slide-roadmap-vision",
            "slide-call-to-action-columbia",
        ],
        "recsys": [
            "slide-title-recsys",
            "slide-the-problem",
            "slide-the-solution-multi-agent-collaboration",
            "slide-ag2-research-foundation",
            "slide-evidence-performance-gains",
            "slide-architecture",
            "slide-key-features-capabilities",
            "slide-tech-deep-dive-async-streaming-architecture",
            "slide-tech-deep-dive-backend-abstraction-challenges",
            "slide-tech-deep-dive-binary-decision-framework-solution",
            "slide-context-sharing-challenge",
            "slide-context-sharing-solution",
            "slide-additional-context-paths",
            "slide-context-sharing-in-action",
            "slide-benchmarking-results",
            "slide-case-study-success-through-collaboration",
            "slide-case-study-when-coordination-fails",
            "slide-coordination-strategy-research",
            "slide-evolution-from-v001",
            "slide-early-adopters",
            "slide-live-demo-examples",
            "slide-recsys-applications",  # RecSys-specific applications
            "slide-getting-started",
            "slide-roadmap-vision",
            "slide-call-to-action-recsys",
        ],
        "recsys-short": [
            "slide-title-recsys",
            "slide-the-problem",
            "slide-the-solution-multi-agent-collaboration",
            "slide-evidence-performance-gains",
            "slide-architecture",
            "slide-key-features-capabilities",
            "slide-tech-deep-dive-backend-abstraction-challenges",
            "slide-tech-deep-dive-binary-decision-framework-solution",
            "slide-case-study-success-through-collaboration",
            "slide-benchmarking-results",
            "slide-recsys-applications",
            "slide-live-demo-examples",
            "slide-getting-started",
            "slide-call-to-action-recsys",
        ],
        "aibuilders": [
            "slide-title-aibuilders",  # AI Builders-specific title
            "slide-the-problem",
            "slide-the-solution-multi-agent-collaboration",
            "slide-ag2-research-foundation",
            "slide-evidence-performance-gains",
            "slide-architecture",
            "slide-key-features-capabilities",
            "slide-tech-deep-dive-async-streaming-architecture",
            "slide-tech-deep-dive-backend-abstraction-challenges",
            "slide-tech-deep-dive-binary-decision-framework-solution",
            "slide-context-sharing-challenge",
            "slide-context-sharing-solution",
            "slide-context-sharing-in-action",
            "slide-benchmarking-results",
            "slide-case-study-success-through-collaboration",
            "slide-case-study-when-coordination-fails",
            "slide-coordination-strategy-research",
            "slide-evolution-from-v001",
            "slide-early-adopters",
            "slide-live-demo-examples",
            "slide-applications",  # Generic applications
            "slide-getting-started",
            "slide-roadmap-vision",
            "slide-call-to-action-aibuilders",
        ],
    }

    if presentation_name not in slide_configs:
        print(f"Unknown presentation type: {presentation_name}")
        print(f"Available types: {', '.join(slide_configs.keys())}")
        return

    # Start building the HTML with presentation-specific head
    head_component = f"head-{presentation_name}" if presentation_name in ["columbia", "aibuilders"] else "head"
    html_content = load_component(head_component)
    html_content += '\n<body>\n    <div class="slideshow-container">\n'

    # Add all slides for this presentation
    slides = slide_configs[presentation_name]
    for i, slide in enumerate(slides):
        slide_content = load_component(slide)
        if slide_content:
            # Add blank line separator before each slide (except the first)
            if i > 0:
                html_content += "\n"
            html_content += slide_content + "\n"

    # Add navigation and closing tags
    html_content += "    </div>\n"

    # Load navigation and inject slide titles
    nav_content = load_component("navigation")
    if nav_content and presentation_name in slide_titles:
        # Format slide titles with proper indentation (one per line)
        titles_list = slide_titles[presentation_name]
        formatted_titles = "[\n"
        for i, title in enumerate(titles_list):
            formatted_titles += f'            "{title}"'
            if i < len(titles_list) - 1:
                formatted_titles += ","
            formatted_titles += "\n"
        formatted_titles += "        ]"

        # Replace the hardcoded titles array in the navigation
        import re

        nav_content = re.sub(
            r"const slideTitles = \[.*?\];",
            f"const slideTitles = {formatted_titles};",
            nav_content,
            flags=re.DOTALL,
        )
        html_content += nav_content
    else:
        # Fallback to basic navigation
        html_content += nav_content

    # Write the complete presentation
    output_path = Path(__file__).parent / f"{presentation_name}.html"
    output_path.write_text(html_content)
    print(f"Built presentation: {output_path}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python build_presentation.py <presentation_name>")
        print("Available presentations: m2l, columbia, recsys, recsys-short, aibuilders")
        sys.exit(1)

    presentation_name = sys.argv[1]
    build_presentation(presentation_name)
