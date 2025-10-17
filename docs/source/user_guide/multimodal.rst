Multimodal Capabilities
=======================

MassGen supports comprehensive multimodal AI workflows, enabling agents to work with images, audio, and video content. This includes generation (creating new content), understanding (analyzing existing content), and file-based interactions.

.. note::

   **Multimodal Timeline:**

   * **v0.0.27**: Image generation and understanding
   * **v0.0.30**: Audio and video understanding
   * **v0.0.31**: Audio generation (text-to-speech, transcription) and video generation (Sora-2)

.. warning::
   **Current Multimodal Limitations:**

   Agents **cannot directly analyze** multimodal content (images, audio, video) they generate in their workspace. Generated files are saved but not directly accessible for analysis.

   **What works:**

   * ✅ Generate images/audio/video from text prompts
   * ✅ Upload and analyze pre-existing multimodal files via ``upload_files`` configuration
   * ✅ Process multimodal content **when used as input** to generation tools:

      - Call ``generate_and_store_image_with_input_images`` with a generated image → Agent can "see" it during generation
      - Call ``generate_text_with_input_audio`` with generated audio → Agent can read/transcribe it

   **What doesn't work:**

   * ❌ Agent generates an image → Agent cannot directly analyze that image
   * ❌ Agent generates audio → Agent cannot directly transcribe/analyze it (unless using it as input to another tool)
   * ❌ Multi-agent workflows where Agent A generates content and Agent B analyzes it

   **Workaround:** To analyze generated multimodal content, you must use it as **input** to another generation/processing tool (e.g., generate image variation with input image, transcribe audio). The content is only "readable" during API processing, not through direct workspace file access.

   **Note:** Direct workspace multimodal file reading (``read_multimodal_files``) is planned for future releases.

Overview
--------

Multimodal capabilities extend MassGen's multi-agent collaboration across different content types:

**Image Capabilities:**

* **Generation**: Create images from text descriptions (DALL-E, Imagen)
* **Understanding**: Analyze and describe image content (Vision models)

**Audio Capabilities:**

* **Generation**: Text-to-speech, audio synthesis
* **Understanding**: Transcription, audio analysis

**Video Capabilities:**

* **Generation**: Create videos from text prompts (Sora-2)
* **Understanding**: Analyze video content

**File Operations:**

* **Upload and Search**: Work with documents and files (RAG)
* **MCP Tools**: Read multimodal files with base64 encoding

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

Audio Capabilities
------------------

MassGen supports both audio generation (creating speech from text) and audio understanding (transcribing and analyzing audio files).

Audio Generation (Text-to-Speech)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Convert text to natural-sounding speech using OpenAI's text-to-speech models:

.. code-block:: yaml

   agents:
     - id: "audio_creator"
       backend:
         type: "openai"
         model: "gpt-4o-audio-preview"
         cwd: "workspace"
         enable_audio_generation: true

**Available Voices:**

* **alloy**: Neutral, balanced voice
* **echo**: Warm, engaging voice
* **fable**: Expressive, storytelling voice
* **onyx**: Deep, authoritative voice
* **nova**: Friendly, energetic voice
* **shimmer**: Soft, gentle voice
* **coral**: Warm, conversational voice
* **sage**: Calm, wise voice

**Supported Formats:**

* WAV, MP3, Opus, AAC, FLAC

**Example Command:**

.. code-block:: bash

   massgen \
     --config @examples/basic/single/single_gpt4o_audio_generation.yaml \
     "Generate a podcast introduction with a professional tone"

**Configuration Options:**

.. code-block:: yaml

   backend:
     type: "openai"
     model: "gpt-4o-audio-preview"
     enable_audio_generation: true
     audio_voice: "alloy"              # Choose voice
     audio_format: "mp3"               # Output format
     speaking_instructions: "Speak in a professional, clear tone"

Audio Understanding (Transcription)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Transcribe and analyze audio files:

.. code-block:: yaml

   agents:
     - id: "transcriber"
       backend:
         type: "openai"
         model: "gpt-4o"
         upload_files:
           - audio_path: "path/to/audio.mp3"

**Supported Formats:**

