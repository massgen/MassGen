Developer API Documentation
============================

Internal API reference for MassGen contributors and developers.

.. note::
   **For Users:** If you want to use MassGen from Python, see :doc:`../reference/python_api` for the simple ``massgen.run()`` API.

   **For Contributors:** This section documents MassGen's internal classes, methods, and modules for those contributing to the codebase or building extensions.

.. toctree::
   :maxdepth: 2
   :caption: API Modules

   agents
   orchestrator
   backends
   formatter
   mcp_tools
   frontend
   token_manager

Core Components
---------------

.. automodule:: massgen
   :members: Orchestrator, AgentConfig
   :undoc-members:
   :show-inheritance:

Quick Reference
---------------

* :doc:`agents` - Agent classes and interfaces
* :doc:`orchestrator` - Orchestration and coordination components
* :doc:`backends` - Backend implementations for different LLM providers
* :doc:`formatter` - Message and tool formatting utilities
* :doc:`mcp_tools` - Model Context Protocol (MCP) integration tools
* :doc:`frontend` - Frontend displays and UI components
* :doc:`token_manager` - Token management and usage tracking