Multimodal Capabilities
=======================

MassGen supports comprehensive multimodal AI workflows, enabling agents to both understand and generate images, audio, video, and file content. This includes analyzing existing content and creating new multimodal outputs.

.. note::
   **Multimodal Tools (v0.1.3+):**

   MassGen provides custom tools for both understanding and generating multimodal content:

   **Understanding Tools:**

   * ✅ **understand_audio**: Transcribe audio files to text
   * ✅ **understand_file**: Analyze documents (PDF, DOCX, XLSX, PPTX) and text files
   * ✅ **understand_image**: Describe and analyze images
   * ✅ **understand_video**: Extract and analyze key frames from videos

   **Generation Tools:**

   * ✅ **text_to_image_generation**: Generate images from text prompts (GPT-4.1)
   * ✅ **image_to_image_generation**: Create image variations from existing images
   * ✅ **text_to_video_generation**: Generate videos from text descriptions (Sora-2)
   * ✅ **text_to_speech_continue_generation**: Generate expressive speech with emotional tone
   * ✅ **text_to_speech_transcription_generation**: Convert text to speech (TTS)
   * ✅ **text_to_file_generation**: Generate formatted documents (TXT, MD, PDF)

   **File Access:**

   * Files must be accessible via ``context_paths`` configuration or created within agent workspaces
   * Supports both pre-existing files and agent-generated content
   * Provides secure, sandboxed file access to agents

Overview
--------

Multimodal capabilities extend MassGen's multi-agent collaboration across different content types:

**Image Capabilities:**

* **Understanding**: Analyze and describe image content (Vision models)
* **Generation**: Create images from text prompts, generate variations from existing images

**Audio Capabilities:**

* **Understanding**: Transcription, audio analysis
* **Generation**: Text-to-speech with emotional expression, direct TTS conversion

**Video Capabilities:**

* **Understanding**: Analyze video content through key frame extraction
* **Generation**: Create videos from text descriptions

**File Operations:**

* **Understanding**: Analyze documents and files (PDF, DOCX, XLSX, PPTX, text files)
* **Generation**: Generate formatted documents from text prompts
* **Custom Tools**: Comprehensive multimodal file handling

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

Image Generation
----------------

Generate images from text descriptions using AI models. MassGen provides two generation approaches:

Text-to-Image Generation
~~~~~~~~~~~~~~~~~~~~~~~~~

Create new images from text prompts using GPT-4.1:

.. code-block:: yaml

   agents:
     - id: "image_generator"
       backend:
         type: "openai"
         model: "gpt-4o"
         cwd: "workspace1"
         enable_image_generation: true
         custom_tools:
           - name: ["text_to_image_generation"]
             category: "multimodal"
             path: "massgen/tool/_multimodal_tools/text_to_image_generation.py"
             function: ["text_to_image_generation"]
       system_message: "You are an AI assistant with access to text-to-image generation capabilities."

**Example Command:**

.. code-block:: bash

   massgen \
     --config massgen/configs/tools/custom_tools/multimodal_tools/text_to_image_generation_single.yaml \
     "Please generate an image of a cat in space."

**Key Features:**

* Powered by OpenAI's GPT-4.1 model
* Generates high-quality images from text descriptions
* Automatically saves images to agent workspace

Image-to-Image Generation
~~~~~~~~~~~~~~~~~~~~~~~~~~

Create variations or modifications of existing images:

.. code-block:: yaml

   agents:
     - id: "image_editor"
       backend:
         type: "openai"
         model: "gpt-4o"
         cwd: "workspace1"
         enable_image_generation: true
         custom_tools:
           - name: ["image_to_image_generation"]
             category: "multimodal"
             path: "massgen/tool/_multimodal_tools/image_to_image_generation.py"
             function: ["image_to_image_generation"]
           - name: ["understand_image"]
             category: "multimodal"
             path: "massgen/tool/_multimodal_tools/understand_image.py"
             function: ["understand_image"]

   orchestrator:
     context_paths:
       - path: "path/to/source_image.jpg"
         permission: "read"