* MP3, MP4, M4A, WAV, WEBM

**Example Use Cases:**

* Meeting transcription
* Podcast analysis
* Voice memo processing
* Interview transcription
* Audio content summarization

Video Capabilities
------------------

MassGen supports video generation (creating videos from text) and video understanding (analyzing video content).

Video Generation
~~~~~~~~~~~~~~~~

Create videos from text descriptions using OpenAI's Sora-2 API:

.. code-block:: yaml

   agents:
     - id: "video_creator"
       backend:
         type: "openai"
         model: "sora-2"
         cwd: "workspace"
         enable_video_generation: true

**Example Command:**

.. code-block:: bash

   massgen \
     --config @examples/basic/single/single_gpt4o_video_generation.yaml \
     "Create a 10-second video of ocean waves at sunset"

**Features:**

* Asynchronous video generation with progress monitoring
* Automatic MP4 format output
* Configurable video duration
* Workspace storage and organization

**Configuration:**

.. code-block:: yaml

   backend:
     type: "openai"
     model: "sora-2"
     enable_video_generation: true
     video_duration: 10  # Duration in seconds

Video Understanding
~~~~~~~~~~~~~~~~~~~

Analyze and extract information from video files:

.. code-block:: yaml

   agents:
     - id: "video_analyzer"
       backend:
         type: "claude"  # or chatcompletion, qwen
         model: "claude-sonnet-4"
         upload_files:
           - video_path: "path/to/video.mp4"

**Supported Backends:**

* Claude (Anthropic): Video understanding
* ChatCompletion providers: Varies by provider
* Qwen API: Video understanding support

**Supported Formats:**

* MP4, AVI, MOV, WEBM

**Example Use Cases:**

* Video content analysis
* Scene detection and description
* Action recognition
* Video summarization
* Quality assessment

**Example Configuration:**

.. code-block:: yaml

   agents:
     - id: "qwen_video"
       backend:
         type: "chatcompletion"
         model: "qwen-vl-max"
         base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1"
         api_key: "${QWEN_API_KEY}"
         upload_files:
           - video_path: "@examples/resources/demo_video.mp4"

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

Multimodal capabilities vary by backend. This table shows which backends support which multimodal features:

.. list-table:: Backend Multimodal Capabilities
   :header-rows: 1
   :widths: 15 12 12 12 12 12 12

   * - Backend
     - Image
     - Audio
     - Video
     - File Upload
     - File Search
     - Notes
   * - ``openai``
     - ⭐ Both
     - ⭐ Both
     - ⭐ Generation
     - ✅
     - ✅
     - DALL-E, TTS, Sora-2
   * - ``claude``
     - ✅ Understanding
     - ✅ Understanding
     - ✅ Understanding
     - ✅
     - ❌
     - Vision models
   * - ``claude_code``
     - ✅ Understanding
     - ❌
     - ❌
     - ⭐ Native
     - ❌
     - Native file tools
   * - ``gemini``
     - ✅ Understanding
     - ❌
     - ❌
     - ✅
     - ❌
     - Multimodal Pro/Flash
   * - ``grok``
     - ❌
     - ❌
     - ❌
     - ❌
     - ❌
     - Limited multimodal
   * - ``azure_openai``
     - ⭐ Both
     - ❌
     - ❌
     - ✅
     - ❌
     - DALL-E support
   * - ``chatcompletion``
     - ❌
     - ✅ Understanding
     - ✅ Understanding
     - ✅
     - ❌
     - Provider-dependent

**Legend:**

* ⭐ **Both** - Supports BOTH understanding (analyze existing) AND generation (create new)
* ✅ **Understanding** - Can analyze/process existing content only
* ✅ **Generation** - Can create new content only
* ✅ **Available** - Feature supported
* ❌ **Not available** - Feature not supported

**Capability Details:**

* **Image Both**: Can analyze images you provide AND generate new images (e.g., ``openai``, ``azure_openai``)
* **Audio Both**: Can transcribe/analyze audio AND generate speech (e.g., ``openai`` with TTS)
* **Video Generation**: Can create videos from text (e.g., ``openai`` with Sora-2)
* **Understanding Only**: Can only analyze existing content, not create new (e.g., ``claude``, ``gemini``)
* **Native**: Built into the backend (e.g., ``claude_code`` filesystem tools)

