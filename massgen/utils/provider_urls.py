"""Provider URL validation helpers."""

from __future__ import annotations

from urllib.parse import urlsplit

_ATLASCLOUD_HOST = "atlascloud.ai"


def is_atlascloud_url(base_url: str | None) -> bool:
    """Return whether a URL targets Atlas Cloud or one of its subdomains."""
    if not base_url:
        return False

    try:
        parsed = urlsplit(base_url)
        hostname = parsed.hostname
        has_userinfo = parsed.username is not None or parsed.password is not None
    except (TypeError, ValueError):
        return False

    if parsed.scheme.lower() not in {"http", "https"} or has_userinfo or not hostname:
        return False

    hostname = hostname.rstrip(".").lower()
    return hostname == _ATLASCLOUD_HOST or hostname.endswith(f".{_ATLASCLOUD_HOST}")
