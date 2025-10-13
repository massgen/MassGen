Multimodal Capabilities
=======================

MassGen supports multimodal AI workflows, enabling agents to work with images and other visual content. This includes image generation, image understanding, and file-based interactions.

.. note::

   Multimodal support was introduced in **v0.0.27** and is currently available through OpenAI backends (GPT-4o, GPT-5-nano).

Overview
--------

Multimodal capabilities extend MassGen's multi-agent collaboration to visual tasks:

* **Image Generation**: Create images from text descriptions
* **Image Understanding**: Analyze and describe image content
* **File Upload and Search**: Work with documents and visual files
* **Multimodal MCP Tools**: Read images as base64 data for processing

Image Generation
----------------

Image generation allows agents to create visual content from textual descriptions. Multiple agents can collaborate to refine image generation prompts and produce high-quality results.

Basic Configuration
~~~~~~~~~~~~~~~~~~~

Enable image generation in your agent configuration:

.. code-block:: yaml

   agents:
     - id: "image_creator"
       backend:
         type: "openai"
         model: "gpt-4o"
         cwd: "workspace"
         enable_image_generation: true  # Enable image generation

   orchestrator:
     snapshot_storage: "snapshots"
     agent_temporary_workspace: "temp_workspaces"

**Example Command:**

.. code-block:: bash

   massgen \
     --config @examples/basic/single/single_gpt4o_image_generation.yaml \
     "Generate an image of gray tabby cat hugging an otter with an orange scarf."

Multi-Agent Image Generation
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Leverage multiple agents to refine and improve image generation prompts:

.. code-block:: yaml

   agents:
     - id: "gpt4o_1"
       backend:
         type: "openai"
         model: "gpt-4o"
         text:
           verbosity: "medium"
         cwd: "workspace1"
         enable_image_generation: true

     - id: "gpt4o_2"
       backend:
         type: "openai"
         model: "gpt-4o"
         text:
           verbosity: "medium"
         cwd: "workspace2"
         enable_image_generation: true

   orchestrator:
     snapshot_storage: "snapshots"
     agent_temporary_workspace: "temp_workspaces"

**Example Command:**

.. code-block:: bash

   massgen \
     --config @examples/basic/multi/gpt4o_image_generation.yaml \
     "Create a professional logo for a tech startup focused on AI"

**How It Works:**

1. Both agents analyze the image generation request
2. Agents collaborate to refine the prompt and approach
3. The winning agent executes the image generation
4. Generated images are saved to the agent's workspace

Image Understanding
-------------------

Image understanding enables agents to analyze visual content, extract information, and answer questions about images.

Basic Configuration
~~~~~~~~~~~~~~~~~~~

Upload images for agents to analyze:

.. code-block:: yaml

   agents:
     - id: "vision_agent"
       backend:
         type: "openai"
         model: "gpt-5-nano"
         upload_files:
           - image_path: "@examples/resources/v0.0.27-example/multimodality.jpg"
       system_message: "You are a helpful assistant"

**Example Command:**

.. code-block:: bash

   massgen \
     --config @examples/basic/single/single_gpt5nano_image_understanding.yaml \
     "Please summarize the content in this image."

Multi-Agent Image Analysis
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Multiple agents can provide diverse perspectives on image content:

.. code-block:: yaml

   agents:
     - id: "response_agent1"
       backend:
         type: "openai"
         model: "gpt-5-nano"
         upload_files:
           - image_path: "@examples/resources/v0.0.27-example/multimodality.jpg"
       system_message: "You are a helpful assistant"

     - id: "response_agent2"
       backend:
         type: "openai"
         model: "gpt-5-nano"
         upload_files:
           - image_path: "@examples/resources/v0.0.27-example/multimodality.jpg"
       system_message: "You are a helpful assistant"

**Example Command:**

.. code-block:: bash

   massgen \
     --config @examples/basic/multi/gpt5nano_image_understanding.yaml \
     "Analyze this image and identify key elements, mood, and composition."

**Use Cases:**

* Document analysis and OCR
* Visual content description for accessibility
* Image classification and categorization
* Design feedback and critique
* Scene understanding for robotics

File Upload and Search
----------------------

File upload and search capabilities enable agents to work with documents and perform retrieval-augmented generation (RAG).

File Upload Configuration
~~~~~~~~~~~~~~~~~~~~~~~~~~

Upload files for agent access:

.. code-block:: yaml

   agents:
     - id: "document_agent"
       backend:
         type: "openai"
         model: "gpt-5-nano"
         upload_files:
           - image_path: "path/to/document.pdf"
           - image_path: "path/to/image.jpg"

**Supported File Types:**

* Images: JPG, PNG, GIF, WebP
* Documents: PDF (with text extraction)
* Future support planned for audio, video, and other formats

Vector Store Management
~~~~~~~~~~~~~~~~~~~~~~~

The OpenAI backend automatically manages vector stores for file search:

.. code-block:: yaml

   agents:
     - id: "search_agent"
       backend:
         type: "openai"
         model: "gpt-5-nano"
         upload_files:
           - image_path: "documents/report.pdf"
         enable_file_search: true  # Enable vector store search

**Features:**

* Automatic vector store creation
* Efficient similarity search
* Context retrieval for Q&A
* Cleanup utilities for uploaded files

**Example Use Case:**

.. code-block:: bash

   # Document Q&A with file search
   massgen \
     --config @examples/basic/single/single_gpt5nano_file_search.yaml \
     "What are the main conclusions from the uploaded research paper?"

Multimodal MCP Tools
--------------------

MassGen provides MCP-based tools for working with multimodal content in agent workspaces.

