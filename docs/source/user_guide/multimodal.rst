Multimodal Capabilities
=======================

MassGen supports comprehensive multimodal AI workflows, enabling agents to work with images, audio, and video content. This includes understanding (analyzing existing content) and file-based interactions.

.. note::
   **Multimodal Understanding with Custom Tools (v0.1.3+):**

   MassGen now provides custom tools for understanding multimodal content:

   * ✅ **understand_audio**: Transcribe audio files to text
   * ✅ **understand_file**: Analyze documents (PDF, DOCX, XLSX, PPTX) and text files
   * ✅ **understand_image**: Describe and analyze images
   * ✅ **understand_video**: Extract and analyze key frames from videos

   **File Access:**

   * Files must be accessible via ``context_paths`` configuration or created within agent workspaces
   * Supports both pre-existing files and agent-generated content
   * Provides secure, sandboxed file access to agents

Overview
--------

Multimodal capabilities extend MassGen's multi-agent collaboration across different content types:

**Image Capabilities:**

* **Understanding**: Analyze and describe image content (Vision models)

**Audio Capabilities:**

* **Understanding**: Transcription, audio analysis

**Video Capabilities:**

* **Understanding**: Analyze video content

**File Operations:**

* **Upload and Search**: Work with documents and files
* **Custom Tools**: Understand and analyze multimodal files (images, audio, video, documents)

Image Understanding
-------------------

Image understanding enables agents to analyze visual content, extract information, and answer questions about images using the ``understand_image`` custom tool.

Basic Configuration
~~~~~~~~~~~~~~~~~~~

Configure agents with the ``understand_image`` tool:

.. code-block:: yaml

   agents:
     - id: "vision_agent"
       backend:
         type: "openai"
         model: "gpt-5-nano"
         cwd: "workspace1"
         custom_tools:
           - name: ["understand_image"]
             category: "multimodal"
             path: "massgen/tool/_multimodal_tools/understand_image.py"
             function: ["understand_image"]
       system_message: "You are a helpful assistant"

   orchestrator:
     context_paths:
       - path: "@examples/resources/v0.0.27-example/multimodality.jpg"
         permission: "read"

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
         cwd: "workspace1"
         custom_tools:
           - name: ["understand_image"]
             category: "multimodal"
             path: "massgen/tool/_multimodal_tools/understand_image.py"
             function: ["understand_image"]
       system_message: "You are a helpful assistant"

     - id: "response_agent2"
       backend:
         type: "openai"
         model: "gpt-5-nano"
         cwd: "workspace2"
         custom_tools:
           - name: ["understand_image"]
             category: "multimodal"
             path: "massgen/tool/_multimodal_tools/understand_image.py"
             function: ["understand_image"]
       system_message: "You are a helpful assistant"

   orchestrator:
     context_paths:
       - path: "@examples/resources/v0.0.27-example/multimodality.jpg"
         permission: "read"

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

Audio Understanding
-------------------

Transcribe and analyze audio files using the ``understand_audio`` custom tool:

.. code-block:: yaml

   agents:
     - id: "transcriber"
       backend:
         type: "openai"
         model: "gpt-5-nano"
         cwd: "workspace1"
         custom_tools:
           - name: ["understand_audio"]
             category: "multimodal"
             path: "massgen/tool/_multimodal_tools/understand_audio.py"
             function: ["understand_audio"]

   orchestrator:
     context_paths:
       - path: "path/to/audio.mp3"
         permission: "read"

**Supported Formats:**

* WAV, MP3, M4A, MP4, OGG, FLAC, AAC, WMA, OPUS

**Example Use Cases:**

* Meeting transcription
* Podcast analysis
* Voice memo processing
* Interview transcription
* Audio content summarization

Video Understanding
-------------------

Analyze and extract information from video files using the ``understand_video`` custom tool:

.. code-block:: yaml

   agents:
     - id: "video_analyzer"
       backend:
         type: "openai"
         model: "gpt-5-nano"
         cwd: "workspace1"
         custom_tools:
           - name: ["understand_video"]
             category: "multimodal"
             path: "massgen/tool/_multimodal_tools/understand_video.py"
             function: ["understand_video"]

   orchestrator:
     context_paths:
       - path: "path/to/video.mp4"
         permission: "read"

**Supported Formats:**

