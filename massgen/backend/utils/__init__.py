"""
Backend utility modules for reducing code duplication.
These utilities are used by backend implementations without splitting them.
"""

from .streaming_utils import StreamAccumulator, StreamProcessor, parse_sse_chunk
from .message_converters import MessageConverter
from .api_helpers import APIRequestBuilder, ResponseParser

__all__ = [
    'StreamAccumulator',
    'StreamProcessor', 
    'parse_sse_chunk',
    'MessageConverter',
    'APIRequestBuilder',
    'ResponseParser'
]