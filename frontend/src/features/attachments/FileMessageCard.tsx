import React from 'react';
import styles from './FileMessageCard.module.css';
import { formatBytes, getFileIcon } from '../../lib/api';
import type { Message, Attachment } from '../../types';

interface FileMessageCardProps {
  message: Message;
  currentUserId: number;
}

export const FileMessageCard: React.FC<FileMessageCardProps> = ({ message, currentUserId }) => {
  const attachment: Attachment | undefined =
    message.attachments && message.attachments.length > 0
      ? message.attachments[0]
      : undefined;

  const filename = attachment?.original_filename || message.content;
  const isSentByMe = message.sender_id === currentUserId;
  const icon = getFileIcon(filename);

  const downloadUrl = attachment?.download_url || (attachment?.id ? `/api/attachments/${attachment.id}/download` : '#');
  const shortSha = attachment?.sha256 ? `${attachment.sha256.substring(0, 8)}...` : null;

  return (
    <div
      className={`${styles.card} ${isSentByMe ? styles.fileSent : styles.fileReceived}`}
      data-testid="file-message-card"
    >
      <div className={styles.mainRow}>
        <div className={styles.iconWrapper}>{icon}</div>
        <div className={styles.infoCol}>
          <span className={styles.filename} title={filename}>
            {filename}
          </span>
          <span className={styles.sizeText}>
            {attachment ? formatBytes(attachment.size_bytes) : 'File attachment'}
          </span>
        </div>
      </div>

      <div className={styles.actionRow}>
        {shortSha ? (
          <span
            className={styles.hashBadge}
            title={`SHA-256 Checksum: ${attachment?.sha256}`}
          >
            SHA: {shortSha}
          </span>
        ) : (
          <span />
        )}

        <a
          href={downloadUrl}
          download={filename}
          className={styles.downloadLink}
          title={`Download ${filename}`}
          target="_blank"
          rel="noopener noreferrer"
        >
          <span>⬇️</span> Download
        </a>
      </div>
    </div>
  );
};
