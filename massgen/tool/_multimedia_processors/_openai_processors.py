# -*- coding: utf-8 -*-
"""OpenAI multimedia processing tools."""

import base64
import os
from typing import Any, Literal, Optional

from .._result import AudioContent, ExecutionResult, ImageContent, TextContent


async def openai_generate_image(
    description: str,
    output_path: Optional[str] = None,
    image_model: Literal["dall-e-2", "dall-e-3"] = "dall-e-3",
    resolution: Literal["256x256", "512x512", "1024x1024", "1792x1024", "1024x1792"] = "1024x1024",
    quality_level: Literal["standard", "hd"] = "standard",
    api_key: Optional[str] = None,
    **extra_params: Any,
) -> ExecutionResult:
    """Generate images using OpenAI's DALL-E models.

    Args:
        description: Text prompt for image generation
        output_path: Optional path to save the image
        image_model: DALL-E model version to use
        resolution: Image dimensions
        quality_level: Image quality setting
        api_key: OpenAI API key

    Returns:
        ExecutionResult with generated image
    """
    try:
        from openai import OpenAI

        # Initialize client
        client = OpenAI(api_key=api_key or os.environ.get("OPENAI_API_KEY"))

        if not client.api_key:
            return ExecutionResult(
                output_blocks=[
                    TextContent(
                        data="Error: OpenAI API key not provided or found in environment",
                    ),
                ],
            )

        # Generate image
        response = client.images.generate(
            model=image_model,
            prompt=description,
            size=resolution,
            quality=quality_level,
            n=1,
        )

        image_url = response.data[0].url

        # Save if path provided
        if output_path:
            import requests

            img_data = requests.get(image_url).content
            with open(output_path, "wb") as file:
                file.write(img_data)

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
                    data="Error: openai package not installed. Install with: pip install openai",
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


async def openai_generate_audio(
    text_input: str,
    output_path: Optional[str] = None,
    voice_model: Literal["alloy", "echo", "fable", "onyx", "nova", "shimmer"] = "nova",
    audio_model: Literal["tts-1", "tts-1-hd"] = "tts-1",
    audio_format: Literal["mp3", "opus", "aac", "flac"] = "mp3",
    speech_speed: float = 1.0,
    api_key: Optional[str] = None,
    **extra_params: Any,
) -> ExecutionResult:
    """Generate speech audio from text using OpenAI TTS.

    Args:
        text_input: Text to convert to speech
        output_path: Optional path to save audio file
        voice_model: Voice to use for speech
        audio_model: TTS model version
        audio_format: Output audio format
        speech_speed: Speech rate (0.25 to 4.0)
        api_key: OpenAI API key

    Returns:
        ExecutionResult with generated audio
    """
    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key or os.environ.get("OPENAI_API_KEY"))

        if not client.api_key:
            return ExecutionResult(
                output_blocks=[
                    TextContent(
                        data="Error: OpenAI API key not provided",
                    ),
                ],
            )

        response = client.audio.speech.create(
            model=audio_model,
            voice=voice_model,
            input=text_input,
            response_format=audio_format,
            speed=speech_speed,
        )

        audio_data = response.content

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
                    data="Error: openai package not installed",
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


async def openai_modify_image(
    original_image: str,
    mask_image: str,
    modification_prompt: str,
    output_path: Optional[str] = None,
    resolution: Literal["256x256", "512x512", "1024x1024"] = "1024x1024",
    api_key: Optional[str] = None,
    **extra_params: Any,
) -> ExecutionResult:
    """Edit an image with a mask using DALL-E.

    Args:
        original_image: Path to original image
        mask_image: Path to mask image (transparent areas to edit)
        modification_prompt: Description of desired changes
        output_path: Optional save path
        resolution: Output resolution
        api_key: OpenAI API key

    Returns:
        ExecutionResult with modified image
    """
    try:
        from openai import OpenAI

        if not os.path.exists(original_image):
            return ExecutionResult(
                output_blocks=[
                    TextContent(
                        data=f"Error: Original image '{original_image}' not found",
                    ),
                ],
            )

        if not os.path.exists(mask_image):
            return ExecutionResult(
                output_blocks=[
                    TextContent(
                        data=f"Error: Mask image '{mask_image}' not found",
                    ),
                ],
            )

        client = OpenAI(api_key=api_key or os.environ.get("OPENAI_API_KEY"))

        with open(original_image, "rb") as img_file:
            with open(mask_image, "rb") as mask_file:
                response = client.images.edit(
                    image=img_file,
                    mask=mask_file,
                    prompt=modification_prompt,
                    size=resolution,
                    n=1,
                )

        edited_url = response.data[0].url

        if output_path:
            import requests

            img_data = requests.get(edited_url).content
            with open(output_path, "wb") as file:
                file.write(img_data)

            return ExecutionResult(
                output_blocks=[
                    TextContent(
                        data=f"Image edited and saved to: {output_path}",
                    ),
                    ImageContent(data=edited_url),
                ],
            )
        else:
            return ExecutionResult(
                output_blocks=[
                    ImageContent(data=edited_url),
                ],
            )

    except Exception as error:
        return ExecutionResult(
            output_blocks=[
                TextContent(
                    data=f"Error editing image: {error}",
                ),
            ],
        )