**Use Cases:**

* Create artistic variations of existing images
* Style transfer and image transformation
* Generate similar images with different characteristics
* Image editing and enhancement workflows

Multi-Agent Image Generation
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Combine understanding and generation capabilities with multiple agents:

.. code-block:: yaml

  agents:
    - id: "text_to_image_generation_tool1"
      backend:
        type: "openai"
        model: "gpt-4o"
        cwd: "workspace1"
        enable_image_generation: true
        custom_tools:
          - name: ["text_to_image_generation"]
            category: "multimodal"
            path: "massgen/tool/_multimodal_tools/text_to_image_generation.py"
            function: ["text_to_image_generation"]
          - name: ["understand_image"]
            category: "multimodal"
            path: "massgen/tool/_multimodal_tools/understand_image.py"
            function: ["understand_image"]
          - name: ["image_to_image_generation"]
            category: "multimodal"
            path: "massgen/tool/_multimodal_tools/image_to_image_generation.py"
            function: ["image_to_image_generation"]
      system_message: |
        You are an AI assistant with access to text-to-image generation capabilities.

    - id: "text_to_image_generation_tool2"
      backend:
        type: "openai"
        model: "gpt-4o"
        cwd: "workspace2"
        enable_image_generation: true
        custom_tools:
          - name: ["text_to_image_generation"]
            category: "multimodal"
            path: "massgen/tool/_multimodal_tools/text_to_image_generation.py"
            function: ["text_to_image_generation"]
          - name: ["understand_image"]
            category: "multimodal"
            path: "massgen/tool/_multimodal_tools/understand_image.py"
            function: ["understand_image"]
      system_message: |
        You are an AI assistant with access to text-to-image generation capabilities.

    orchestrator:
      snapshot_storage: "snapshots"
      agent_temporary_workspace: "temp_workspaces"

**Example Command:**

.. code-block:: bash

   massgen \
     --config massgen/configs/tools/custom_tools/multimodal_tools/text_to_image_generation_multi.yaml \
     "Please generate an image of a cat in space."

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

Audio/Speech Generation
-----------------------

Generate speech and audio content from text using OpenAI's audio generation capabilities. MassGen provides two text-to-speech approaches:

Expressive Speech Generation
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Generate natural-sounding speech with emotional expression using GPT-4o Audio:

.. code-block:: yaml

   agents:
     - id: "speech_generator"
       backend:
         type: "openai"
         model: "gpt-4o"
         cwd: "workspace1"
         enable_audio_generation: true
         custom_tools:
           - name: ["text_to_speech_continue_generation"]
             category: "multimodal"
             path: "massgen/tool/_multimodal_tools/text_to_speech_continue_generation.py"
             function: ["text_to_speech_continue_generation"]
       system_message: "You are an AI assistant with access to text-to-speech generation capabilities."

**Example Command:**

.. code-block:: bash

   massgen \
     --config massgen/configs/tools/custom_tools/multimodal_tools/text_to_speech_generation_single.yaml \
     "I want you to tell me a very short introduction about Sherlock Holmes in one sentence, and I want you to use emotion voice to read it out loud."

**Key Features:**

* Powered by GPT-4o Audio Preview model
* Supports emotional and expressive speech
* Multiple voice options (alloy, echo, fable, onyx, nova, shimmer)
* Output formats: WAV, MP3
* Natural conversation flow with context awareness

Direct Text-to-Speech (TTS)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Convert text directly to speech using OpenAI's TTS API:

.. code-block:: yaml

   agents:
     - id: "tts_agent"
       backend:
         type: "openai"
         model: "gpt-4o"
         cwd: "workspace1"
         enable_audio_generation: true
         custom_tools:
           - name: ["text_to_speech_transcription_generation"]
             category: "multimodal"
             path: "massgen/tool/_multimodal_tools/text_to_speech_transcription_generation.py"
             function: ["text_to_speech_transcription_generation"]

**Key Features:**

