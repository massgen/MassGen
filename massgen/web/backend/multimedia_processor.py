"""
Multimedia Processing for MassGen Web Interface

Handles image, audio, and video processing with thumbnail generation.
"""

import asyncio
import os
from pathlib import Path
from typing import Dict, Any, Optional

# Conditional imports for multimedia processing
try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

try:
    import librosa
    LIBROSA_AVAILABLE = True
except ImportError:
    LIBROSA_AVAILABLE = False

class MultimediaProcessor:
    """Handles multimedia file processing and thumbnail generation"""
    
    def __init__(self, storage_dir: str = "./web_uploads"):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(exist_ok=True)
        
        # Create subdirectories
        (self.storage_dir / "thumbnails").mkdir(exist_ok=True)
        (self.storage_dir / "processed").mkdir(exist_ok=True)
        
    async def process_image(self, file_path: str) -> Dict[str, Any]:
        """Process uploaded image and create thumbnail"""
        try:
            if not PIL_AVAILABLE:
                return {
                    "error": "PIL not available for image processing",
                    "dimensions": None,
                    "format": None,
                    "thumbnail_path": None
                }
                
            # Run in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, self._process_image_sync, file_path)
            
        except Exception as e:
            return {
                "error": str(e),
                "dimensions": None,
                "format": None,
                "thumbnail_path": None
            }
            
    def _process_image_sync(self, file_path: str) -> Dict[str, Any]:
        """Synchronous image processing"""
        image = Image.open(file_path)
        
        # Generate thumbnail
        thumbnail = image.copy()
        thumbnail.thumbnail((200, 200), Image.Resampling.LANCZOS)
        
        # Save thumbnail
        file_stem = Path(file_path).stem
        thumbnail_path = self.storage_dir / "thumbnails" / f"{file_stem}_thumb.jpg"
        thumbnail.save(thumbnail_path, "JPEG")
        
        return {
            "dimensions": image.size,
            "format": image.format,
            "thumbnail_path": str(thumbnail_path),
            "file_size": os.path.getsize(file_path)
        }
        
    async def process_audio(self, file_path: str) -> Dict[str, Any]:
        """Process audio file and extract metadata"""
        try:
            if not LIBROSA_AVAILABLE:
                # Fallback to basic file info
                return {
                    "duration": None,
                    "sample_rate": None,
                    "channels": None,
                    "file_size": os.path.getsize(file_path),
                    "error": "librosa not available for detailed audio analysis"
                }
                
            # Run in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, self._process_audio_sync, file_path)
            
        except Exception as e:
            return {
                "error": str(e),
                "duration": None,
                "sample_rate": None,
                "channels": None,
                "file_size": os.path.getsize(file_path)
            }
            
    def _process_audio_sync(self, file_path: str) -> Dict[str, Any]:
        """Synchronous audio processing"""
        y, sr = librosa.load(file_path)
        duration = librosa.get_duration(y=y, sr=sr)
        
        return {
            "duration": duration,
            "sample_rate": sr,
            "channels": 1 if len(y.shape) == 1 else y.shape[0],
            "file_size": os.path.getsize(file_path)
        }
        
    async def process_video(self, file_path: str) -> Dict[str, Any]:
        """Process video file and extract metadata"""
        try:
            # Basic video metadata without ffmpeg dependency
            file_size = os.path.getsize(file_path)
            
            # Try to extract basic info using file extension
            file_ext = Path(file_path).suffix.lower()
            video_formats = {
                '.mp4': 'MP4',
                '.webm': 'WebM',
                '.mov': 'QuickTime',
                '.avi': 'AVI',
                '.mkv': 'Matroska'
            }
            
            format_name = video_formats.get(file_ext, 'Unknown')
            
            return {
                "format": format_name,
                "file_size": file_size,
                "duration": None,  # Would need ffmpeg for this
                "resolution": None,  # Would need ffmpeg for this
                "error": "Full video processing requires ffmpeg (not implemented)"
            }
            
        except Exception as e:
            return {
                "error": str(e),
                "format": None,
                "file_size": 0,
                "duration": None,
                "resolution": None
            }
            
    def get_media_url(self, media_file_path: str) -> str:
        """Get URL for serving media file"""
        relative_path = Path(media_file_path).relative_to(self.storage_dir)
        return f"/media/{relative_path}"
        
    def cleanup_old_files(self, max_age_hours: int = 24):
        """Clean up old uploaded files"""
        import time
        current_time = time.time()
        cutoff_time = current_time - (max_age_hours * 3600)
        
        for file_path in self.storage_dir.rglob("*"):
            if file_path.is_file() and file_path.stat().st_mtime < cutoff_time:
                try:
                    file_path.unlink()
                    print(f"Cleaned up old file: {file_path}")
                except Exception as e:
                    print(f"Error cleaning up {file_path}: {e}")
                    
    def get_supported_formats(self) -> Dict[str, list]:
        """Get list of supported file formats"""
        return {
            "images": [".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"],
            "audio": [".mp3", ".wav", ".m4a", ".ogg", ".flac"],
            "video": [".mp4", ".webm", ".mov", ".avi", ".mkv"]
        }