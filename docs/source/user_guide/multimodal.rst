Multimodal Capabilities
=======================

MassGen supports comprehensive multimodal AI workflows, enabling agents to work with images, audio, and video content. This includes understanding (analyzing existing content) and file-based interactions.

.. note::

   **Multimodal Timeline:**

   * **v0.0.27**: Image understanding
   * **v0.0.30**: Audio and video understanding

.. note::
   **Multimodal Understanding with Custom Tools (v0.1.3+):**

   MassGen now provides custom tools for understanding multimodal content:

   * ✅ **understand_audio**: Transcribe audio files to text
   * ✅ **understand_file**: Analyze documents (PDF, DOCX, XLSX, PPTX) and text files
   * ✅ **understand_image**: Describe and analyze images
   * ✅ **understand_video**: Extract and analyze key frames from videos

   **File Access:**

   * Files must be accessible via ``context_paths`` configuration
   * Supports both pre-existing files and agent-generated content
   * Provides secure, sandboxed file access to agents

   **Limitations:**

   * Files must be explicitly configured in ``context_paths``
   * Agent-generated files in workspace are not automatically accessible for analysis
   * To analyze generated content, add the file path to ``context_paths`` or use multi-agent workflows

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

* **Upload and Search**: Work with documents and files (RAG)
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

Custom Multimodal Understanding Tools
--------------------------------------

MassGen v0.1.3+ provides custom tools for understanding multimodal content. These tools use OpenAI's APIs to analyze images, audio, video, and various file formats.

Overview
~~~~~~~~

The custom multimodal understanding tools enable agents to:

* **understand_audio**: Transcribe audio files using OpenAI's Transcription API
* **understand_file**: Analyze text files and documents (PDF, DOCX, XLSX, PPTX)
* **understand_image**: Describe and analyze images using vision models
* **understand_video**: Extract key frames from videos for content analysis

**Key Features:**

* Direct integration with OpenAI's gpt-4.1 and transcription APIs
* File-based workflows with ``context_paths`` for secure access
* Support for multiple file formats without MCP server overhead
* Easy configuration through YAML custom_tools

Configuration
~~~~~~~~~~~~~

Custom multimodal tools are configured through the ``custom_tools`` section in your agent configuration:

.. code-block:: yaml

   agents:
     - id: "multimodal_agent"
       backend:
         type: "openai"
         model: "gpt-5-nano"
         cwd: "workspace1"
         custom_tools:
           - name: ["understand_image"]
             category: "multimodal"
             path: "massgen/tool/_multimodal_tools/understand_image.py"
             function: ["understand_image"]

   orchestrator:
     context_paths:
       - path: "path/to/your/image.jpg"
         permission: "read"

understand_audio Tool
~~~~~~~~~~~~~~~~~~~~~

Transcribe audio files to text using OpenAI's Transcription API:

.. code-block:: yaml

   agents:
     - id: "audio_transcriber"
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
       - path: "massgen/configs/resources/v0.1.3-example/Sherlock_Holmes.mp3"
         permission: "read"

**Example Command:**

.. code-block:: bash

   massgen \
     --config massgen/configs/tools/custom_tools/multimodal_tools/understand_audio.yaml \
     "Please summarize the content in this audio."

**Supported Formats:**

* WAV, MP3, M4A, MP4, OGG, FLAC, AAC, WMA, OPUS

**Tool Parameters:**

* ``audio_paths``: List of audio file paths to transcribe
* ``model``: Model to use (default: "gpt-4o-transcribe")
* ``allowed_paths``: Optional list of allowed directories

understand_file Tool
~~~~~~~~~~~~~~~~~~~~

Analyze and understand file contents including text files and documents:

.. code-block:: yaml

   agents:
     - id: "file_analyzer"
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
       - path: "massgen/configs/resources/v0.1.3-example/TUMIX.pdf"
         permission: "read"

**Example Command:**

.. code-block:: bash

   massgen \
     --config massgen/configs/tools/custom_tools/multimodal_tools/understand_file.yaml \
     "Please summarize the content in this file."

**Supported File Types:**

* **Text Files**: .py, .js, .java, .md, .txt, .log, .csv, .json, .yaml, etc.
* **PDF**: Requires PyPDF2 (``pip install PyPDF2``)
* **Word**: .docx - Requires python-docx (``pip install python-docx``)
* **Excel**: .xlsx - Requires openpyxl (``pip install openpyxl``)
* **PowerPoint**: .pptx - Requires python-pptx (``pip install python-pptx``)

**Tool Parameters:**

* ``file_path``: Path to the file to analyze
* ``prompt``: Question or instruction about the file
* ``model``: Model to use (default: "gpt-4.1")
* ``max_chars``: Maximum characters to read (default: 50000)
* ``allowed_paths``: Optional list of allowed directories