* MP4, AVI, MOV, MKV, FLV, WMV, WEBM, M4V, MPG, MPEG

**Example Use Cases:**

* Video content analysis
* Scene detection and description
* Action recognition
* Video summarization
* Quality assessment

**Requirements:**

* Requires opencv-python (``pip install opencv-python``)

File Understanding
------------------

File understanding capabilities enable agents to analyze documents and perform Q&A using the ``understand_file`` custom tool.

Basic Configuration
~~~~~~~~~~~~~~~~~~~

Configure agents to analyze files:

.. code-block:: yaml

   agents:
     - id: "document_agent"
       backend:
         type: "openai"
         model: "gpt-5-nano"
         cwd: "workspace1"
         custom_tools:
           - name: ["understand_file"]
             category: "multimodal"
             path: "massgen/tool/_multimodal_tools/understand_file.py"
             function: ["understand_file"]

   orchestrator:
     context_paths:
       - path: "path/to/document.pdf"
         permission: "read"
       - path: "path/to/report.docx"
         permission: "read"

**Supported File Types:**

* **Text Files**: .py, .js, .java, .md, .txt, .log, .csv, .json, .yaml, etc.
* **PDF**: Requires PyPDF2 (``pip install PyPDF2``)
* **Word**: .docx - Requires python-docx (``pip install python-docx``)
* **Excel**: .xlsx - Requires openpyxl (``pip install openpyxl``)
* **PowerPoint**: .pptx - Requires python-pptx (``pip install python-pptx``)

**Example Use Case:**

.. code-block:: bash

   # Document Q&A
   massgen \
     --config @examples/basic/single/single_gpt5nano_file_search.yaml \
     "What are the main conclusions from the research paper?"

Supported Backends
------------------

Multimodal capabilities vary by backend. This table shows which backends support which multimodal features:

.. list-table:: Backend Multimodal Capabilities
   :header-rows: 1
   :widths: 15 12 12 12 12 12

   * - Backend
     - Image
     - Audio
     - Video
     - File
     - Notes
   * - ``openai``
     - ✅
     - ✅
     - ✅
     - ✅
     - Vision models
   * - ``claude``
     - ✅
     - ✅
     - ✅
     - ✅
     - Vision models
   * - ``claude_code``
     - ✅
     - ✅
     - ✅
     - ⭐
     - Native file tools
   * - ``gemini``
     - ✅
     - ✅
     - ✅
     - ✅
     - Multimodal Pro/Flash
   * - ``grok``
     - ✅
     - ✅
     - ✅
     - ✅
     - Multimodal support
   * - ``azure_openai``
     - ✅
     - ✅
     - ✅
     - ✅
     - Vision models
   * - ``chatcompletion``
     - ✅
     - ✅
     - ✅
     - ✅
     - Provider-dependent

**Legend:**

* ✅ - Feature supported via custom tools
* ⭐ - Native backend support
* ❌ - Not available


See :doc:`backends` for complete backend capabilities including web search, code execution, and MCP support.

Configuration Examples
----------------------

Complete configuration files are available in the MassGen repository:

**Custom Multimodal Understanding Tools (v0.1.3+):**

* ``massgen/configs/tools/custom_tools/multimodal_tools/understand_audio.yaml`` - Audio transcription tool
* ``massgen/configs/tools/custom_tools/multimodal_tools/understand_file.yaml`` - File understanding tool (PDF, DOCX, etc.)
* ``massgen/configs/tools/custom_tools/multimodal_tools/understand_image.yaml`` - Image understanding tool
* ``massgen/configs/tools/custom_tools/multimodal_tools/understand_video.yaml`` - Video understanding tool

**Image:**

* ``@examples/basic/single/single_gpt5nano_image_understanding.yaml`` - Image understanding
* ``@examples/basic/multi/gpt5nano_image_understanding.yaml`` - Multi-agent image analysis

**Audio:**

* ``@examples/basic/single/single_openrouter_audio_understanding.yaml`` - Audio transcription

**Video:**

* ``@examples/basic/single/single_qwen_video_understanding.yaml`` - Video analysis with Qwen

**File Operations:**

* ``@examples/basic/single/single_gpt5nano_file_search.yaml`` - Document Q&A with file search

Browse all examples in the `Configuration README <https://github.com/Leezekun/MassGen/blob/main/@examples/README.md>`_.

