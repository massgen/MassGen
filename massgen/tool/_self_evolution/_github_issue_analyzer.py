# -*- coding: utf-8 -*-
"""
GitHub Issue Analyzer - Self-Evolution Tool for Market Analysis

This tool enables MassGen agents to analyze GitHub issues and pull requests
to understand user needs, prioritize features, and drive market-driven development.

This demonstrates Self-Evolution: Market Analysis capabilities where
agents can autonomously understand what users need and identify next features.
"""

from typing import AsyncGenerator, List, Optional

import aiohttp

from massgen.tool._result import ExecutionResult, TextContent


async def fetch_github_issues(
    repo: str,
    state: str = "open",
    labels: Optional[List[str]] = None,
    limit: int = 50,
) -> AsyncGenerator[ExecutionResult, None]:
    """Fetch and analyze GitHub issues for a repository.

    This tool fetches issues from a GitHub repository and provides structured
    analysis to help understand user needs, feature requests, and pain points.
    Useful for market-driven development and feature prioritization.

    Note: GitHub API returns both issues and pull requests from the /issues endpoint.
    This tool automatically filters out PRs and returns only actual issues.

    Args:
        repo: Repository in format "owner/repo" (e.g., "Leezekun/MassGen")
        state: Issue state - "open", "closed", or "all" (default: "open")
        labels: Optional list of label names to filter by (e.g., ["enhancement", "bug"])
        limit: Maximum number of issues to analyze (default: 50, max: 100)

    Returns:
        ExecutionResult with issue analysis including titles, descriptions,
        labels, engagement metrics, and categorization

    Example:
        >>> async for result in fetch_github_issues(
        ...     repo="Leezekun/MassGen",
        ...     state="open",
        ...     labels=["enhancement"],
        ...     limit=10
        ... ):
        ...     print(result.output_blocks[0].data)
    """
    # Validate inputs
    if limit > 100:
        limit = 100
    if state not in ["open", "closed", "all"]:
        state = "open"

    # Initial status
    yield ExecutionResult(
        output_blocks=[
            TextContent(
                data=f"🔍 Fetching {state} issues from {repo} (limit: {limit})...",
            ),
        ],
        is_streaming=True,
        is_final=False,
    )

    try:
        # GitHub API endpoint
        api_url = f"https://api.github.com/repos/{repo}/issues"

        # Fetch more items than requested to account for PR filtering
        # GitHub API returns both issues and PRs, so we need extra buffer
        fetch_limit = min(limit * 2, 100)  # Fetch 2x requested, max 100

        # Build query parameters
        params = {
            "state": state,
            "per_page": fetch_limit,
            "sort": "created",
            "direction": "desc",
        }

        if labels:
            params["labels"] = ",".join(labels)

        # Fetch issues from GitHub API
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url, params=params) as response:
                if response.status != 200:
                    error_text = await response.text()
                    yield ExecutionResult(
                        output_blocks=[
                            TextContent(
                                data=f"❌ Error fetching issues: HTTP {response.status}\n{error_text}",
                            ),
                        ],
                        is_streaming=True,
                        is_final=True,
                    )
                    return

                issues_data = await response.json()

        # Filter out pull requests (GitHub API returns PRs as issues)
        total_fetched = len(issues_data)
        issues = [issue for issue in issues_data if "pull_request" not in issue]
        prs_filtered = total_fetched - len(issues)

        # Limit to requested number of issues
        issues = issues[:limit]

        if not issues:
            yield ExecutionResult(
                output_blocks=[
                    TextContent(
                        data=f"ℹ️  No issues found matching criteria (repo: {repo}, state: {state}, labels: {labels})\n" f"Fetched {total_fetched} items, filtered out {prs_filtered} pull requests.",
                    ),
                ],
                is_streaming=True,
                is_final=True,
            )
            return

        # Progress update with PR filtering info
        filter_msg = f" (filtered out {prs_filtered} PRs)" if prs_filtered > 0 else ""
        yield ExecutionResult(
            output_blocks=[
                TextContent(data=f"📊 Analyzing {len(issues)} issues{filter_msg}..."),
            ],
            is_streaming=True,
            is_final=False,
        )

        # Analyze issues
        analysis = _analyze_issues(issues, repo)

        # Format final result
        result_text = _format_analysis(analysis, repo, state, labels)

        yield ExecutionResult(
            output_blocks=[TextContent(data=result_text)],
            meta_info={
                "total_issues": len(issues),
                "repo": repo,
                "state": state,
                "labels": labels or [],
                "categories": list(analysis["by_category"].keys()),
            },
            is_streaming=True,
            is_final=True,
        )

    except aiohttp.ClientError as e:
        yield ExecutionResult(
            output_blocks=[
                TextContent(data=f"❌ Network error fetching issues: {str(e)}"),
            ],
            is_streaming=True,
            is_final=True,
        )
    except Exception as e:
        yield ExecutionResult(
            output_blocks=[
                TextContent(data=f"❌ Error analyzing issues: {str(e)}"),
            ],
            is_streaming=True,
            is_final=True,
        )


