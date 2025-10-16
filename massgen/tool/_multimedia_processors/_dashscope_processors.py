# -*- coding: utf-8 -*-
"""DashScope multimedia processing tools."""

import base64
import os
from typing import Any, Literal, Optional

from .._result import AudioContent, ExecutionResult, ImageContent, TextContent


async def dashscope_generate_image(
    description: str,
    output_path: Optional[str] = None,
    image_style: Literal["realistic", "anime", "cartoon"] = "realistic",
    resolution: Literal["512x512", "1024x1024"] = "1024x1024",
    api_key: Optional[str] = None,
    **extra_params: Any,
) -> ExecutionResult:
    """Generate images from text descriptions using DashScope API.

    Args:
        description: Text prompt describing the desired image
        output_path: Optional path to save the generated image
        image_style: Style of the generated image
        resolution: Image resolution
        api_key: DashScope API key (uses env var if not provided)

    Returns:
        ExecutionResult with generated image data
    """
    try:
        # Import dashscope here to avoid dependency if not used
        import dashscope
        from dashscope import ImageSynthesis

        # Configure API key
        if api_key:
            dashscope.api_key = api_key
        elif not os.environ.get("DASHSCOPE_API_KEY"):
            return ExecutionResult(
                output_blocks=[
                    TextContent(
                        data="Error: DashScope API key not provided or found in environment",
                    ),
                ],
            )

        # Generate image
        response = ImageSynthesis.call(
            model=ImageSynthesis.Models.wanx_v1,
            prompt=description,
            n=1,
            size=resolution,
            style=f"<{image_style}>",
        )

        if response.status_code != 200:
            return ExecutionResult(
                output_blocks=[
                    TextContent(
                        data=f"Error: API returned status {response.status_code}: {response.message}",
                    ),
                ],
            )

        image_url = response.output["results"][0]["url"]

        # Download image if output path specified
        if output_path:
            import requests

            img_response = requests.get(image_url)
            with open(output_path, "wb") as file:
                file.write(img_response.content)

            return ExecutionResult(
                output_blocks=[
                    TextContent(
                        data=f"Image generated and saved to: {output_path}",
                    ),
                    ImageContent(data=image_url),
                ],
            )
        else:
            return ExecutionResult(
                output_blocks=[
                    ImageContent(data=image_url),
                ],
            )

    except ImportError:
        return ExecutionResult(
            output_blocks=[
                TextContent(
                    data="Error: dashscope package not installed. Install with: pip install dashscope",
                ),
            ],
        )
    except Exception as error:
        return ExecutionResult(
            output_blocks=[
                TextContent(
                    data=f"Error generating image: {error}",
                ),
            ],
        )


async def dashscope_generate_audio(
    text_input: str,
    output_path: Optional[str] = None,
    voice_type: Literal["male", "female"] = "female",
    speech_rate: float = 1.0,
    api_key: Optional[str] = None,
    **extra_params: Any,
) -> ExecutionResult:
    """Generate audio speech from text using DashScope API.

    Args:
        text_input: Text to convert to speech
        output_path: Optional path to save the audio file
        voice_type: Voice gender selection
        speech_rate: Speed of speech (0.5 to 2.0)
        api_key: DashScope API key

    Returns:
        ExecutionResult with generated audio data
    """
    try:
        import dashscope
        from dashscope.audio.tts import SpeechSynthesizer

        if api_key:
            dashscope.api_key = api_key
        elif not os.environ.get("DASHSCOPE_API_KEY"):
            return ExecutionResult(
                output_blocks=[
                    TextContent(
                        data="Error: DashScope API key not provided or found in environment",
                    ),
                ],
            )

        # Configure voice
        voice_model = "sambert-zhichu-v1" if voice_type == "female" else "sambert-zhida-v1"

        response = SpeechSynthesizer.call(
            model=voice_model,
            text=text_input,
            sample_rate=16000,
            speech_rate=int(speech_rate * 100),
        )

        if response.get_audio_data() is None:
            return ExecutionResult(
                output_blocks=[
                    TextContent(
                        data="Error: Failed to generate audio",
                    ),
                ],
            )

        audio_data = response.get_audio_data()

        if output_path:
            with open(output_path, "wb") as file:
                file.write(audio_data)

            return ExecutionResult(
                output_blocks=[
                    TextContent(
                        data=f"Audio generated and saved to: {output_path}",
                    ),
                    AudioContent(
                        data=base64.b64encode(audio_data).decode("utf-8"),
                    ),
                ],
            )
        else:
            return ExecutionResult(
                output_blocks=[
                    AudioContent(
                        data=base64.b64encode(audio_data).decode("utf-8"),
                    ),
                ],
            )

    except ImportError:
        return ExecutionResult(
            output_blocks=[
                TextContent(
                    data="Error: dashscope package not installed",
                ),
            ],
        )
    except Exception as error:
        return ExecutionResult(
            output_blocks=[
                TextContent(
                    data=f"Error generating audio: {error}",
                ),
            ],
        )


async def dashscope_analyze_image(
    image_path: str,
    analysis_prompt: str = "Describe this image in detail",
    api_key: Optional[str] = None,
    **extra_params: Any,
) -> ExecutionResult:
    """Analyze image content using DashScope vision API.

    Args:
        image_path: Path to the image file
        analysis_prompt: Question or prompt about the image
        api_key: DashScope API key

    Returns:
        ExecutionResult with image analysis
    """
    try:
        import dashscope
        from dashscope import MultiModalConversation

        if not os.path.exists(image_path):
            return ExecutionResult(
                output_blocks=[
                    TextContent(
                        data=f"Error: Image file '{image_path}' not found",
                    ),
                ],
            )

        if api_key:
            dashscope.api_key = api_key
        elif not os.environ.get("DASHSCOPE_API_KEY"):
            return ExecutionResult(
                output_blocks=[
                    TextContent(
                        data="Error: DashScope API key not provided",
                    ),
                ],
            )

        # Encode image
        with open(image_path, "rb") as file:
            image_data = base64.b64encode(file.read()).decode("utf-8")

        messages = [
            {
                "role": "user",
                "content": [
                    {"image": f"data:image/jpeg;base64,{image_data}"},
                    {"text": analysis_prompt},
                ],
            }
        ]

        response = MultiModalConversation.call(
            model="qwen-vl-plus",
            messages=messages,
        )

        if response.status_code != 200:
            return ExecutionResult(
                output_blocks=[
                    TextContent(
                        data=f"Error: API returned {response.status_code}",
                    ),
                ],
            )

        analysis_result = response.output.choices[0].message.content[0]["text"]

        return ExecutionResult(
            output_blocks=[
                TextContent(data=analysis_result),
            ],
        )

    except ImportError:
        return ExecutionResult(
            output_blocks=[
                TextContent(
                    data="Error: dashscope package not installed",
                ),
            ],
        )
    except Exception as error:
        return ExecutionResult(
            output_blocks=[
                TextContent(
                    data=f"Error analyzing image: {error}",
                ),
            ],
        )
