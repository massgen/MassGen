# -*- coding: utf-8 -*-
"""
Crawl4AI Web Scraping Tools - Custom tool wrapper for crawl4ai REST API.

This module provides MassGen custom tools that wrap the crawl4ai Docker container's
REST API, providing powerful web scraping capabilities without MCP protocol overhead.

Available Tools:
- crawl4ai_md: Extract clean markdown from webpages
- crawl4ai_html: Get preprocessed HTML
- crawl4ai_screenshot: Capture webpage screenshots
- crawl4ai_pdf: Generate PDFs from webpages
- crawl4ai_execute_js: Run JavaScript on pages
- crawl4ai_crawl: Crawl multiple URLs
- crawl4ai_ask: Query crawl4ai library documentation

Prerequisites:
- Crawl4ai Docker container running at http://localhost:11235
  Start with: docker run -d -p 11235:11235 --name crawl4ai --shm-size=1g unclecode/crawl4ai:latest
"""

import json
from typing import List, Optional
from urllib.parse import urlparse

import httpx

from massgen.tool._result import ExecutionResult, TextContent

# Base URL for crawl4ai container
CRAWL4AI_BASE_URL = "http://localhost:11235"
DEFAULT_TIMEOUT = 60.0


def _validate_url(url: str) -> tuple[bool, str]:
    """Validate that a URL is properly formatted.

    Args:
        url: URL to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        parsed = urlparse(url)
        if not parsed.scheme or parsed.scheme not in ("http", "https"):
            return False, f"URL must use http or https protocol, got: {parsed.scheme or 'none'}"
        if not parsed.netloc:
            return False, "URL must have a valid domain"
        return True, ""
    except Exception as e:
        return False, f"Invalid URL format: {str(e)}"


async def _check_url_accessible(url: str) -> tuple[bool, str, int]:
    """Check if a URL is accessible via HEAD request.

    Args:
        url: URL to check

    Returns:
        Tuple of (is_accessible, error_message, status_code)
    """
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            response = await client.head(url)
            if response.status_code >= 400:
                return False, f"URL returned error status {response.status_code}", response.status_code
            return True, "", response.status_code
    except httpx.ConnectError:
        return False, "Could not connect to URL (connection refused or DNS error)", 0
    except httpx.TimeoutException:
        return False, "URL request timed out", 0
    except Exception as e:
        return False, f"Error checking URL: {str(e)}", 0


async def _check_docker_running() -> tuple[bool, str]:
    """Check if the crawl4ai Docker container is running and accessible.

    Returns:
        Tuple of (is_running, error_message)
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{CRAWL4AI_BASE_URL}/health")
            if response.status_code == 200:
                return True, ""
            return False, f"crawl4ai container health check failed with status {response.status_code}"
    except httpx.ConnectError:
        return False, (
            "crawl4ai Docker container is not running or not accessible at http://localhost:11235\n\n"
            "To start the container, run:\n"
            "  docker pull unclecode/crawl4ai:latest\n"
            "  docker run -d -p 11235:11235 --name crawl4ai --shm-size=1g unclecode/crawl4ai:latest\n\n"
            "To verify it's running:\n"
            "  docker ps | grep crawl4ai"
        )
    except httpx.TimeoutException:
        return False, "crawl4ai container is not responding (timeout). Check if the container is healthy."
    except Exception as e:
        return False, f"Error checking crawl4ai container: {str(e)}"


def require_docker(func):
    """Decorator that checks if Docker container is running before executing the function."""
    from functools import wraps

    @wraps(func)
    async def wrapper(*args, **kwargs):
        is_docker_running, docker_error = await _check_docker_running()
        if not is_docker_running:
            return ExecutionResult(
                output_blocks=[
                    TextContent(
                        data=json.dumps(
                            {
                                "success": False,
                                "error": "Docker container not running",
                                "details": docker_error,
                            },
                            indent=2,
                        ),
                    ),
                ],
            )
        return await func(*args, **kwargs)

    return wrapper