* Uses GPT-4o-mini-TTS for fast, cost-effective generation
* Direct text-to-speech conversion
* Supports multiple voices and output formats
* Optional instructions for voice style customization
* Streaming response for efficient processing

**Supported Voices:**

* ``alloy`` - Neutral, balanced voice
* ``echo`` - Clear, professional voice
* ``fable`` - Warm, storytelling voice
* ``onyx`` - Deep, authoritative voice
* ``nova`` - Energetic, friendly voice
* ``shimmer`` - Soft, gentle voice

**Supported Formats:**

* MP3 (default)
* WAV
* OPUS
* AAC
* FLAC

Multi-Agent Audio/Speech Generation
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Combine understanding and generation capabilities with multiple agents:

.. code-block:: yaml

  agents:
    - id: "text_to_speech_continue_generation_tool1"
      backend:
        type: "openai"
        model: "gpt-4o"
        cwd: "workspace1"
        enable_audio_generation: true
        custom_tools:
          - name: ["text_to_speech_transcription_generation"]
            category: "multimodal"
            path: "massgen/tool/_multimodal_tools/text_to_speech_transcription_generation.py"
            function: ["text_to_speech_transcription_generation"]
          - name: ["understand_audio"]
            category: "multimodal"
            path: "massgen/tool/_multimodal_tools/understand_audio.py"
            function: ["understand_audio"]
          - name: ["text_to_speech_continue_generation"]
            category: "multimodal"
            path: "massgen/tool/_multimodal_tools/text_to_speech_continue_generation.py"
            function: ["text_to_speech_continue_generation"]
      system_message: |
        You are an AI assistant with access to text-to-speech generation capabilities.

    - id: "text_to_speech_continue_generation_tool2"
      backend:
        type: "openai"
        model: "gpt-4o"
        cwd: "workspace2"
        enable_audio_generation: true
        custom_tools:
          - name: ["text_to_speech_transcription_generation"]
            category: "multimodal"
            path: "massgen/tool/_multimodal_tools/text_to_speech_transcription_generation.py"
            function: ["text_to_speech_transcription_generation"]
          - name: ["understand_audio"]
            category: "multimodal"
            path: "massgen/tool/_multimodal_tools/understand_audio.py"
            function: ["understand_audio"]
          - name: ["text_to_speech_continue_generation"]
            category: "multimodal"
            path: "massgen/tool/_multimodal_tools/text_to_speech_continue_generation.py"
            function: ["text_to_speech_continue_generation"]
      system_message: |
        You are an AI assistant with access to text-to-speech generation capabilities.

  orchestrator:
    snapshot_storage: "snapshots"
    agent_temporary_workspace: "temp_workspaces"


**Example Command:**

.. code-block:: bash

   massgen \
     --config massgen/configs/tools/custom_tools/multimodal_tools/text_to_speech_generation_multi.yaml \
     "I want to you tell me a very short introduction about Sherlock Homes in one sentence, and I want you to use emotion voice to read it out loud."

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

Video Generation
----------------

Generate videos from text descriptions using OpenAI's Sora-2 API:

.. code-block:: yaml

   agents:
     - id: "video_generator"
       backend:
         type: "openai"
         model: "gpt-4o"
         cwd: "workspace1"
         enable_video_generation: true
         custom_tools:
           - name: ["text_to_video_generation"]
             category: "multimodal"
             path: "massgen/tool/_multimodal_tools/text_to_video_generation.py"
             function: ["text_to_video_generation"]
       system_message: "You are an AI assistant with access to text-to-video generation capabilities."

**Example Command:**

.. code-block:: bash

   massgen \
     --config massgen/configs/tools/custom_tools/multimodal_tools/text_to_video_generation_single.yaml \
     "Generate a 4 seconds video with neon-lit alley at night, light rain, slow push-in, cinematic."

**Key Features:**

* Powered by OpenAI's Sora-2 model
* Generate high-quality videos from text descriptions
* Customizable video duration (4-20 seconds)
* Automatic video download and storage
* Supports detailed scene descriptions and camera movements

