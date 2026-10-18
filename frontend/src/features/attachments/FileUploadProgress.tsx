import React from 'react';
import styles from './FileUploadProgress.module.css';
import { formatBytes, getFileIcon } from '../../lib/api';

interface FileUploadProgressProps {
  filename: string;
  filesize: number;
  progress: number;
  uploading: boolean;
  error?: string | null;
  onCancel?: () => void;
}

export const FileUploadProgress: React.FC<FileUploadProgressProps> = ({
  filename,
  filesize,
  progress,
  uploading,
  error,
  onCancel,
}) => {
  const icon = getFileIcon(filename);

  return (
    <div className={styles.container} data-testid="upload-progress-container">
      <div className={styles.topRow}>
        <div className={styles.fileMeta}>
          <span className={styles.fileIcon}>{icon}</span>
          <span className={styles.name} title={filename}>
            {filename}
          </span>
          <span className={styles.size}>({formatBytes(filesize)})</span>
        </div>

        {uploading ? (
          <span className={styles.statusText}>Uploading {progress}%...</span>
        ) : error ? (
          <span className={styles.errorText}>Upload failed</span>
        ) : (
          <span className={styles.statusText}>Ready</span>
        )}

        {onCancel && (
          <button
            type="button"
            className={styles.cancelBtn}
            onClick={onCancel}
            title="Cancel upload"
          >
            ✕
          </button>
        )}
      </div>

      <div className={styles.progressBarTrack}>
        <div
          className={`${styles.progressBarFill} ${
            error
              ? styles.progressFillError
              : progress >= 100
              ? styles.progressFillSuccess
              : ''
          }`}
          style={{ width: `${error ? 100 : progress}%` }}
        />
      </div>

      {error && <div className={styles.errorText}>{error}</div>}
    </div>
  );
};
