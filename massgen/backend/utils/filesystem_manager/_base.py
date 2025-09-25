from enum import Enum

class Permission(Enum):
    """File access permission types."""

    READ = "read"
    WRITE = "write"