@require_docker
async def crawl4ai_md(
    url: str,
    filter_type: str = "fit",
    query: Optional[str] = None,
) -> ExecutionResult:
    """Extract clean markdown text content from a webpage.

    PRIMARY TOOL for reading and understanding website content. Use this when you need to:
    - Read articles, documentation, blog posts, or any text content
    - Understand what a webpage says
    - Extract information from a website
    - Summarize web content

    DO NOT use screenshot tools for reading content - use this tool instead.

    Fetches webpage and converts to clean markdown format ideal for LLM consumption.
    Uses intelligent content filtering to extract only relevant text.

    Args:
        url: The webpage URL to scrape (must be absolute http/https URL)
        filter_type: Content filter strategy - "fit" (smart filtering, default),
                     "raw" (no filtering), "bm25" (keyword-based), "llm" (AI-powered)
        query: Query string for BM25/LLM filters (optional)

    Returns:
        ExecutionResult containing:
        - success: Whether the operation succeeded
        - url: The scraped URL
        - markdown: Clean markdown content
        - filter: Filter strategy used

    Examples:
        >>> result = await crawl4ai_md("https://example.com")
        >>> # Returns markdown of the page

        >>> result = await crawl4ai_md("https://news.ycombinator.com", filter_type="bm25", query="AI safety")
        >>> # Returns filtered content matching "AI safety"
    """
    # Validate URL format
    is_valid, error_msg = _validate_url(url)
    if not is_valid:
        return ExecutionResult(
            output_blocks=[
                TextContent(
                    data=json.dumps(
                        {
                            "success": False,
                            "error": f"Invalid URL: {error_msg}",
                            "url": url,
                        },
                        indent=2,
                    ),
                ),
            ],
        )

    # Check if URL is accessible
    is_accessible, access_error, status_code = await _check_url_accessible(url)
    if not is_accessible:
        return ExecutionResult(
            output_blocks=[
                TextContent(
                    data=json.dumps(
                        {
                            "success": False,
                            "error": f"URL not accessible: {access_error}",
                            "url": url,
                            "status_code": status_code,
                        },
                        indent=2,
                    ),
                ),
            ],
        )

    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            response = await client.post(
                f"{CRAWL4AI_BASE_URL}/md",
                json={
                    "url": url,
                    "f": filter_type,
                    "q": query,
                },
            )
            response.raise_for_status()
            data = response.json()

        if data.get("success"):
            result_data = {
                "success": True,
                "url": data.get("url"),
                "markdown": data.get("markdown"),
                "filter": data.get("filter"),
            }
        else:
            result_data = {
                "success": False,
                "error": "Crawl failed",
                "url": url,
            }

        return ExecutionResult(
            output_blocks=[TextContent(data=json.dumps(result_data, indent=2))],
        )

    except httpx.HTTPStatusError as e:
        return ExecutionResult(
            output_blocks=[
                TextContent(
                    data=json.dumps(
                        {
                            "success": False,
                            "error": f"HTTP error {e.response.status_code}: {e.response.reason_phrase}",
                            "url": url,
                            "status_code": e.response.status_code,
                        },
                        indent=2,
                    ),
                ),
            ],
        )
    except Exception as e:
        return ExecutionResult(
            output_blocks=[
                TextContent(
                    data=json.dumps(
                        {
                            "success": False,
                            "error": f"Failed to scrape URL: {str(e)}",
                            "url": url,
                        },
                        indent=2,
                    ),
                ),
            ],
        )


@require_docker
async def crawl4ai_html(url: str) -> ExecutionResult:
    """Extract preprocessed HTML from a webpage.

    Fetches and preprocesses HTML, removing scripts/styles for cleaner
    structure extraction. Useful for building schemas or parsing structured data.

    Args:
        url: The webpage URL to scrape

    Returns:
        ExecutionResult containing preprocessed HTML

    Examples:
        >>> result = await crawl4ai_html("https://example.com")
        >>> # Returns cleaned HTML
    """
    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            response = await client.post(
                f"{CRAWL4AI_BASE_URL}/html",
                json={"url": url},
            )
            response.raise_for_status()
            data = response.json()

        result_data = {
            "success": True,
            "url": url,
            "html": data.get("html", ""),
        }

        return ExecutionResult(
            output_blocks=[TextContent(data=json.dumps(result_data, indent=2))],
        )

    except Exception as e:
        return ExecutionResult(
            output_blocks=[
                TextContent(
                    data=json.dumps(
                        {"success": False, "error": str(e), "url": url},
                        indent=2,
                    ),
                ),
            ],
        )


