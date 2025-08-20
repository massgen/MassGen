"""
MCP-specific exceptions.
"""


class MCPError(Exception):
    """Base exception for MCP-related errors."""

    pass


class MCPConnectionError(MCPError):
    """Raised when MCP server connection fails."""

    pass


class MCPTimeoutError(MCPError):
    """Raised when MCP operation times out."""

    pass


class MCPServerError(MCPError):
    """Raised when MCP server returns an error."""

    def __init__(self, message: str, code: int = None):
        super().__init__(message)
        self.code = code


class MCPProtocolError(MCPError):
    """Raised when MCP protocol violation occurs."""

    pass