**Use Cases:**

* Marketing and advertising content creation
* Concept visualization and storyboarding
* Educational and training videos
* Social media content generation
* Creative storytelling and animation
* Product demonstration videos

**Best Practices for Video Generation:**

* Provide detailed scene descriptions including:

  * Setting and environment
  * Lighting conditions
  * Camera movements (push-in, pull-out, pan, etc.)
  * Atmosphere and mood
  * Objects and characters

* Use cinematic terminology for better results
* Specify duration based on content complexity
* Combine with ``understand_video`` tool for quality verification

Multi-Agent Video Generation
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Combine video generation with analysis for iterative improvement:

.. code-block:: yaml

  agents:
    - id: "text_to_video_generation_tool1"
      backend:
        type: "openai"
        model: "gpt-4o"
        cwd: "workspace1"
        enable_video_generation: true
        custom_tools:
          - name: ["understand_video"]
            category: "multimodal"
            path: "massgen/tool/_multimodal_tools/understand_video.py"
            function: ["understand_video"]
          - name: ["text_to_video_generation"]
            category: "multimodal"
            path: "massgen/tool/_multimodal_tools/text_to_video_generation.py"
            function: ["text_to_video_generation"]
      system_message: |
        You are an AI assistant with access to text-to-video generation capabilities.

    - id: "text_to_video_generation_tool2"
      backend:
        type: "openai"
        model: "gpt-4o"
        cwd: "workspace2"
        enable_video_generation: true
        custom_tools:
          - name: ["understand_video"]
            category: "multimodal"
            path: "massgen/tool/_multimodal_tools/understand_video.py"
            function: ["understand_video"]
          - name: ["text_to_video_generation"]
            category: "multimodal"
            path: "massgen/tool/_multimodal_tools/text_to_video_generation.py"
            function: ["text_to_video_generation"]
      system_message: |
        You are an AI assistant with access to text-to-video generation capabilities.

  orchestrator:
    snapshot_storage: "snapshots"
    agent_temporary_workspace: "temp_workspaces"


**Example Command:**

.. code-block:: bash

   massgen \
     --config massgen/configs/tools/custom_tools/multimodal_tools/text_to_video_generation_multi.yaml \
     "Generate a 4 seconds video with neon-lit alley at night, light rain, slow push-in, cinematic."

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

File Generation
---------------

Generate formatted documents from text using AI. The ``text_to_file_generation`` tool can create professional documents in various formats:

.. code-block:: yaml

   agents:
     - id: "document_generator"
       backend:
         type: "openai"
         model: "gpt-4o"
         cwd: "workspace1"
         enable_file_generation: true
         custom_tools:
           - name: ["text_to_file_generation"]
             category: "multimodal"
             path: "massgen/tool/_multimodal_tools/text_to_file_generation.py"
             function: ["text_to_file_generation"]
       system_message: "You are an AI assistant with access to text-to-file generation capabilities."

**Example Command:**

.. code-block:: bash

   massgen \
     --config massgen/configs/tools/custom_tools/multimodal_tools/text_to_file_generation_single.yaml \
     "Please generate a comprehensive technical report about the latest developments in Large Language Models (LLMs) and Generative AI. The report should include: 1) Executive Summary, 2) Introduction to LLMs, 3) Recent breakthroughs, 4) Applications in industry, 5) Ethical considerations, 6) Future directions. Save it as a PDF file."

**Supported Output Formats:**

* **TXT** - Plain text files
* **MD** - Markdown formatted documents
* **PDF** - Professional PDF documents with formatting

Multi-Agent Document Workflow
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Combine generation with review and refinement:

.. code-block:: yaml

  agents:
    - id: "text_to_file_generation_tool1"
      backend:
        type: "openai"
        model: "gpt-4o"
        cwd: "workspace1"
        enable_file_generation: true
        custom_tools:
          - name: ["text_to_file_generation"]
            category: "multimodal"
            path: "massgen/tool/_multimodal_tools/text_to_file_generation.py"
            function: ["text_to_file_generation"]
          - name: ["understand_file"]
            category: "multimodal"
            path: "massgen/tool/_multimodal_tools/understand_file.py"
            function: ["understand_file"]
      system_message: |
        You are an AI assistant with access to text-to-file generation capabilities.

    - id: "text_to_file_generation_tool2"
      backend:
        type: "openai"
        model: "gpt-4o"
        cwd: "workspace2"
        enable_file_generation: true
        custom_tools:
          - name: ["text_to_file_generation"]
            category: "multimodal"
            path: "massgen/tool/_multimodal_tools/text_to_file_generation.py"
            function: ["text_to_file_generation"]
          - name: ["understand_file"]
            category: "multimodal"
            path: "massgen/tool/_multimodal_tools/understand_file.py"
            function: ["understand_file"]
      system_message: |
        You are an AI assistant with access to text-to-file generation capabilities.

  orchestrator:
    snapshot_storage: "snapshots"
    agent_temporary_workspace: "temp_workspaces"

**Example Command:**

.. code-block:: bash

   massgen \
     --config massgen/configs/tools/custom_tools/multimodal_tools/text_to_file_generation_multi.yaml \
     "Please generate a comprehensive technical report about the latest developments in Large Language Models (LLMs) and Generative AI. The report should include: 1) Executive Summary, 2) Introduction to LLMs, 3) Recent breakthroughs, 4) Applications in industry, 5) Ethical considerations, 6) Future directions. Save it as a PDF file."

**Requirements:**

* PDF generation requires ``reportlab`` (``pip install reportlab``)

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

**Custom Multimodal Generation Tools (Latest):**

* ``massgen/configs/tools/custom_tools/multimodal_tools/text_to_image_generation_single.yaml`` - Single-agent image generation
* ``massgen/configs/tools/custom_tools/multimodal_tools/text_to_image_generation_multi.yaml`` - Multi-agent image generation
* ``massgen/configs/tools/custom_tools/multimodal_tools/text_to_video_generation_single.yaml`` - Single-agent video generation
* ``massgen/configs/tools/custom_tools/multimodal_tools/text_to_video_generation_multi.yaml`` - Multi-agent video generation
* ``massgen/configs/tools/custom_tools/multimodal_tools/text_to_speech_generation_single.yaml`` - Single-agent speech generation
* ``massgen/configs/tools/custom_tools/multimodal_tools/text_to_speech_generation_multi.yaml`` - Multi-agent speech generation
* ``massgen/configs/tools/custom_tools/multimodal_tools/text_to_file_generation_single.yaml`` - Single-agent document generation
* ``massgen/configs/tools/custom_tools/multimodal_tools/text_to_file_generation_multi.yaml`` - Multi-agent document generation

**Image Understanding:**

* ``@examples/basic/single/single_gpt5nano_image_understanding.yaml`` - Image understanding
* ``@examples/basic/multi/gpt5nano_image_understanding.yaml`` - Multi-agent image analysis

**Audio Understanding:**

* ``@examples/basic/single/single_openrouter_audio_understanding.yaml`` - Audio transcription

**Video Understanding:**

* ``@examples/basic/single/single_qwen_video_understanding.yaml`` - Video analysis with Qwen

**File Operations:**

* ``@examples/basic/single/single_gpt5nano_file_search.yaml`` - Document Q&A with file search

Browse all examples in the `Configuration README <https://github.com/Leezekun/MassGen/blob/main/@examples/README.md>`_.

Best Practices
--------------

1. **File Access and Configuration**

   * Use ``context_paths`` to provide secure file access to agents for understanding tasks
   * Ensure files are accessible before running - use absolute paths or paths relative to execution directory
   * Install required dependencies before use:

     * Audio Understanding: No additional dependencies (uses OpenAI API)
     * Video Understanding: ``pip install opencv-python``
     * File Understanding (PDF): ``pip install PyPDF2``
     * File Understanding (Word): ``pip install python-docx``
     * File Understanding (Excel): ``pip install openpyxl``
     * File Understanding (PowerPoint): ``pip install python-pptx``
     * File Generation (PDF): ``pip install reportlab``

