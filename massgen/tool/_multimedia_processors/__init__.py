# -*- coding: utf-8 -*-
"""Multimedia processing tools."""

from ._dashscope_processors import (
    dashscope_generate_image,
    dashscope_generate_audio,
    dashscope_analyze_image,
)
from ._openai_processors import (
    openai_generate_image,
    openai_generate_audio,
    openai_modify_image,
    openai_create_variation,
    openai_analyze_image,
    openai_transcribe_audio,
)

__all__ = [
    "dashscope_generate_image",
    "dashscope_generate_audio", 
    "dashscope_analyze_image",
    "openai_generate_image",
    "openai_generate_audio",
    "openai_modify_image",
    "openai_create_variation",
    "openai_analyze_image",
    "openai_transcribe_audio",
]