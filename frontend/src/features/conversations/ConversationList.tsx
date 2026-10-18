import React, { useState } from 'react';
import styles from './ConversationList.module.css';
import type { Conversation } from '../../types';

interface ConversationListProps {
  conversations: Conversation[];
  activeId: number | null;
  currentUserId: number;
  onlineUsers?: Set<number>;
  onSelect: (id: number) => void;
  onOpenNewDialog: () => void;
  loading: boolean;
}

export const ConversationList: React.FC<ConversationListProps> = ({
  conversations,
  activeId,
  currentUserId,
  onlineUsers = new Set(),
  onSelect,
  onOpenNewDialog,
  loading,
}) => {
  const [filterText, setFilterText] = useState('');

  const getDisplayName = (conv: Conversation): string => {
    if (conv.type === 'group') {
      return conv.name || 'Group Chat';
    }
    const otherMember = conv.members.find((m) => m.user_id !== currentUserId);
    return otherMember ? otherMember.display_name : 'Direct Chat';
  };

  const getInitials = (name: string): string => {
    return name.slice(0, 2).toUpperCase();
  };

  const filteredConversations = conversations.filter((c) => {
    if (!filterText.trim()) return true;
    const name = getDisplayName(c).toLowerCase();
    return name.includes(filterText.toLowerCase().trim());
  });

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <div className={styles.headerTitleRow}>
          <h2 className={styles.title}>Chats</h2>
          {conversations.length > 0 && (
            <span className={styles.countBadge}>{conversations.length}</span>
          )}
        </div>
        <button className={styles.newBtn} onClick={onOpenNewDialog} title="Start new direct or group chat">
          <span className={styles.newBtnPlus}>+</span> New Chat
        </button>
      </div>

      {conversations.length > 3 && (
        <div className={styles.filterWrapper}>
          <span className={styles.filterIcon}>🔍</span>
          <input
            type="text"
            className={styles.filterInput}
            placeholder="Filter conversations..."
            value={filterText}
            onChange={(e) => setFilterText(e.target.value)}
          />
          {filterText && (
            <button
              className={styles.filterClearBtn}
              onClick={() => setFilterText('')}
              title="Clear filter"
            >
              ✕
            </button>
          )}
        </div>
      )}

      <ul className={styles.list}>
        {loading && conversations.length === 0 && (
          <li className={styles.emptyState}>Loading conversations...</li>
        )}

        {!loading && conversations.length === 0 && (
          <li className={styles.emptyState}>
            <div className={styles.emptyIcon}>💬</div>
            <div className={styles.emptyTitle}>No conversations yet</div>
            <div className={styles.emptyDesc}>Click <strong>+ New Chat</strong> to begin messaging.</div>
          </li>
        )}

        {!loading && conversations.length > 0 && filteredConversations.length === 0 && (
          <li className={styles.emptyState}>
            No chats matching &ldquo;{filterText}&rdquo;
          </li>
        )}

        {filteredConversations.map((conv) => {
          const title = getDisplayName(conv);
          const isGroup = conv.type === 'group';
          const otherMember = !isGroup
            ? conv.members.find((m) => m.user_id !== currentUserId)
            : null;
          const isOtherOnline = otherMember ? onlineUsers.has(otherMember.user_id) : false;
          const isActive = conv.id === activeId;

          return (
            <li
              key={conv.id}
              className={`${styles.item} ${isActive ? styles.itemActive : ''}`}
              onClick={() => onSelect(conv.id)}
            >
              <div className={styles.avatarWrapper}>
                <div className={`${styles.avatar} ${isGroup ? styles.avatarGroup : ''}`}>
                  {isGroup ? (
                    <span className={styles.groupIcon}>👥</span>
                  ) : (
                    getInitials(title)
                  )}
                </div>
                {!isGroup && isOtherOnline && (
                  <span className={styles.onlineBadge} title="Online" />
                )}
              </div>
              <div className={styles.convInfo}>
                <div className={styles.convHeaderRow}>
                  <div className={styles.convName}>{title}</div>
                  {conv.unread_count && conv.unread_count > 0 ? (
                    <span className={styles.unreadBadge}>
                      {conv.unread_count > 99 ? '99+' : conv.unread_count}
                    </span>
                  ) : null}
                </div>
                <div className={styles.convMeta}>
                  {isGroup
                    ? `${conv.members.length} members`
                    : `@${otherMember?.username || ''}`}
                </div>
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
};