2. **Generation Tool Configuration**

   * Enable generation capabilities with backend flags:

     * ``enable_image_generation: true`` for image generation
     * ``enable_video_generation: true`` for video generation
     * ``enable_audio_generation: true`` for speech generation
     * ``enable_file_generation: true`` for document generation

   * Set appropriate ``cwd`` for organized output storage
   * Use ``storage_path`` parameter to customize output locations
   * Verify generated content with corresponding understanding tools

3. **Performance and Cost Optimization**

   * **Understanding Tools:**

     * Set appropriate ``max_chars`` limits for large documents to control API costs
     * Adjust ``num_frames`` for videos (default: 8) based on content length and detail needed
     * Monitor OpenAI API usage when processing large files or many files

   * **Generation Tools:**

     * Image generation (GPT-4.1) is more expensive than standard API calls
     * Video generation (Sora-2) can be costly - use appropriate duration (4-20 seconds)
     * Speech generation costs vary by model (gpt-4o-audio-preview vs gpt-4o-mini-tts)
     * Use multi-agent to refine prompts before generation

4. **Quality and Accuracy**

   * **Understanding:**

     * Use high-quality source files (clear images, high-quality audio, well-lit videos)
     * Ask specific, detailed questions to get better responses
     * Use multi-agent collaboration for diverse perspectives on complex content

   * **Generation:**

     * Provide detailed, specific prompts for better generation results
     * For images: Include style, composition, lighting, and mood details
     * For videos: Specify scene, camera movements, duration, and atmosphere
     * For speech: Choose appropriate voice and specify emotional tone
     * For documents: Outline structure, sections, and formatting requirements
     * Combine understanding and generation agents for iterative refinement

5. **Workspace Management**

   * Configure ``cwd`` for organized file storage (both input and output)
   * Use ``snapshot_storage`` for agent collaboration and sharing generated content
   * Review generated content in agent workspaces before distribution
   * Include ``.massgen/`` in ``.gitignore``
   * Clean up old workspaces periodically to manage storage
   * Use descriptive filenames for generated content (automatic timestamp-based naming available)

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

**Content Understanding:**

* **Document Processing:**

  * Analyze PDFs, Word docs, Excel sheets, PowerPoint presentations
  * Extract data from forms, tables, and structured documents
  * Summarize research papers, technical documentation, and reports

* **Media Analysis:**

  * Transcribe meeting recordings, interviews, and podcasts
  * Analyze video content through key frame extraction
  * Extract information from screenshots, charts, and diagrams

* **Code and Visual Analysis:**

  * Code analysis with AI-powered explanations
  * Visual content description for accessibility
  * Scene detection and description in videos

**Content Generation:**

* **Creative Content Creation:**

  * Generate marketing visuals and product images from descriptions
  * Create social media content (images, videos, audio)
  * Produce concept art and design mockups
  * Generate voice-overs and narration for videos

* **Document and Report Generation:**

  * Automatically generate technical reports and white papers
  * Create formatted business documentation (PDF, MD, TXT)
  * Produce meeting summaries and documentation
  * Generate educational materials and training guides

* **Video Production:**

  * Create promotional and marketing videos from text descriptions
  * Generate concept visualization and storyboards
  * Produce educational content and tutorials
  * Create social media video content

* **Audio Content:**

  * Generate audiobooks and narrated content
  * Create podcast intros and outros
  * Produce accessibility audio for visually impaired users
  * Generate multilingual voice content

Next Steps
----------

* :doc:`backends` - Backend-specific multimodal capabilities
* :doc:`file_operations` - Workspace and file management
* :doc:`tools` - Custom tools configuration and usage
* :doc:`../examples/advanced_patterns` - Advanced multimodal patterns
* :doc:`../reference/yaml_schema` - Complete configuration reference
