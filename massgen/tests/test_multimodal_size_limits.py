#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for size and dimension limits in multimodal tools (image, video, audio).

This test suite generates fake media files to test:
- understand_image: 18MB file size + 768px × 2000px dimension limits
- understand_video: Frame dimension limits (768px × 2000px per frame)
- understand_audio: 25MB file size limit

All test files are created in temporary directories and cleaned up after tests.
"""

import tempfile
from pathlib import Path

import pytest


class TestImageSizeLimits:
    """Test suite for understand_image size and dimension limits."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for test files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def _create_test_image(self, width: int, height: int, output_path: Path, format: str = "PNG"):
        """
        Create a test image with specified dimensions.

        Args:
            width: Image width in pixels
            height: Image height in pixels
            output_path: Path to save the image
            format: Image format (PNG or JPEG)
        """
        import numpy as np
        from PIL import Image

        # Create a simple gradient image
        img_array = np.zeros((height, width, 3), dtype=np.uint8)
        for i in range(height):
            img_array[i, :, 0] = int((i / height) * 255)  # Red gradient
        for j in range(width):
            img_array[:, j, 1] = int((j / width) * 255)  # Green gradient

        img = Image.fromarray(img_array, "RGB")
        img.save(output_path, format=format)

    def _create_large_image(self, output_path: Path, target_size_mb: float = 20):
        """
        Create a large image file exceeding size limits.

        Args:
            output_path: Path to save the image
            target_size_mb: Target size in megabytes
        """
        import numpy as np
        from PIL import Image

        # Calculate dimensions to achieve target file size
        # PNG compression varies, so we'll create a large uncompressed image
        # Rough estimate: width * height * 3 (RGB) should exceed target
        pixels_needed = int((target_size_mb * 1024 * 1024) / 3)
        side = int(pixels_needed**0.5)

        # Create random noise image (doesn't compress well)
        img_array = np.random.randint(0, 256, (side, side, 3), dtype=np.uint8)
        img = Image.fromarray(img_array, "RGB")
        img.save(output_path, format="PNG")

    @pytest.mark.asyncio
    async def test_image_within_limits(self, temp_dir):
        """Test that images within size and dimension limits are processed without resizing."""
        from massgen.tool._multimodal_tools.understand_image import understand_image

        # Create a small image within limits (512x512)
        img_path = temp_dir / "small_image.png"
        self._create_test_image(512, 512, img_path, format="PNG")

        # Use real OpenAI API
        result = await understand_image(str(img_path), prompt="Describe this test image in one sentence.")

        # Check that it succeeded
        assert result.output_blocks is not None
        assert len(result.output_blocks) > 0

        # Parse result JSON
        import json

        result_data = json.loads(result.output_blocks[0].data)

        print("\n" + "=" * 80)
        print("TEST: Image Within Limits (512x512)")
        print("=" * 80)
        print(json.dumps(result_data, indent=2))
        print("=" * 80 + "\n")

        assert result_data["success"] is True

    @pytest.mark.asyncio
    async def test_image_dimension_limit(self, temp_dir):
        """Test that images exceeding dimension limits are resized."""
        from massgen.tool._multimodal_tools.understand_image import understand_image

        # Create an image exceeding dimension limits (3000x4000)
        img_path = temp_dir / "large_dimensions.jpg"
        self._create_test_image(3000, 4000, img_path, format="JPEG")

        # Check original size
        from PIL import Image

        with Image.open(img_path) as img:
            original_width, original_height = img.size
            assert original_width == 3000
            assert original_height == 4000

        # Use real OpenAI API - should resize internally and succeed
        result = await understand_image(str(img_path), prompt="Describe this test image in one sentence.")

        # Check that it succeeded (image was resized internally)
        assert result.output_blocks is not None
        import json

        result_data = json.loads(result.output_blocks[0].data)

        print("\n" + "=" * 80)
        print("TEST: Image Exceeding Dimension Limits (3000x4000)")
        print("=" * 80)
        print(json.dumps(result_data, indent=2))
        print("=" * 80 + "\n")

        assert result_data["success"] is True

    def test_image_dimension_calculation(self, temp_dir):
        """Test dimension limit calculation logic directly."""
        # Test that we correctly identify when resizing is needed
        max_short_side = 768
        max_long_side = 2000

        test_cases = [
            # (width, height, needs_resize)
            (512, 512, False),  # Within limits
            (768, 2000, False),  # Exactly at limits
            (2000, 768, False),  # Rotated, exactly at limits
            (800, 1000, True),  # Short side exceeds
            (1000, 2500, True),  # Long side exceeds
            (3000, 4000, True),  # Both exceed
        ]

        for width, height, expected_resize in test_cases:
            short_side = min(width, height)
            long_side = max(width, height)
            needs_resize = short_side > max_short_side or long_side > max_long_side

            assert needs_resize == expected_resize, f"Dimension check failed for {width}x{height}: expected resize={expected_resize}, got {needs_resize}"