**Provider-Specific Notes:**

* **OpenAI**: Most comprehensive multimodal support (DALL-E, TTS, Sora-2)
* **Claude**: Strong vision capabilities, audio/video understanding
* **Gemini**: Multimodal understanding with Flash/Pro models
* **Azure OpenAI**: Image generation/understanding via DALL-E
* **ChatCompletion**: Varies by provider (Qwen, etc.)

See :doc:`backends` for complete backend capabilities including web search, code execution, and MCP support.

Configuration Examples
----------------------

Complete configuration files are available in the MassGen repository:

**Image:**

* ``@examples/basic/single/single_gpt4o_image_generation.yaml`` - Single agent image generation
* ``@examples/basic/multi/gpt4o_image_generation.yaml`` - Multi-agent image generation
* ``@examples/basic/single/single_gpt5nano_image_understanding.yaml`` - Image understanding
* ``@examples/basic/multi/gpt5nano_image_understanding.yaml`` - Multi-agent image analysis

**Audio:**

* ``@examples/basic/single/single_gpt4o_audio_generation.yaml`` - Text-to-speech generation
* ``@examples/basic/multi/gpt4o_audio_generation.yaml`` - Multi-agent audio generation
* ``@examples/basic/single/single_openrouter_audio_understanding.yaml`` - Audio transcription

**Video:**

* ``@examples/basic/single/single_gpt4o_video_generation.yaml`` - Video generation with Sora-2
* ``@examples/basic/single/single_qwen_video_understanding.yaml`` - Video analysis with Qwen

**File Operations:**

* ``@examples/basic/single/single_gpt5nano_file_search.yaml`` - Document Q&A with file search

Browse all examples in the `Configuration README <https://github.com/Leezekun/MassGen/blob/main/@examples/README.md>`_.

Best Practices
--------------

1. **Image Generation**

   * Use descriptive, detailed prompts with style and mood
   * Leverage multiple agents for prompt refinement
   * Specify composition, lighting, and artistic style clearly
   * Review generated images in agent workspaces
   * Iterate on prompts based on results

2. **Image Understanding**

   * Upload high-quality images for better analysis
   * Ask specific questions about image content
   * Use multi-agent collaboration for diverse perspectives
   * Combine with web search for contextual information
   * Specify aspect ratio and resolution when needed

3. **Audio Generation**

   * Choose appropriate voice for your use case (professional, friendly, etc.)
   * Use ``speaking_instructions`` to control tone and style
   * Select optimal audio format (MP3 for general use, WAV for high quality)
   * Test different voices to find the best match
   * Review generated audio in workspaces

4. **Audio Understanding**

   * Use clear, high-quality audio recordings
   * Supported formats: MP3, WAV, M4A, WEBM
   * Combine transcription with analysis tasks
   * Ask specific questions about audio content
   * Monitor file size limits (default 64MB)

5. **Video Generation**

   * Write detailed scene descriptions with action and movement
   * Specify duration (typically 5-10 seconds for Sora-2)
   * Be patient - video generation is asynchronous
   * Review generated videos in MP4 format
   * Iterate on prompts for better results

6. **Video Understanding**

   * Upload clear, well-lit videos
   * Supported formats: MP4, AVI, MOV, WEBM
   * Ask about specific scenes, actions, or content
   * Use appropriate backends (Claude, Qwen for video)
   * Monitor file size limits

7. **File Upload and Search**

   * Organize files logically before upload
   * Use vector store search for large document collections
   * Clean up uploaded files after processing
   * Monitor API costs for file storage and search
   * Test file paths before deployment

8. **Workspace Management**

   * Configure ``cwd`` for organized file storage
   * Use ``snapshot_storage`` for agent collaboration
   * Review generated/analyzed content in workspaces
   * Include ``.massgen/`` in ``.gitignore``
   * Clean up old workspaces periodically

Troubleshooting
---------------

**Image Issues:**