def _analyze_issues(issues: List[dict], repo: str) -> dict:
    """Analyze issues and extract insights."""
    analysis = {
        "total": len(issues),
        "by_category": {},
        "by_label": {},
        "top_engaged": [],
        "recent": [],
        "all_issues": [],
    }

    # Categorize issues
    for issue in issues:
        # Extract data
        title = issue.get("title", "")
        number = issue.get("number", 0)
        labels = [label["name"] for label in issue.get("labels", [])]
        comments = issue.get("comments", 0)
        reactions = issue.get("reactions", {}).get("total_count", 0)
        created_at = issue.get("created_at", "")
        body = issue.get("body", "")[:500]  # Truncate long descriptions
        url = issue.get("html_url", "")

        # Calculate engagement score
        engagement = comments + (reactions * 2)

        # Categorize by keywords
        category = _categorize_issue(title, labels, body)
        if category not in analysis["by_category"]:
            analysis["by_category"][category] = []
        analysis["by_category"][category].append(
            {"number": number, "title": title, "engagement": engagement},
        )

        # Count by label
        for label in labels:
            if label not in analysis["by_label"]:
                analysis["by_label"][label] = 0
            analysis["by_label"][label] += 1

        # Store issue data
        issue_summary = {
            "number": number,
            "title": title,
            "labels": labels,
            "comments": comments,
            "reactions": reactions,
            "engagement": engagement,
            "created_at": created_at,
            "category": category,
            "url": url,
            "body_preview": body,
        }

        analysis["all_issues"].append(issue_summary)

    # Get top engaged issues
    analysis["top_engaged"] = sorted(
        analysis["all_issues"],
        key=lambda x: x["engagement"],
        reverse=True,
    )[:5]

    # Get most recent issues
    analysis["recent"] = sorted(
        analysis["all_issues"],
        key=lambda x: x["created_at"],
        reverse=True,
    )[:5]

    return analysis


def _categorize_issue(title: str, labels: List[str], body: str) -> str:
    """Categorize an issue based on title, labels, and body."""
    title_lower = title.lower()
    body_lower = body.lower()
    labels_lower = [label.lower() for label in labels]

    # Check labels first (most reliable)
    if "bug" in labels_lower:
        return "Bug Fix"
    if "enhancement" in labels_lower or "feature" in labels_lower:
        return "Feature Request"
    if "documentation" in labels_lower or "docs" in labels_lower:
        return "Documentation"
    if "performance" in labels_lower:
        return "Performance"
    if "question" in labels_lower or "help wanted" in labels_lower:
        return "Question/Support"

    # Check title and body
    if any(word in title_lower or word in body_lower for word in ["add", "support", "implement", "new feature", "feature request"]):
        return "Feature Request"
    if any(word in title_lower or word in body_lower for word in ["bug", "error", "crash", "broken", "fix"]):
        return "Bug Fix"
    if any(word in title_lower or word in body_lower for word in ["doc", "readme"]):
        return "Documentation"
    if any(word in title_lower or word in body_lower for word in ["slow", "performance", "optimize"]):
        return "Performance"

    return "Other"


def _format_analysis(
    analysis: dict,
    repo: str,
    state: str,
    labels: Optional[List[str]],
) -> str:
    """Format the analysis into a readable report."""
    lines = []

    # Header
    lines.append(f"# GitHub Issues Analysis: {repo}")
    lines.append(f"**State**: {state}")
    if labels:
        lines.append(f"**Filters**: {', '.join(labels)}")
    lines.append(f"**Total Issues Analyzed**: {analysis['total']}")
    lines.append("")

    # Category breakdown
    lines.append("## Issues by Category")
    for category, issues in sorted(
        analysis["by_category"].items(),
        key=lambda x: len(x[1]),
        reverse=True,
    ):
        lines.append(f"- **{category}**: {len(issues)} issues")
    lines.append("")

    # Label breakdown
    if analysis["by_label"]:
        lines.append("## Most Common Labels")
        for label, count in sorted(
            analysis["by_label"].items(),
            key=lambda x: x[1],
            reverse=True,
        )[:10]:
            lines.append(f"- `{label}`: {count} issues")
        lines.append("")

    # Top engaged issues
    lines.append("## Top 5 Most Engaged Issues")
    lines.append("*(Based on comments + reactions)*")
    lines.append("")
    for i, issue in enumerate(analysis["top_engaged"], 1):
        lines.append(
            f"{i}. **#{issue['number']}**: {issue['title']} " f"({issue['comments']} comments, {issue['reactions']} reactions) " f"[{issue['category']}]",
        )
    lines.append("")

    # Recent issues
    lines.append("## 5 Most Recent Issues")
    lines.append("")
    for i, issue in enumerate(analysis["recent"], 1):
        labels_str = ", ".join(f"`{label}`" for label in issue["labels"][:3])
        if len(issue["labels"]) > 3:
            labels_str += f" +{len(issue['labels']) - 3} more"
        lines.append(
            f"{i}. **#{issue['number']}**: {issue['title']} " f"[{issue['category']}] {labels_str}",
        )
    lines.append("")

    # Recommendations
    lines.append("## 💡 Insights & Recommendations")
    lines.append("")

    # Most requested category
    if analysis["by_category"]:
        top_category = max(analysis["by_category"].items(), key=lambda x: len(x[1]))
        lines.append(
            f"- **Primary User Need**: {top_category[0]} ({len(top_category[1])} requests)",
        )

    # High engagement issues
    high_engagement = [i for i in analysis["all_issues"] if i["engagement"] > 5]
    if high_engagement:
        lines.append(
            f"- **High Engagement**: {len(high_engagement)} issues with 5+ comments/reactions",
        )

    # Feature vs bug ratio
    features = len(analysis["by_category"].get("Feature Request", []))
    bugs = len(analysis["by_category"].get("Bug Fix", []))
    if features > 0 or bugs > 0:
        lines.append(
            f"- **Feature vs Bug Ratio**: {features} features / {bugs} bugs",
        )

    lines.append("")
    lines.append(
        "**Next Steps**: Review high-engagement issues and top category for prioritization.",
    )

    return "\n".join(lines)
