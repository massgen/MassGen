# -*- coding: utf-8 -*-
"""Tool module for MassGen framework."""

from ._code_executors import run_python_script, run_shell_script
from ._file_handlers import append_file_content, read_file_content, save_file_content
from ._manager import ToolManager
from ._multimedia_processors import (
    dashscope_analyze_image,
    dashscope_generate_audio,
    dashscope_generate_image,
    openai_analyze_image,
    openai_create_variation,
    openai_generate_audio,
    openai_generate_image,
    openai_modify_image,
    openai_transcribe_audio,
)
from ._result import ExecutionResult
from .workflow_toolkits import (
    BaseToolkit,
    NewAnswerToolkit,
    ToolType,
    VoteToolkit,
    get_workflow_tools,
)

__all__ = [
    "ToolManager",
    "ExecutionResult",
    "two_num_tool",
    "run_python_script",
    "run_shell_script",
    "read_file_content",
    "save_file_content",
    "append_file_content",
    "dashscope_generate_image",
    "dashscope_generate_audio",
    "dashscope_analyze_image",
    "openai_generate_image",
    "openai_generate_audio",
    "openai_modify_image",
    "openai_create_variation",
    "openai_analyze_image",
    "openai_transcribe_audio",
    "BaseToolkit",
    "ToolType",
    "NewAnswerToolkit",
    "VoteToolkit",
    "get_workflow_tools",
]