understand_image Tool
~~~~~~~~~~~~~~~~~~~~~

Describe and analyze images using OpenAI's vision capabilities:

.. code-block:: yaml

   agents:
     - id: "image_analyzer"
       backend:
         type: "openai"
         model: "gpt-5-nano"
         cwd: "workspace1"
         custom_tools:
           - name: ["understand_image"]
             category: "multimodal"
             path: "massgen/tool/_multimodal_tools/understand_image.py"
             function: ["understand_image"]

   orchestrator:
     context_paths:
       - path: "massgen/configs/resources/v0.1.3-example/multimodality.jpg"
         permission: "read"

**Example Command:**

.. code-block:: bash

   massgen \
     --config massgen/configs/tools/custom_tools/multimodal_tools/understand_image.yaml \
     "Please summarize the content in this image."

**Supported Formats:**

* PNG, JPEG, JPG

**Tool Parameters:**

* ``image_path``: Path to the image file
* ``prompt``: Question or instruction about the image
* ``model``: Model to use (default: "gpt-4.1")
* ``allowed_paths``: Optional list of allowed directories

understand_video Tool
~~~~~~~~~~~~~~~~~~~~~

Extract key frames from videos and analyze content:

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
       - path: "massgen/configs/resources/v0.1.3-example/oppenheimer_trailer_1920.mp4"
         permission: "read"

**Example Command:**

.. code-block:: bash

   massgen \
     --config massgen/configs/tools/custom_tools/multimodal_tools/understand_video.yaml \
     "What's happening in this video?"

**Supported Formats:**

* MP4, AVI, MOV, MKV, FLV, WMV, WEBM, M4V, MPG, MPEG

**Tool Parameters:**

* ``video_path``: Path to the video file
* ``prompt``: Question or instruction about the video
* ``num_frames``: Number of key frames to extract (default: 8)
* ``model``: Model to use (default: "gpt-4.1")
* ``allowed_paths``: Optional list of allowed directories

**Requirements:**

* Requires opencv-python (``pip install opencv-python``)

Prerequisites
~~~~~~~~~~~~~

**Required Dependencies:**

Different tools require specific Python packages:

.. code-block:: bash

   # For understand_file (PDF support)
   pip install PyPDF2

   # For understand_file (Word documents)
   pip install python-docx

   # For understand_file (Excel spreadsheets)
   pip install openpyxl

   # For understand_file (PowerPoint presentations)
   pip install python-pptx

   # For understand_video
   pip install opencv-python

**API Requirements:**

* OpenAI API key must be set in ``.env`` file or environment variable
* Set ``OPENAI_API_KEY=your_api_key_here``

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
     - ✅ Understanding
     - ✅ Understanding
     - ✅ Understanding
     - ✅ Understanding
     - Vision models
   * - ``claude``
     - ✅ Understanding
     - ✅ Understanding
     - ✅ Understanding
     - ✅ Understanding
     - Vision models
   * - ``claude_code``
     - ✅ Understanding
     - ✅ Understanding
     - ✅ Understanding
     - ⭐ Native
     - Native file tools
   * - ``gemini``
     - ✅ Understanding
     - ✅ Understanding
     - ✅ Understanding
     - ✅ Understanding
     - Multimodal Pro/Flash
   * - ``grok``
     - ✅ Understanding
     - ✅ Understanding
     - ✅ Understanding
     - ✅ Understanding
     - Multimodal support
   * - ``azure_openai``
     - ✅ Understanding
     - ✅ Understanding
     - ✅ Understanding
     - ✅ Understanding
     - Vision models
   * - ``chatcompletion``
     - ✅ Understanding
     - ✅ Understanding
     - ✅ Understanding
     - ✅ Understanding
     - Provider-dependent

**Legend:**

* ✅ **Understanding** - Can analyze/process existing content
* ✅ **Available** - Feature supported
* ❌ **Not available** - Feature not supported
* ⭐ **Native** - Built into the backend

**Capability Details:**

* **Understanding**: Can analyze existing content (images, audio, video, files)
* **Native**: Built into the backend (e.g., ``claude_code`` filesystem tools)

**Provider-Specific Notes:**

* **OpenAI**: Strong vision capabilities, comprehensive multimodal understanding including files
* **Claude**: Strong vision capabilities, comprehensive multimodal understanding including files
* **Claude Code**: Native file tools with multimodal understanding capabilities
* **Gemini**: Multimodal understanding with Flash/Pro models including files
* **Grok**: Comprehensive multimodal understanding including files
* **Azure OpenAI**: Multimodal understanding via vision models including files
* **ChatCompletion**: Multimodal support varies by provider (Qwen, etc.) including files

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