@require_docker
async def crawl4ai_screenshot(
    url: str,
    wait_seconds: float = 2.0,
    output_filename: Optional[str] = None,
    workspace_path: Optional[str] = None,
) -> ExecutionResult:
    """Capture a screenshot of a webpage.

    Takes full-page PNG screenshot after waiting for page load.
    Saves to agent's workspace if filename provided.
    Should verify the webpage content either visually or via HTML/markdown tools.

    Args:
        url: The webpage URL to screenshot
        wait_seconds: Seconds to wait before capturing (default: 2.0)
        output_filename: Optional filename to save in workspace (e.g., "screenshot.png")
        workspace_path: Agent's workspace directory (auto-injected)

    Returns:
        ExecutionResult with base64 screenshot or saved file path

    Examples:
        >>> result = await crawl4ai_screenshot("https://example.com")
        >>> # Returns base64-encoded screenshot

        >>> result = await crawl4ai_screenshot("https://example.com", output_filename="example.png")
        >>> # Saves example.png to agent's workspace
    """
    import base64
    from pathlib import Path

    try:
        # Always get base64 response (don't use output_path - that saves in container)
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            response = await client.post(
                f"{CRAWL4AI_BASE_URL}/screenshot",
                json={
                    "url": url,
                    "screenshot_wait_for": wait_seconds,
                },
            )
            response.raise_for_status()
            data = response.json()

        screenshot_b64 = data.get("screenshot")

        if not screenshot_b64:
            return ExecutionResult(
                output_blocks=[
                    TextContent(
                        data=json.dumps(
                            {"success": False, "error": "No screenshot returned", "url": url},
                            indent=2,
                        ),
                    ),
                ],
            )

        # If filename provided, save to agent's workspace
        if output_filename:
            screenshot_data = base64.b64decode(screenshot_b64)

            # Use workspace_path if provided (auto-injected by MassGen)
            if workspace_path:
                workspace_dir = Path(workspace_path)
            else:
                # Fallback: use current directory if workspace_path not provided
                workspace_dir = Path.cwd()

            output_path = workspace_dir / output_filename
            output_path.write_bytes(screenshot_data)

            result_data = {
                "success": True,
                "url": url,
                "saved_to": str(output_path),
                "filename": output_filename,
            }
        else:
            result_data = {
                "success": True,
                "url": url,
                "screenshot_base64": screenshot_b64[:100] + "...",  # Preview
                "note": "Provide output_filename parameter to save to workspace",
            }

        return ExecutionResult(
            output_blocks=[TextContent(data=json.dumps(result_data, indent=2))],
        )

    except Exception as e:
        return ExecutionResult(
            output_blocks=[
                TextContent(
                    data=json.dumps(
                        {"success": False, "error": str(e), "url": url},
                        indent=2,
                    ),
                ),
            ],
        )


@require_docker
async def crawl4ai_pdf(
    url: str,
    output_filename: Optional[str] = None,
    workspace_path: Optional[str] = None,
) -> ExecutionResult:
    """Generate a PDF from a webpage.

    Creates a PDF document of the rendered page. Useful for archival
    or generating printable versions. Saves to agent's workspace if filename provided.

    Args:
        url: The webpage URL to convert to PDF
        output_filename: Optional filename to save in workspace (e.g., "page.pdf")
        workspace_path: Agent's workspace directory (auto-injected by MassGen)

    Returns:
        ExecutionResult with saved file path

    Examples:
        >>> result = await crawl4ai_pdf("https://example.com", output_filename="example.pdf")
        >>> # Saves example.pdf to agent's workspace
    """
    import base64
    from pathlib import Path

    try:
        # Always get base64 response
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            response = await client.post(
                f"{CRAWL4AI_BASE_URL}/pdf",
                json={"url": url},
            )
            response.raise_for_status()
            data = response.json()

        pdf_b64 = data.get("pdf")

        if not pdf_b64:
            return ExecutionResult(
                output_blocks=[
                    TextContent(
                        data=json.dumps(
                            {"success": False, "error": "No PDF returned", "url": url},
                            indent=2,
                        ),
                    ),
                ],
            )

        # If filename provided, save to agent's workspace
        if output_filename:
            pdf_data = base64.b64decode(pdf_b64)

            # Use workspace_path if provided (auto-injected by MassGen)
            if workspace_path:
                workspace_dir = Path(workspace_path)
            else:
                # Fallback: use current directory if workspace_path not provided
                workspace_dir = Path.cwd()

            output_path = workspace_dir / output_filename
            output_path.write_bytes(pdf_data)

            result_data = {
                "success": True,
                "url": url,
                "saved_to": str(output_path),
                "filename": output_filename,
            }
        else:
            result_data = {
                "success": True,
                "url": url,
                "pdf_size_bytes": len(base64.b64decode(pdf_b64)),
                "note": "Provide output_filename parameter to save to workspace",
            }

        return ExecutionResult(
            output_blocks=[TextContent(data=json.dumps(result_data, indent=2))],
        )

    except Exception as e:
        return ExecutionResult(
            output_blocks=[
                TextContent(
                    data=json.dumps(
                        {"success": False, "error": str(e), "url": url},
                        indent=2,
                    ),
                ),
            ],
        )


