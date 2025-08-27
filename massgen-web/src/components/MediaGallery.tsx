import React from 'react';
import { MediaFile } from '../types.ts';

interface MediaGalleryProps {
  files: MediaFile[];
  onMediaClick?: (file: MediaFile) => void;
}

export const MediaGallery: React.FC<MediaGalleryProps> = ({ 
  files, 
  onMediaClick 
}) => {
  const getMediaIcon = (contentType: string) => {
    if (contentType.startsWith('image/')) return '🖼️';
    if (contentType.startsWith('audio/')) return '🎵';
    if (contentType.startsWith('video/')) return '🎬';
    return '📎';
  };

  if (files.length === 0) {
    return (
      <div className="text-center text-gray-500 py-4">
        No media files attached
      </div>
    );
  }

  return (
    <div className="grid grid-cols-4 gap-2">
      {files.map((file) => (
        <div
          key={file.id}
          className="bg-gray-700 rounded p-2 text-center cursor-pointer hover:bg-gray-600"
          onClick={() => onMediaClick?.(file)}
          title={file.filename}
        >
          <div className="text-2xl mb-1">
            {getMediaIcon(file.content_type)}
          </div>
          <div className="text-xs text-gray-300 truncate">
            {file.filename}
          </div>
        </div>
      ))}
    </div>
  );
};