* **Image generation not working:** Ensure ``enable_image_generation: true`` in backend configuration

  .. code-block:: yaml

     backend:
       type: "openai"
       model: "gpt-4o"
       enable_image_generation: true  # Required for DALL-E

* **Image upload fails:** Verify image path is correct and accessible. Use absolute paths or paths relative to execution directory.

**Audio Issues:**

* **Audio generation fails:** Ensure you're using a supported model (``gpt-4o-audio-preview``) with ``enable_audio_generation: true``

  .. code-block:: yaml

     backend:
       type: "openai"
       model: "gpt-4o-audio-preview"
       enable_audio_generation: true
       audio_voice: "alloy"  # Choose from available voices

* **Audio file too large:** Check file size limits (default 64MB). Configure with ``media_max_file_size_mb``

  .. code-block:: yaml

     backend:
       type: "openai"
       media_max_file_size_mb: 100  # Increase limit if needed

* **Unsupported audio format:** Use MP3, WAV, M4A, or WEBM formats

**Video Issues:**

* **Video generation slow:** Video generation is asynchronous and can take several minutes. Monitor progress in logs.

* **Video understanding not working:** Ensure you're using a supported backend (Claude, Qwen) with video capabilities

  .. code-block:: yaml

     backend:
       type: "claude"
       model: "claude-sonnet-4"
       upload_files:
         - video_path: "path/to/video.mp4"

* **Video file too large:** Check file size limits. Videos should typically be under 64MB.

**General File Issues:**

* **File not found in workspace:** Check agent's ``cwd`` configuration

  .. code-block:: yaml

     backend:
       cwd: "workspace1"  # Files stored in .massgen/workspaces/workspace1/

* **Vector store errors:** Enable file search explicitly

  .. code-block:: yaml

     backend:
       type: "openai"
       model: "gpt-5-nano"
       enable_file_search: true

* **Permission errors:** Ensure files are readable and paths are accessible

**API Cost Issues:**

* Monitor multimodal API usage carefully - image/audio/video generation can be expensive
* Clean up uploaded files and vector stores after use
* Use appropriate file sizes and durations to control costs

Use Cases
---------

**Image Use Cases:**

* **Creative Design**: Logo generation, marketing assets, visual concept exploration
* **Document Analysis**: PDF Q&A, scanned form understanding, chart analysis
* **Content Creation**: Image descriptions for accessibility, social media content
* **Research**: Scientific image analysis, medical imaging, visual data extraction

**Audio Use Cases:**

* **Content Creation**: Podcast generation, audiobook narration, voiceover production
* **Transcription**: Meeting notes, interview transcription, voice memo processing
* **Accessibility**: Text-to-speech for visually impaired, audio descriptions
* **Language Learning**: Pronunciation practice, language tutorials, conversation practice
* **Customer Service**: IVR systems, automated responses, customer support audio

**Video Use Cases:**

* **Marketing**: Product demonstrations, explainer videos, social media content
* **Education**: Tutorial videos, educational content, training materials
* **Entertainment**: Short-form content creation, video concepts, storyboarding
* **Analysis**: Video content summarization, scene detection, quality assessment
* **Security**: Surveillance analysis, incident review, activity recognition

**Multi-Modal Workflows:**

* **Podcast Production**: Generate script → Text-to-speech → Audio editing workflow
* **Video Marketing**: Generate storyboard image → Create video → Add voiceover
* **Document Processing**: Scan document → OCR with vision → Generate audio summary
* **Educational Content**: Create visual aids → Generate explanation videos → Add narration
* **Accessibility**: Take image → Generate description → Convert to speech

**Enterprise Applications:**

* **Documentation**: Convert technical docs to multimedia formats
* **Training**: Create multi-modal training materials automatically
* **Marketing**: Generate coordinated image, audio, and video campaigns
* **Customer Support**: Multi-modal knowledge base with images, videos, and audio guides

Next Steps
----------

* :doc:`backends` - Backend-specific multimodal capabilities
* :doc:`file_operations` - Workspace and file management
* :doc:`mcp_integration` - MCP tools for multimodal workflows
* :doc:`../examples/advanced_patterns` - Advanced multimodal patterns
* :doc:`../reference/yaml_schema` - Complete configuration reference