@require_docker
async def crawl4ai_execute_js(
    url: str,
    scripts: List[str],
) -> ExecutionResult:
    """Execute JavaScript on a webpage and return results.

    Runs custom JavaScript in the page context. Each script should be
    an expression that returns a value (can be IIFE or async function).
    Returns full CrawlResult including markdown, links, and script outputs.

    Args:
        url: The webpage URL to execute scripts on
        scripts: List of JavaScript code snippets to execute in order

    Returns:
        ExecutionResult with script execution results and page content

    Examples:
        >>> result = await crawl4ai_execute_js(
        ...     "https://example.com",
        ...     ["document.title", "document.links.length"]
        ... )
        >>> # Returns page title and number of links

        >>> result = await crawl4ai_execute_js(
        ...     "https://example.com",
        ...     ["(async () => { await someAsyncOperation(); return result; })()"]
        ... )
        >>> # Executes async JavaScript
    """
    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            response = await client.post(
                f"{CRAWL4AI_BASE_URL}/execute_js",
                json={
                    "url": url,
                    "scripts": scripts,
                },
            )
            response.raise_for_status()
            data = response.json()

        # Extract key information from CrawlResult
        result_data = {
            "success": data.get("success", True),
            "url": data.get("url"),
            "markdown": data.get("markdown"),
            "js_execution_result": data.get("js_execution_result"),
            "links": data.get("links"),
        }

        return ExecutionResult(
            output_blocks=[TextContent(data=json.dumps(result_data, indent=2))],
        )

    except Exception as e:
        return ExecutionResult(
            output_blocks=[
                TextContent(
                    data=json.dumps(
                        {"success": False, "error": str(e), "url": url},
                        indent=2,
                    ),
                ),
            ],
        )


@require_docker
async def crawl4ai_crawl(
    urls: List[str],
    max_urls: int = 100,
) -> ExecutionResult:
    """Crawl multiple URLs in parallel.

    Efficiently scrapes multiple pages concurrently. Returns results
    for all URLs. Limited to 100 URLs per request.

    Args:
        urls: List of URLs to crawl (max 100)
        max_urls: Maximum number of URLs to process (default: 100)

    Returns:
        ExecutionResult with results for all crawled URLs

    Examples:
        >>> result = await crawl4ai_crawl([
        ...     "https://example.com",
        ...     "https://example.org",
        ...     "https://example.net",
        ... ])
        >>> # Returns markdown and metadata for all pages
    """
    try:
        # Limit URLs to prevent overload
        urls_to_crawl = urls[: min(len(urls), max_urls, 100)]

        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT * 3) as client:
            response = await client.post(
                f"{CRAWL4AI_BASE_URL}/crawl",
                json={"urls": urls_to_crawl},
            )
            response.raise_for_status()
            data = response.json()

        result_data = {
            "success": True,
            "total_urls": len(urls_to_crawl),
            "results": data.get("results", []),
        }

        return ExecutionResult(
            output_blocks=[TextContent(data=json.dumps(result_data, indent=2))],
        )

    except Exception as e:
        return ExecutionResult(
            output_blocks=[
                TextContent(
                    data=json.dumps(
                        {
                            "success": False,
                            "error": str(e),
                            "urls": urls[:5],  # Show first 5 for debugging
                        },
                        indent=2,
                    ),
                ),
            ],
        )


# async def crawl4ai_ask(
#     query: str,
#     context_type: str = "all",
#     max_results: int = 20,
# ) -> ExecutionResult:
#     """Query the Crawl4AI library documentation and code context.

#     Searches crawl4ai documentation using BM25 search. Useful for
#     learning about library features or getting code examples.

#     Args:
#         query: Search query (recommended, leave empty for all context)
#         context_type: Type of context - "code", "doc", or "all" (default: "all")
#         max_results: Maximum number of results (default: 20)

#     Returns:
#         ExecutionResult with relevant documentation snippets

#     Examples:
#         >>> result = await crawl4ai_ask("How do I extract structured data?")
#         >>> # Returns documentation about data extraction

#         >>> result = await crawl4ai_ask("JavaScript execution", context_type="code")
#         >>> # Returns code examples for JS execution
#     """
#     try:
#         async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
#             response = await client.get(
#                 f"{CRAWL4AI_BASE_URL}/ask",
#                 params={
#                     "query": query,
#                     "context_type": context_type,
#                     "max_results": max_results,
#                 }
#             )
#             response.raise_for_status()
#             data = response.json()

#         result_data = {
#             "success": True,
#             "query": query,
#             "context_type": context_type,
#             "results": data.get("results", data),  # Flexible result format
#         }

#         return ExecutionResult(
#             output_blocks=[TextContent(data=json.dumps(result_data, indent=2))],
#         )

#     except Exception as e:
#         return ExecutionResult(
#             output_blocks=[
#                 TextContent(
#                     data=json.dumps(
#                         {"success": False, "error": str(e), "query": query},
#                         indent=2,
#                     )
#                 )
#             ],
#         )