read_multimodal_files Tool
~~~~~~~~~~~~~~~~~~~~~~~~~~~

The ``read_multimodal_files`` tool reads images and encodes them as base64 data with MIME type detection:

.. code-block:: yaml

   agents:
     - id: "mcp_agent"
       backend:
         type: "openai"
         model: "gpt-5-nano"
         mcp_servers:
           - name: "workspace"
             type: "stdio"
             command: "python"
             args: ["-m", "massgen.mcp_tools.workspace_tools_server"]

**How It Works:**

1. Agent requests to read an image file from workspace
2. Tool detects MIME type (image/jpeg, image/png, etc.)
3. Image is encoded as base64 data
4. Agent receives structured multimodal content

**Benefits:**

* Seamless integration with MCP workflow
* Automatic format detection
* Base64 encoding for API compatibility
* Support for various image formats

StreamChunk Architecture
~~~~~~~~~~~~~~~~~~~~~~~~

Multimodal content is handled through the ``StreamChunk`` architecture:

**Text Content:**

.. code-block:: python

   from massgen.stream_chunk import TextChunk

   chunk = TextChunk(content="This is a response")

**Multimodal Content:**

.. code-block:: python

   from massgen.stream_chunk import MultimodalChunk

   chunk = MultimodalChunk(
       content_type="image",
       data="base64_encoded_image_data",
       mime_type="image/jpeg"
   )

**Architecture Benefits:**

* Unified message handling for text and multimodal content
* Streaming support for real-time processing
* Extensible for future content types (audio, video, documents)

Supported Backends
------------------

Multimodal capabilities vary by backend:

.. list-table:: Backend Multimodal Support
   :header-rows: 1
   :widths: 20 15 15 15 35

   * - Backend
     - Image Gen
     - Image Understanding
     - File Upload
     - Notes
   * - ``openai``
     - ✅
     - ✅
     - ✅
     - GPT-4o, GPT-5-nano with DALL-E
   * - ``claude``
     - ❌
     - ✅
     - ✅
     - Vision models (Sonnet, Opus)
   * - ``gemini``
     - ❌
     - ✅
     - ✅
     - Multimodal models (Flash, Pro)
   * - ``grok``
     - ❌
     - ✅
     - ❌
     - Vision support in Grok-4
   * - ``claude_code``
     - ❌
     - ❌
     - ❌
     - File operations via MCP

See :doc:`backends` for complete backend capabilities.

Configuration Examples
----------------------

Complete configuration files are available in the MassGen repository:

**Image Generation:**

* ``@examples/basic/single/single_gpt4o_image_generation.yaml``
* ``@examples/basic/multi/gpt4o_image_generation.yaml``

**Image Understanding:**

* ``@examples/basic/single/single_gpt5nano_image_understanding.yaml``
* ``@examples/basic/multi/gpt5nano_image_understanding.yaml``

**File Search:**

* ``@examples/basic/single/single_gpt5nano_file_search.yaml``

Browse all examples in the `Configuration README <https://github.com/Leezekun/MassGen/blob/main/@examples/README.md>`_.

Best Practices
--------------

1. **Image Generation**

   * Use descriptive, detailed prompts
   * Leverage multiple agents for prompt refinement
   * Specify style, mood, and composition clearly
   * Review generated images in agent workspaces

2. **Image Understanding**

   * Upload high-quality images for better analysis
   * Ask specific questions about image content
   * Use multi-agent collaboration for diverse perspectives
   * Combine with web search for contextual information

3. **File Upload and Search**

   * Organize files logically before upload
   * Use vector store search for large document collections
   * Clean up uploaded files after processing
   * Monitor API costs for file storage

4. **Workspace Management**

   * Configure ``cwd`` for organized file storage
   * Use ``snapshot_storage`` for agent collaboration
   * Review generated/analyzed content in workspaces
   * Include ``.massgen/`` in ``.gitignore``

Troubleshooting
---------------

**Image generation not working:**

Ensure ``enable_image_generation: true`` in backend configuration:

.. code-block:: yaml

   backend:
     type: "openai"
     model: "gpt-4o"
     enable_image_generation: true  # Required for DALL-E

**Image upload fails:**

Verify image path is correct and accessible:

.. code-block:: yaml

   upload_files:
     - image_path: "absolute/path/to/image.jpg"  # Use absolute paths

**File not found in workspace:**

Check agent's ``cwd`` configuration:

.. code-block:: yaml

   backend:
     cwd: "workspace1"  # Files stored in .massgen/workspaces/workspace1/

**Vector store errors:**

Enable file search explicitly:

.. code-block:: yaml

   backend:
     type: "openai"
     model: "gpt-5-nano"
     enable_file_search: true

Use Cases
---------

**Creative Design:**

* Logo generation with multi-agent refinement
* Marketing asset creation
* Visual concept exploration
* Design iteration and feedback

**Document Analysis:**

* PDF document Q&A with file search
* Visual document understanding (scanned forms, receipts)
* Chart and diagram analysis
* Multi-document comparison

**Content Creation:**

* Image description for accessibility
* Visual storytelling with generated images
* Social media content generation
* Educational material creation

**Research and Analysis:**

* Scientific image analysis
* Medical imaging interpretation (with appropriate models)
* Visual data extraction
* Comparative visual analysis

Next Steps
----------

* :doc:`backends` - Backend-specific multimodal capabilities
* :doc:`file_operations` - Workspace and file management
* :doc:`mcp_integration` - MCP tools for multimodal workflows
* :doc:`../examples/advanced_patterns` - Advanced multimodal patterns
* :doc:`../reference/yaml_schema` - Complete configuration reference