1. **Custom Multimodal Understanding Tools**

   * Use ``context_paths`` to provide secure file access to agents
   * Install required dependencies (PyPDF2, opencv-python, etc.) before use
   * Set appropriate ``max_chars`` limits for large documents to control API costs
   * Adjust ``num_frames`` for videos based on content length and detail needed
   * Configure ``cwd`` to organize tool outputs in agent workspaces
   * Use specific prompts to get targeted insights from multimodal content
   * Monitor OpenAI API usage when processing large files or many files

2. **Image Understanding**

   * Upload high-quality images for better analysis
   * Ask specific questions about image content
   * Use multi-agent collaboration for diverse perspectives
   * Combine with web search for contextual information
   * Specify aspect ratio and resolution when needed

3. **Audio Understanding**

   * Use clear, high-quality audio recordings
   * Supported formats: MP3, WAV, M4A, WEBM
   * Combine transcription with analysis tasks
   * Ask specific questions about audio content
   * Monitor file size limits (default 64MB)

4. **Video Understanding**

   * Upload clear, well-lit videos
   * Supported formats: MP4, AVI, MOV, WEBM
   * Ask about specific scenes, actions, or content
   * Use appropriate backends (Claude, Qwen for video)
   * Monitor file size limits

5. **File Upload and Search**

   * Organize files logically before upload
   * Use vector store search for large document collections
   * Clean up uploaded files after processing
   * Monitor API costs for file storage and search
   * Test file paths before deployment

6. **Workspace Management**

   * Configure ``cwd`` for organized file storage
   * Use ``snapshot_storage`` for agent collaboration
   * Review analyzed content in workspaces
   * Include ``.massgen/`` in ``.gitignore``
   * Clean up old workspaces periodically

Troubleshooting
---------------

**Image Issues:**

* **Image upload fails:** Verify image path is correct and accessible. Use absolute paths or paths relative to execution directory.

**Audio Issues:**

* **Audio file too large:** Check file size limits (default 64MB). Configure with ``media_max_file_size_mb``

  .. code-block:: yaml

     backend:
       type: "openai"
       media_max_file_size_mb: 100  # Increase limit if needed

* **Unsupported audio format:** Use MP3, WAV, M4A, or WEBM formats

**Video Issues:**

* **Video understanding not working:** Ensure you have opencv-python installed and the video file is in ``context_paths``

  .. code-block:: bash

     pip install opencv-python

  .. code-block:: yaml

     orchestrator:
       context_paths:
         - path: "path/to/video.mp4"
           permission: "read"

* **Video file too large:** Adjust the number of frames extracted using ``num_frames`` parameter (default: 8).

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

**API Cost Issues:**

* Monitor multimodal API usage carefully - image/audio/video understanding can be expensive
* Clean up uploaded files and vector stores after use
* Use appropriate file sizes to control costs

Use Cases
---------

**Custom Multimodal Understanding Tools:**

* **Document Processing**: Analyze PDFs, Word docs, Excel sheets, PowerPoint presentations
* **Audio Transcription**: Convert meeting recordings, interviews, podcasts to text
* **Image Analysis**: Extract information from screenshots, charts, diagrams, photos
* **Video Summarization**: Analyze video content through key frame extraction
* **Code Analysis**: Understand code files with AI-powered explanations
* **Data Extraction**: Pull insights from various file formats automatically
* **Content Moderation**: Analyze images, videos, and audio for compliance
* **Research Assistant**: Summarize academic papers, reports, and documents

**Image Use Cases:**

* **Document Analysis**: PDF Q&A, scanned form understanding, chart analysis
* **Content Creation**: Image descriptions for accessibility, social media content
* **Research**: Scientific image analysis, medical imaging, visual data extraction

**Audio Use Cases:**

* **Transcription**: Meeting notes, interview transcription, voice memo processing
* **Accessibility**: Audio descriptions and transcription
* **Language Learning**: Analyze pronunciation, conversation practice
* **Customer Service**: Analyze customer support audio

**Video Use Cases:**

* **Analysis**: Video content summarization, scene detection, quality assessment
* **Security**: Surveillance analysis, incident review, activity recognition
* **Education**: Analyze educational videos, extract key information

**Multi-Modal Workflows:**

* **Document Processing**: Scan document → OCR with vision → Generate text summary
* **Accessibility**: Take image → Generate description → Extract text content
* **Content Analysis**: Upload video → Extract key frames → Analyze scenes

**Enterprise Applications:**

* **Documentation**: Analyze technical docs and extract information
* **Training**: Process training materials in multiple formats
* **Customer Support**: Multi-modal knowledge base with images, videos, and audio analysis

Next Steps
----------

* :doc:`backends` - Backend-specific multimodal capabilities
* :doc:`file_operations` - Workspace and file management
* :doc:`tools` - Custom tools configuration and usage
* :doc:`../examples/advanced_patterns` - Advanced multimodal patterns
* :doc:`../reference/yaml_schema` - Complete configuration reference
