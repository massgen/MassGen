import React, { useState, useCallback } from 'react';
import { useDropzone } from 'react-dropzone';
import { MediaFile } from '../types.ts';

interface MultimediaInputProps {
  onTaskSubmit: (task: string) => void;
  onMediaUpload: (files: File[]) => void;
  mediaFiles: MediaFile[];
  disabled?: boolean;
}

export const MultimediaInput: React.FC<MultimediaInputProps> = ({
  onTaskSubmit,
  onMediaUpload,
  mediaFiles,
  disabled = false
}) => {
  const [taskText, setTaskText] = useState('');

  const onDrop = useCallback((acceptedFiles: File[]) => {
    onMediaUpload(acceptedFiles);
  }, [onMediaUpload]);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'image/*': ['.png', '.jpg', '.jpeg', '.gif', '.webp'],
      'audio/*': ['.mp3', '.wav', '.m4a', '.ogg'],
      'video/*': ['.mp4', '.webm', '.mov', '.avi']
    },
    disabled
  });

  const handleSubmit = () => {
    if (taskText.trim() && !disabled) {
      onTaskSubmit(taskText);
      setTaskText('');
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && e.ctrlKey) {
      handleSubmit();
    }
  };

  const getMediaIcon = (contentType: string) => {
    if (contentType.startsWith('image/')) return '🖼️';
    if (contentType.startsWith('audio/')) return '🎵';
    if (contentType.startsWith('video/')) return '🎬';
    return '📎';
  };

  const formatFileSize = (bytes: number) => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
  };

  return (
    <div className="multimedia-input p-4 space-y-4 h-full flex flex-col">
      {/* Task Input */}
      <div className="flex-1">
        <label className="block text-sm font-medium mb-2">Coordination Task</label>
        <textarea
          value={taskText}
          onChange={(e) => setTaskText(e.target.value)}
          onKeyPress={handleKeyPress}
          placeholder="Describe what you want the agents to work on...\n\nCtrl+Enter to submit"
          disabled={disabled}
          className="w-full h-32 bg-gray-800 border border-gray-600 rounded px-3 py-2 resize-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
        />
      </div>

      {/* File Upload Zone */}
      <div
        {...getRootProps()}
        className={`border-2 border-dashed rounded-lg p-4 text-center transition-colors cursor-pointer
          ${isDragActive 
            ? 'border-blue-500 bg-blue-500/10' 
            : disabled 
              ? 'border-gray-600 bg-gray-800/50 cursor-not-allowed'
              : 'border-gray-600 hover:border-gray-500 hover:bg-gray-800/30'
          }`}
      >
        <input {...getInputProps()} />
        <div className="space-y-2">
          <div className="text-2xl">📎</div>
          <p className="text-sm">
            {isDragActive 
              ? 'Drop files here...' 
              : 'Drag files here or click to browse'}
          </p>
          <p className="text-xs text-gray-500">
            Images, audio, video supported
          </p>
        </div>
      </div>

      {/* Uploaded Media Files */}
      {mediaFiles.length > 0 && (
        <div className="space-y-2">
          <label className="block text-sm font-medium">Uploaded Files ({mediaFiles.length})</label>
          <div className="space-y-1 max-h-32 overflow-y-auto scrollbar-hide">
            {mediaFiles.map((file) => (
              <div key={file.id} className="bg-gray-800 rounded p-2 text-sm">
                <div className="flex items-center space-x-2">
                  <span>{getMediaIcon(file.content_type)}</span>
                  <span className="flex-1 truncate" title={file.filename}>
                    {file.filename}
                  </span>
                </div>
                {file.metadata.file_size && (
                  <div className="text-xs text-gray-500 mt-1">
                    {formatFileSize(file.metadata.file_size)}
                    {file.metadata.dimensions && 
                      ` • ${file.metadata.dimensions[0]}×${file.metadata.dimensions[1]}`
                    }
                    {file.metadata.duration && 
                      ` • ${Math.round(file.metadata.duration)}s`
                    }
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Submit Button */}
      <button
        onClick={handleSubmit}
        disabled={!taskText.trim() || disabled}
        className="w-full bg-blue-600 hover:bg-blue-500 disabled:bg-gray-600 disabled:cursor-not-allowed px-4 py-3 rounded font-medium transition-colors"
      >
        🚀 Start Coordination
      </button>

      {/* Help Text */}
      <div className="text-xs text-gray-500 space-y-1">
        <p>💡 <strong>Tip:</strong> Upload media files to enhance coordination</p>
        <p>⌨️ <strong>Shortcut:</strong> Ctrl+Enter to submit task</p>
      </div>
    </div>
  );
};