class TestVideoFrameLimits:
    """Test suite for understand_video frame dimension limits."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for test files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def _create_test_video(self, width: int, height: int, output_path: Path, num_frames: int = 30):
        """
        Create a test video with specified dimensions.

        Args:
            width: Video width in pixels
            height: Video height in pixels
            output_path: Path to save the video
            num_frames: Number of frames to generate
        """
        import cv2
        import numpy as np

        # Define the codec and create VideoWriter object
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        fps = 10.0
        video = cv2.VideoWriter(str(output_path), fourcc, fps, (width, height))

        try:
            for i in range(num_frames):
                # Create a frame with gradient (changes over time)
                frame = np.zeros((height, width, 3), dtype=np.uint8)
                intensity = int((i / num_frames) * 255)
                frame[:, :, 0] = intensity  # Blue channel varies by frame
                frame[: height // 2, :, 1] = 128  # Green in top half
                frame[height // 2 :, :, 2] = 128  # Red in bottom half

                video.write(frame)
        finally:
            video.release()

    @pytest.mark.asyncio
    async def test_video_with_large_frames(self, temp_dir):
        """Test that video with large frame dimensions processes correctly (frames are resized)."""
        try:
            import cv2  # noqa: F401
        except ImportError:
            pytest.skip("opencv-python not installed")

        from massgen.tool._multimodal_tools.understand_video import understand_video

        # Create a video with large dimensions (3000x4000)
        video_path = temp_dir / "large_video.mp4"
        self._create_test_video(3000, 4000, video_path, num_frames=10)

        # Use real OpenAI API - should resize frames internally and succeed
        result = await understand_video(
            str(video_path),
            num_frames=3,
            prompt="Describe what you see in this test video in one sentence.",
        )

        # Check that it succeeded
        assert result.output_blocks is not None
        import json

        result_data = json.loads(result.output_blocks[0].data)

        print("\n" + "=" * 80)
        print("TEST: Video With Large Frames (3000x4000) - Frames Should Be Resized")
        print("=" * 80)
        print(json.dumps(result_data, indent=2))
        print("=" * 80 + "\n")

        assert result_data["success"] is True

    @pytest.mark.asyncio
    async def test_video_with_small_frames(self, temp_dir):
        """Test that video with small frame dimensions processes without resizing."""
        try:
            import cv2  # noqa: F401
        except ImportError:
            pytest.skip("opencv-python not installed")

        from massgen.tool._multimodal_tools.understand_video import understand_video

        # Create a video with small dimensions (640x480)
        video_path = temp_dir / "small_video.mp4"
        self._create_test_video(640, 480, video_path, num_frames=10)

        # Use real OpenAI API
        result = await understand_video(
            str(video_path),
            num_frames=3,
            prompt="Describe what you see in this test video in one sentence.",
        )

        # Check that it succeeded
        assert result.output_blocks is not None
        import json

        result_data = json.loads(result.output_blocks[0].data)

        print("\n" + "=" * 80)
        print("TEST: Video With Small Frames (640x480) - No Resize Needed")
        print("=" * 80)
        print(json.dumps(result_data, indent=2))
        print("=" * 80 + "\n")

        assert result_data["success"] is True


class TestAudioSizeLimits:
    """Test suite for understand_audio file size limits."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for test files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def _create_test_audio(self, output_path: Path, duration_seconds: float = 1.0, sample_rate: int = 44100):
        """
        Create a test audio file (WAV format).

        Args:
            output_path: Path to save the audio file
            duration_seconds: Duration in seconds
            sample_rate: Sample rate in Hz
        """
        import wave

        import numpy as np

        # Generate a simple sine wave
        frequency = 440.0  # A4 note
        num_samples = int(sample_rate * duration_seconds)
        t = np.linspace(0, duration_seconds, num_samples, False)
        audio_data = np.sin(2 * np.pi * frequency * t)

        # Convert to 16-bit PCM
        audio_data = (audio_data * 32767).astype(np.int16)

        # Write WAV file
        with wave.open(str(output_path), "w") as wav_file:
            wav_file.setnchannels(1)  # Mono
            wav_file.setsampwidth(2)  # 16-bit
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(audio_data.tobytes())

    def _create_large_audio(self, output_path: Path, target_size_mb: float = 30):
        """
        Create a large audio file exceeding size limits.

        Args:
            output_path: Path to save the audio file
            target_size_mb: Target size in megabytes
        """
        # Calculate duration needed to achieve target size
        # WAV: sample_rate * duration * 2 bytes (16-bit) * channels
        sample_rate = 44100
        bytes_per_second = sample_rate * 2  # 16-bit mono
        duration_seconds = (target_size_mb * 1024 * 1024) / bytes_per_second

        self._create_test_audio(output_path, duration_seconds=duration_seconds, sample_rate=sample_rate)

    @pytest.mark.asyncio
    async def test_audio_within_size_limit(self, temp_dir):
        """Test that audio files within size limit are accepted."""
        from massgen.tool._multimodal_tools.understand_audio import understand_audio

        # Create a small audio file (~1 second, ~88KB)
        audio_path = temp_dir / "small_audio.wav"
        self._create_test_audio(audio_path, duration_seconds=1.0)

        file_size = audio_path.stat().st_size
        assert file_size < 25 * 1024 * 1024, "Test audio should be under 25MB"

        # Use real OpenAI API
        result = await understand_audio([str(audio_path)])

        # Check that it succeeded
        assert result.output_blocks is not None
        import json

        result_data = json.loads(result.output_blocks[0].data)

        print("\n" + "=" * 80)
        print(f"TEST: Audio Within Size Limit (~{file_size/1024/1024:.2f}MB)")
        print("=" * 80)
        print(json.dumps(result_data, indent=2))
        print("=" * 80 + "\n")

        assert result_data["success"] is True

    @pytest.mark.asyncio
    async def test_audio_exceeds_size_limit(self, temp_dir):
        """Test that audio files exceeding 25MB limit are rejected."""
        from massgen.tool._multimodal_tools.understand_audio import understand_audio

        # Create a large audio file (~30MB)
        audio_path = temp_dir / "large_audio.wav"
        self._create_large_audio(audio_path, target_size_mb=30)

        file_size = audio_path.stat().st_size
        assert file_size > 25 * 1024 * 1024, f"Test audio should exceed 25MB, got {file_size / 1024 / 1024:.1f}MB"

        # This should fail validation before calling OpenAI
        result = await understand_audio([str(audio_path)])

        # Check that it failed due to size limit
        assert result.output_blocks is not None
        import json

        result_data = json.loads(result.output_blocks[0].data)

        print("\n" + "=" * 80)
        print(f"TEST: Audio Exceeds Size Limit ({file_size/1024/1024:.1f}MB > 25MB)")
        print("=" * 80)
        print(json.dumps(result_data, indent=2))
        print("=" * 80 + "\n")

        assert result_data["success"] is False
        assert "too large" in result_data["error"].lower()
        assert "25MB" in result_data["error"]

    def test_audio_size_check(self, temp_dir):
        """Test audio file size checking logic."""
        # Create audio files of different sizes
        test_cases = [
            (1.0, True),  # 1 second (~88KB) - should pass
            (10.0, True),  # 10 seconds (~880KB) - should pass
        ]

        for duration, should_pass in test_cases:
            audio_path = temp_dir / f"audio_{duration}s.wav"
            self._create_test_audio(audio_path, duration_seconds=duration)

            file_size = audio_path.stat().st_size
            max_size = 25 * 1024 * 1024

            passes = file_size <= max_size

            assert passes == should_pass, f"Size check failed for {duration}s audio ({file_size / 1024 / 1024:.1f}MB): " f"expected pass={should_pass}, got {passes}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