async def openai_create_variation(
    source_image: str,
    output_path: Optional[str] = None,
    resolution: Literal["256x256", "512x512", "1024x1024"] = "1024x1024",
    num_variations: int = 1,
    api_key: Optional[str] = None,
    **extra_params: Any,
) -> ExecutionResult:
    """Create variations of an existing image.

    Args:
        source_image: Path to source image
        output_path: Optional save path
        resolution: Output resolution
        num_variations: Number of variations to generate
        api_key: OpenAI API key

    Returns:
        ExecutionResult with image variations
    """
    try:
        from openai import OpenAI

        if not os.path.exists(source_image):
            return ExecutionResult(
                output_blocks=[
                    TextContent(
                        data=f"Error: Source image '{source_image}' not found",
                    ),
                ],
            )

        client = OpenAI(api_key=api_key or os.environ.get("OPENAI_API_KEY"))

        with open(source_image, "rb") as img_file:
            response = client.images.create_variation(
                image=img_file,
                n=min(num_variations, 10),  # API limit
                size=resolution,
            )

        variation_urls = [img.url for img in response.data]

        if output_path:
            import requests

            for idx, url in enumerate(variation_urls):
                img_data = requests.get(url).content
                save_path = f"{output_path}_variation_{idx + 1}.png"
                with open(save_path, "wb") as file:
                    file.write(img_data)

            return ExecutionResult(
                output_blocks=[
                    TextContent(
                        data=f"Generated {len(variation_urls)} variations",
                    ),
                    *[ImageContent(data=url) for url in variation_urls],
                ],
            )
        else:
            return ExecutionResult(
                output_blocks=[
                    *[ImageContent(data=url) for url in variation_urls],
                ],
            )

    except Exception as error:
        return ExecutionResult(
            output_blocks=[
                TextContent(
                    data=f"Error creating variations: {error}",
                ),
            ],
        )


async def openai_analyze_image(
    image_path: str,
    analysis_prompt: str = "What's in this image?",
    vision_model: str = "gpt-4-vision-preview",
    api_key: Optional[str] = None,
    **extra_params: Any,
) -> ExecutionResult:
    """Analyze image content using GPT-4 Vision.

    Args:
        image_path: Path to image file
        analysis_prompt: Question about the image
        vision_model: Vision model to use
        api_key: OpenAI API key

    Returns:
        ExecutionResult with image analysis
    """
    try:
        from openai import OpenAI

        if not os.path.exists(image_path):
            return ExecutionResult(
                output_blocks=[
                    TextContent(
                        data=f"Error: Image '{image_path}' not found",
                    ),
                ],
            )

        client = OpenAI(api_key=api_key or os.environ.get("OPENAI_API_KEY"))

        # Encode image
        with open(image_path, "rb") as img_file:
            img_base64 = base64.b64encode(img_file.read()).decode("utf-8")

        response = client.chat.completions.create(
            model=vision_model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": analysis_prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{img_base64}",
                            },
                        },
                    ],
                },
            ],
            max_tokens=500,
        )

        analysis = response.choices[0].message.content

        return ExecutionResult(
            output_blocks=[
                TextContent(data=analysis),
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


async def openai_transcribe_audio(
    audio_path: str,
    output_format: Literal["text", "srt", "vtt", "json"] = "text",
    target_language: Optional[str] = None,
    api_key: Optional[str] = None,
    **extra_params: Any,
) -> ExecutionResult:
    """Transcribe audio to text using Whisper.

    Args:
        audio_path: Path to audio file
        output_format: Format for transcription output
        target_language: Optional language hint
        api_key: OpenAI API key

    Returns:
        ExecutionResult with transcription
    """
    try:
        from openai import OpenAI

        if not os.path.exists(audio_path):
            return ExecutionResult(
                output_blocks=[
                    TextContent(
                        data=f"Error: Audio file '{audio_path}' not found",
                    ),
                ],
            )

        client = OpenAI(api_key=api_key or os.environ.get("OPENAI_API_KEY"))

        with open(audio_path, "rb") as audio_file:
            transcription = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                response_format=output_format,
                language=target_language,
            )

        # Handle different output formats
        if output_format == "json":
            result_text = str(transcription)
        else:
            result_text = transcription

        return ExecutionResult(
            output_blocks=[
                TextContent(
                    data=f"Transcription:\n{result_text}",
                ),
            ],
        )

    except Exception as error:
        return ExecutionResult(
            output_blocks=[
                TextContent(
                    data=f"Error transcribing audio: {error}",
                ),
            ],
        )