Best Practices
--------------

1. **File Access and Configuration**

   * Use ``context_paths`` to provide secure file access to agents
   * Ensure files are accessible before running - use absolute paths or paths relative to execution directory
   * Install required dependencies before use (already included in MassGen environment):

     * Audio: No additional dependencies (uses OpenAI API)
     * Video: ``pip install opencv-python``
     * Files (PDF): ``pip install PyPDF2``
     * Files (Word): ``pip install python-docx``
     * Files (Excel): ``pip install openpyxl``
     * Files (PowerPoint): ``pip install python-pptx``

2. **Performance and Cost Optimization**

   * Set appropriate ``max_chars`` limits for large documents to control API costs
   * Adjust ``num_frames`` for videos (default: 8) based on content length and detail needed
   * Monitor OpenAI API usage when processing large files or many files
   * Use specific prompts to get targeted insights from multimodal content

3. **Quality and Accuracy**

   * Use high-quality source files (clear images, high-quality audio, well-lit videos)
   * Ask specific, detailed questions to get better responses
   * Use multi-agent collaboration for diverse perspectives on complex content
   * Combine with web search tools for contextual information

4. **Workspace Management**

   * Configure ``cwd`` for organized file storage
   * Use ``snapshot_storage`` for agent collaboration
   * Review analyzed content in agent workspaces
   * Include ``.massgen/`` in ``.gitignore``
   * Clean up old workspaces periodically

Troubleshooting
---------------

**Image Issues:**

* **Image file not found:** Ensure image path is added to ``context_paths`` and the file exists

  .. code-block:: yaml

     orchestrator:
       context_paths:
         - path: "path/to/image.jpg"
           permission: "read"

**Audio Issues:**

* **Audio file not found:** Ensure audio path is in ``context_paths`` and file exists
* **Unsupported audio format:** Use supported formats: WAV, MP3, M4A, MP4, OGG, FLAC, AAC, WMA, OPUS
* **API transcription error:** Verify OpenAI API key is set in ``.env`` file

**Video Issues:**

* **opencv-python not installed:** Install with ``pip install opencv-python``
* **Video file not found:** Ensure video path is in ``context_paths`` and file exists

  .. code-block:: yaml

     orchestrator:
       context_paths:
         - path: "path/to/video.mp4"
           permission: "read"

* **Unsupported video format:** Use supported formats: MP4, AVI, MOV, MKV, FLV, WMV, WEBM, M4V, MPG, MPEG
* **High API costs:** Reduce ``num_frames`` parameter (default: 8) to extract fewer frames

**General File Issues:**

* **File not found:** Ensure the file path is added to ``context_paths`` in the orchestrator configuration

  .. code-block:: yaml

     orchestrator:
       context_paths:
         - path: "path/to/your/file"
           permission: "read"

* **Permission errors:** Verify that files are readable and paths are accessible

* **Missing dependencies:** Install required Python packages for specific file types

  .. code-block:: bash

     pip install PyPDF2 python-docx openpyxl python-pptx opencv-python

**API and Dependency Issues:**

* **Missing OpenAI API key:** Set ``OPENAI_API_KEY`` in ``.env`` file or environment variable
* **Import errors:** Install required dependencies for your file types (see Best Practices section)
* **API costs:** Monitor usage carefully - multimodal understanding can be expensive with large files or many frames

Use Cases
---------

**Document Processing:**

* Analyze PDFs, Word docs, Excel sheets, PowerPoint presentations
* Extract data from forms, tables, and structured documents
* Summarize research papers, technical documentation, and reports

**Media Analysis:**

* Transcribe meeting recordings, interviews, and podcasts
* Analyze video content through key frame extraction
* Extract information from screenshots, charts, and diagrams

**Content Understanding:**

* Code analysis with AI-powered explanations
* Visual content description for accessibility
* Scene detection and description in videos

**Enterprise Workflows:**

* Multi-format knowledge base (text, images, audio, video)
* Training material processing and summarization
* Customer support content analysis and moderation

Next Steps
----------

* :doc:`backends` - Backend-specific multimodal capabilities
* :doc:`file_operations` - Workspace and file management
* :doc:`tools` - Custom tools configuration and usage
* :doc:`../examples/advanced_patterns` - Advanced multimodal patterns
* :doc:`../reference/yaml_schema` - Complete configuration reference
