# -*- coding: utf-8 -*-
"""Tool module for MassGen framework."""

from ._browser_automation import browser_automation, simple_browser_automation
from ._code_executors import run_python_script, run_shell_script
from ._computer_use import computer_use
from ._file_handlers import append_file_content, read_file_content, save_file_content
from ._gemini_computer_use import gemini_computer_use
from ._manager import ToolManager
from ._result import ExecutionResult
from .workflow_toolkits import (
    BaseToolkit,
    NewAnswerToolkit,
    PostEvaluationToolkit,
    ToolType,
    VoteToolkit,
    get_post_evaluation_tools,
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
    "computer_use",
    "gemini_computer_use",
    "browser_automation",
    "simple_browser_automation",
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
    "PostEvaluationToolkit",
    "get_workflow_tools",
    "get_post_evaluation_tools",
]
