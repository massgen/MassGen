# -*- coding: utf-8 -*-
from enum import Enum


class Permission(Enum):
    """File access permission types."""

    READ = "read"
    WRITE = "write"
