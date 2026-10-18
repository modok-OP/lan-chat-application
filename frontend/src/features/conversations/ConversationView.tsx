import React, { useState, useEffect, useRef } from 'react';
import styles from './ConversationView.module.css';
import { api } from '../../lib/api';
import { GroupDetailsModal } from '../groups';
import { FileMessageCard, FileUploadProgress } from '../attachments';
import type {
  Conversation,
  Message,
  MessageCreatedPayload,
  TypingUpdatedPayload,
  MessageReactionUpdatedPayload,
} from '../../types';

interface ConversationViewProps {
  conversation: Conversation;
  currentUserId: number;
  onlineUsers?: Set<number>;
  lastMessage?: MessageCreatedPayload | null;
  lastTypingUpdate?: TypingUpdatedPayload | null;
  lastReactionUpdate?: MessageReactionUpdatedPayload | null;
  onSendMessage?: (
    conversationId: number,
    content: string,
    clientMessageId?: string,
    replyToMessageId?: number
  ) => Promise<unknown>;
  onSendTyping?: (conversationId: number, isTyping: boolean) => void;
  onConversationUpdated?: (updated: Conversation) => void;
  onLeaveGroup?: () => Promise<void>;
  onBack?: () => void;
}

export const ConversationView: React.FC<ConversationViewProps> = ({
  conversation,
  currentUserId,
  onlineUsers = new Set(),
  lastMessage = null,
  lastTypingUpdate = null,
  lastReactionUpdate = null,
  onSendMessage,
  onSendTyping,
  onConversationUpdated,
  onLeaveGroup,
  onBack,
}) => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [oldestId, setOldestId] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [inputContent, setInputContent] = useState('');
  const [sending, setSending] = useState(false);
  const [isDetailsOpen, setIsDetailsOpen] = useState(false);

  // Message search state
  const [isSearchOpen, setIsSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [searching, setSearching] = useState(false);
  const [serverMatchedIds, setServerMatchedIds] = useState<Set<number>>(new Set());

  // Real-time typing indicators state
  const [typingUsers, setTypingUsers] = useState<Map<number, string>>(new Map());
  const typingTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastTypingSentRef = useRef<number>(0);

  // File upload state
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploadError, setUploadError] = useState<string | null>(null);

  // Message reply and reaction state
  const [replyingToMessage, setReplyingToMessage] = useState<Message | null>(null);
  const [activeEmojiPickerMsgId, setActiveEmojiPickerMsgId] = useState<number | null>(null);
  const QUICK_EMOJIS = ['👍', '❤️', '😂', '😮', '😢', '🎉', '🔥', '👏'];

  const messageEndRef = useRef<HTMLDivElement>(null);

  const handleToggleReaction = async (messageId: number, emoji: string) => {
    setActiveEmojiPickerMsgId(null);
    try {
      const res = await api.toggleReaction(messageId, emoji);
      setMessages((prev) =>
        prev.map((m) =>
          m.id === messageId ? { ...m, reactions: res.reactions } : m
        )
      );
    } catch (err) {
      console.error('Failed to toggle reaction:', err);
    }
  };

  // Fetch initial message history on conversation change
  useEffect(() => {
    let isMounted = true;
    const fetchHistory = async () => {
      try {
        setLoading(true);
        const data = await api.getMessages(conversation.id);
        if (isMounted) {
          setMessages(data.messages);
          setHasMore(data.has_more);
          setOldestId(data.oldest_id || null);
        }
      } catch (err) {
        console.error('Failed to load message history:', err);
      } finally {
        if (isMounted) setLoading(false);
      }
    };

    fetchHistory();
    return () => {
      isMounted = false;
    };
  }, [conversation.id]);

  // Listen for real-time incoming messages
  useEffect(() => {
    if (!lastMessage) return;
    if (lastMessage.conversation_id !== conversation.id) return;

    setMessages((prev) => {
      // Check if message is already in list (by id or client_message_id)
      const existingIndex = prev.findIndex(
        (m) =>
          m.id === lastMessage.message_id ||
          (m.client_message_id &&
            lastMessage.client_message_id &&
            m.client_message_id === lastMessage.client_message_id)
      );

      const incomingMsg: Message = {
        id: lastMessage.message_id,
        conversation_id: lastMessage.conversation_id,
        sender_id: lastMessage.sender?.id ?? null,
        sender_username: lastMessage.sender?.username ?? null,
        sender_display_name: lastMessage.sender?.display_name ?? null,
        client_message_id: lastMessage.client_message_id,
        message_type: lastMessage.message_type,
        content: lastMessage.content,
        reply_to_message_id: lastMessage.reply_to_message_id,
        reply_to: lastMessage.reply_to || null,
        reactions: lastMessage.reactions || [],
        created_at: lastMessage.created_at,
        attachments: lastMessage.attachments || [],
      };

      if (existingIndex >= 0) {
        // Update existing optimistic message with server details
        const existing = prev[existingIndex];
        const updated = [...prev];
        updated[existingIndex] = {
          ...incomingMsg,
          reactions: (incomingMsg.reactions && incomingMsg.reactions.length > 0)
            ? incomingMsg.reactions
            : (existing.reactions || []),
        };
        return updated;
      }

      return [...prev, incomingMsg];
    });
  }, [lastMessage, conversation.id]);

  // Handle incoming reaction updates
  useEffect(() => {
    if (!lastReactionUpdate) return;
    if (lastReactionUpdate.conversation_id !== conversation.id) return;

    setMessages((prev) =>
      prev.map((m) =>
        m.id === lastReactionUpdate.message_id
          ? { ...m, reactions: lastReactionUpdate.reactions }
          : m
      )
    );
  }, [lastReactionUpdate, conversation.id]);

  // Scroll to bottom when new messages arrive
  useEffect(() => {
    if (!loadingMore) {
      messageEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, loadingMore]);

  // Debounced search query against backend API
  useEffect(() => {
    const clean = searchQuery.trim();
    if (!clean) {
      setServerMatchedIds(new Set());
      setSearching(false);
      return;
    }

    setSearching(true);
    const timer = setTimeout(async () => {
      try {
        const res = await api.searchMessages(conversation.id, clean);
        setServerMatchedIds(new Set(res.messages.map((m) => m.id)));
      } catch (err) {
        console.warn('Search query error:', err);
      } finally {
        setSearching(false);
      }
    }, 250);

    return () => clearTimeout(timer);
  }, [searchQuery, conversation.id]);

  const isMessageMatched = (msg: Message): boolean => {
    const clean = searchQuery.trim();
    if (!clean) return false;
    if (serverMatchedIds.has(msg.id)) return true;
    return msg.content.toLowerCase().includes(clean.toLowerCase());
  };

  const highlightText = (text: string, query: string) => {
    const clean = query.trim();
    if (!clean) return text;
    try {
      const parts = text.split(
        new RegExp(`(${clean.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi')
      );
      return parts.map((part, i) =>
        part.toLowerCase() === clean.toLowerCase() ? (
          <mark key={i} className={styles.highlightMark}>
            {part}
          </mark>
        ) : (
          part
        )
      );
    } catch {
      return text;
    }
  };

  // Handle incoming typing updates from other conversation members
  useEffect(() => {
    if (!lastTypingUpdate) return;
    if (lastTypingUpdate.conversation_id !== conversation.id) return;
    if (lastTypingUpdate.user_id === currentUserId) return;

    setTypingUsers((prev) => {
      const next = new Map(prev);
      if (lastTypingUpdate.is_typing) {
        next.set(
          lastTypingUpdate.user_id,
          lastTypingUpdate.display_name || lastTypingUpdate.username
        );
      } else {
        next.delete(lastTypingUpdate.user_id);
      }
      return next;
    });
  }, [lastTypingUpdate, conversation.id, currentUserId]);

  // Auto-clear typing users after 4.5 seconds of silence
  useEffect(() => {
    if (typingUsers.size === 0) return;
    const timer = setTimeout(() => {
      setTypingUsers(new Map());
    }, 4500);
    return () => clearTimeout(timer);
  }, [typingUsers]);

  // Clean up typing state on conversation change
  useEffect(() => {
    setTypingUsers(new Map());
  }, [conversation.id]);

  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const val = e.target.value;
    setInputContent(val);

    if (!onSendTyping) return;

    const now = Date.now();
    if (val.trim()) {
      if (now - lastTypingSentRef.current > 2000) {
        lastTypingSentRef.current = now;
        onSendTyping(conversation.id, true);
      }
      if (typingTimeoutRef.current) {
        clearTimeout(typingTimeoutRef.current);
      }
      typingTimeoutRef.current = setTimeout(() => {
        onSendTyping(conversation.id, false);
      }, 2500);
    } else {
      if (typingTimeoutRef.current) {
        clearTimeout(typingTimeoutRef.current);
      }
      onSendTyping(conversation.id, false);
    }
  };

  const renderReadReceipt = (messageId: number) => {
    if (isGroup) {
      const otherMembers = conversation.members.filter(
        (m) => m.user_id !== currentUserId && m.is_active
      );
      if (otherMembers.length === 0) {
        return <span className={styles.sentCheckmark} title="Sent">✓</span>;
      }
      const readCount = otherMembers.filter(
        (m) => m.last_read_message_id && m.last_read_message_id >= messageId
      ).length;

      if (readCount === 0) {
        return <span className={styles.sentCheckmark} title="Sent">✓</span>;
      }
      if (readCount >= otherMembers.length) {
        return (
          <span className={styles.readCheckmarks} title="Read by all group members">
            ✓✓
          </span>
        );
      }
      return (
        <span
          className={styles.readCheckmarks}
          title={`Read by ${readCount} of ${otherMembers.length} members`}
        >
          ✓✓ <span className={styles.readCount}>{readCount}</span>
        </span>
      );
    } else {
      const otherMember = conversation.members.find((m) => m.user_id !== currentUserId);
      const isRead =
        otherMember?.last_read_message_id &&
        otherMember.last_read_message_id >= messageId;

      if (isRead) {
        return (
          <span
            className={styles.readCheckmarks}
            title={`Read by ${otherMember?.display_name || 'recipient'}`}
          >
            ✓✓
          </span>
        );
      }
      return <span className={styles.sentCheckmark} title="Sent">✓</span>;
    }
  };

  const renderTypingIndicator = () => {
    if (typingUsers.size === 0) return null;
    const names = Array.from(typingUsers.values());
    let text = '';
    if (names.length === 1) {
      text = `${names[0]} is typing...`;
    } else if (names.length === 2) {
      text = `${names[0]} and ${names[1]} are typing...`;
    } else {
      text = 'Several people are typing...';
    }

    return (
      <div className={styles.typingIndicator}>
        <span className={styles.typingDots}>
          <span className={styles.typingDot} />
          <span className={styles.typingDot} />
          <span className={styles.typingDot} />
        </span>
        <span>{text}</span>
      </div>
    );
  };

  const handleLoadMore = async () => {
    if (!oldestId || loadingMore) return;
    try {
      setLoadingMore(true);
      const data = await api.getMessages(conversation.id, oldestId);
      setMessages((prev) => [...data.messages, ...prev]);
      setHasMore(data.has_more);
      setOldestId(data.oldest_id || null);
    } catch (err) {
      console.error('Failed to load older messages:', err);
    } finally {
      setLoadingMore(false);
    }
  };

  const handleSendMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    const clean = inputContent.trim();
    if (!clean || sending) return;

    if (typingTimeoutRef.current) {
      clearTimeout(typingTimeoutRef.current);
    }
    if (onSendTyping) {
      onSendTyping(conversation.id, false);
    }

    const replyId = replyingToMessage?.id;
    setReplyingToMessage(null);

    const clientMsgId = `c-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
    setInputContent('');
    setSending(true);

    try {
      if (onSendMessage) {
        // Real-time send via WebSocket
        await onSendMessage(conversation.id, clean, clientMsgId, replyId);
      } else {
        // HTTP fallback
        const newMsg = await api.postMessage(conversation.id, clean, clientMsgId, replyId);
        setMessages((prev) => {
          if (prev.some((m) => m.id === newMsg.id || m.client_message_id === newMsg.client_message_id)) {
            return prev;
          }
          return [...prev, newMsg];
        });
      }
    } catch (wsErr) {
      console.warn('WebSocket send failed, attempting HTTP fallback:', wsErr);
      try {
        const newMsg = await api.postMessage(conversation.id, clean, clientMsgId, replyId);
        setMessages((prev) => {
          if (prev.some((m) => m.id === newMsg.id || m.client_message_id === newMsg.client_message_id)) {
            return prev;
          }
          return [...prev, newMsg];
        });
      } catch (httpErr) {
        console.error('Failed to send message via fallback:', httpErr);
      }
    } finally {
      setSending(false);
    }
  };

  const handleFileSelected = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setSelectedFile(file);
    setUploadError(null);
    setUploadProgress(0);

    // Client-side guard for 25 MB limit
    if (file.size > 25 * 1024 * 1024) {
      setUploadError('File size exceeds the maximum limit (25 MB).');
      return;
    }

    if (file.size === 0) {
      setUploadError('Cannot upload an empty file.');
      return;
    }

    try {
      setUploading(true);
      const clientMsgId = `c-file-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
      const newMsg = await api.uploadAttachment(
        conversation.id,
        file,
        clientMsgId,
        (percent) => {
          setUploadProgress(percent);
        }
      );

      // Add to messages if not already arrived via WebSocket
      setMessages((prev) => {
        if (
          prev.some(
            (m) =>
              m.id === newMsg.id ||
              (m.client_message_id && m.client_message_id === newMsg.client_message_id)
          )
        ) {
          return prev;
        }
        return [...prev, newMsg];
      });

      // Reset file selection on success
      setSelectedFile(null);
      setUploadProgress(0);
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'File upload failed';
      setUploadError(msg);
    } finally {
      setUploading(false);
    }
  };

  const handleCancelUpload = () => {
    setSelectedFile(null);
    setUploading(false);
    setUploadProgress(0);
    setUploadError(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const isGroup = conversation.type === 'group';
  const otherMember = !isGroup
    ? conversation.members.find((m) => m.user_id !== currentUserId)
    : null;
  const isOtherOnline = otherMember ? onlineUsers.has(otherMember.user_id) : false;

  const onlineGroupCount = isGroup
    ? conversation.members.filter((m) => onlineUsers.has(m.user_id)).length
    : 0;

  const getTitle = () => {
    if (isGroup) {
      return conversation.name || 'Group Chat';
    }
    return otherMember ? otherMember.display_name : 'Direct Chat';
  };

  const renderSubtitle = () => {
    if (isGroup) {
      return (
        <span className={styles.subtitle}>
          {conversation.members.length} members
          {onlineGroupCount > 0 && ` (${onlineGroupCount} online)`}
        </span>
      );
    }

    if (!otherMember) return null;

    return (
      <span className={styles.subtitle}>
        <span>@{otherMember.username}</span>
        {isOtherOnline ? (
          <span className={styles.statusOnline}>
            <span className={styles.onlineDot} /> Online
          </span>
        ) : (
          <span className={styles.statusOffline}>
            <span className={styles.offlineDot} /> Offline
          </span>
        )}
      </span>
    );
  };

  const currentMember = conversation.members.find((m) => m.user_id === currentUserId);
  const isCurrentMemberActive = currentMember ? currentMember.is_active : false;

  return (
    <div className={styles.container}>
      <header className={styles.header}>
        <div className={styles.headerLeft}>
          {onBack && (
            <button
              type="button"
              className={styles.backBtn}
              onClick={onBack}
              title="Back to conversation list"
            >
              ← Back
            </button>
          )}
          <div className={styles.headerInfo}>
            <h2 className={styles.title}>{getTitle()}</h2>
            {renderSubtitle()}
          </div>
        </div>
        <div className={styles.headerActions}>
          <button
            className={`${styles.headerActionBtn} ${
              isSearchOpen ? styles.headerActionBtnActive : ''
            }`}
            onClick={() => {
              setIsSearchOpen((prev) => !prev);
              if (isSearchOpen) setSearchQuery('');
            }}
            title="Search messages in this conversation"
          >
            🔍 Search
          </button>
          {isGroup && (
            <button
              className={styles.detailsBtn}
              onClick={() => setIsDetailsOpen(true)}
              title="View group members and settings"
            >
              👥 Group Details
            </button>
          )}
        </div>
      </header>

      {isSearchOpen && (
        <div className={styles.searchBar}>
          <div className={styles.searchInputWrapper}>
            <span className={styles.searchIcon}>🔍</span>
            <input
              type="text"
              className={styles.searchInput}
              placeholder="Search messages in this conversation..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              autoFocus
            />
            {searchQuery && (
              <button
                className={styles.searchClearBtn}
                onClick={() => setSearchQuery('')}
                title="Clear search"
              >
                ✕
              </button>
            )}
          </div>
          <div className={styles.searchMeta}>
            {searching ? (
              <span className={styles.searchingText}>Searching...</span>
            ) : searchQuery.trim() ? (
              <span className={styles.searchCountText}>
                {messages.filter((m) => isMessageMatched(m)).length === 0
                  ? 'No matches'
                  : `${messages.filter((m) => isMessageMatched(m)).length} match${
                      messages.filter((m) => isMessageMatched(m)).length === 1 ? '' : 'es'
                    }`}
              </span>
            ) : null}
            <button
              className={styles.searchCloseBtn}
              onClick={() => {
                setIsSearchOpen(false);
                setSearchQuery('');
              }}
              title="Close search"
            >
              Done
            </button>
          </div>
        </div>
      )}

      <div className={styles.messageArea}>
        {hasMore && (
          <button
            className={styles.loadMoreBtn}
            onClick={handleLoadMore}
            disabled={loadingMore}
          >
            {loadingMore ? 'Loading older messages...' : '↑ Load earlier messages'}
          </button>
        )}

        {loading && messages.length === 0 && (
          <div className={styles.emptyState}>Loading conversation history...</div>
        )}

        {!loading && messages.length === 0 && (
          <div className={styles.emptyState}>
            No messages yet in this conversation.<br />
            Send a message below to start chatting!
          </div>
        )}

        {isSearchOpen && searchQuery.trim() && messages.filter((m) => isMessageMatched(m)).length === 0 && (
          <div className={styles.noSearchMatchState}>
            No messages matching &ldquo;<strong>{searchQuery}</strong>&rdquo; found in this conversation.
          </div>
        )}

        {messages.map((msg) => {
          if (msg.message_type === 'system') {
            return (
              <div key={msg.id} className={styles.systemMessageRow}>
                <div className={styles.systemBubble}>
                  <span>{msg.content}</span>
                  <span className={styles.systemTime}>
                    {new Date(msg.created_at).toLocaleTimeString([], {
                      hour: '2-digit',
                      minute: '2-digit',
                    })}
                  </span>
                </div>
              </div>
            );
          }

          const isSentByMe = msg.sender_id === currentUserId;

          return (
            <div
              key={msg.id}
              id={`msg-${msg.id}`}
              className={`${styles.messageRow} ${
                isSentByMe ? styles.messageSent : styles.messageReceived
              }`}
            >
              {!isSentByMe && (
                <span className={styles.senderName}>
                  {msg.sender_display_name || msg.sender_username || 'User'}
                </span>
              )}

              {/* Action Toolbar on hover */}
              <div className={styles.messageToolbar}>
                <button
                  type="button"
                  className={styles.messageActionBtn}
                  onClick={() =>
                    setActiveEmojiPickerMsgId(
                      activeEmojiPickerMsgId === msg.id ? null : msg.id
                    )
                  }
                  title="Add reaction"
                >
                  😀
                </button>
                <button
                  type="button"
                  className={styles.messageActionBtn}
                  onClick={() => setReplyingToMessage(msg)}
                  title="Reply"
                >
                  ↩️
                </button>
              </div>

              {/* Emoji Picker Popover */}
              {activeEmojiPickerMsgId === msg.id && (
                <div className={styles.emojiPicker}>
                  {QUICK_EMOJIS.map((emoji) => (
                    <button
                      key={emoji}
                      type="button"
                      className={styles.emojiPickerBtn}
                      onClick={() => handleToggleReaction(msg.id, emoji)}
                      title={`React ${emoji}`}
                    >
                      {emoji}
                    </button>
                  ))}
                </div>
              )}

              {msg.message_type === 'file' ? (
                <div>
                  {msg.reply_to && (
                    <div
                      className={styles.replyQuote}
                      onClick={() => {
                        const target = document.getElementById(`msg-${msg.reply_to?.id}`);
                        if (target) {
                          target.scrollIntoView({ behavior: 'smooth', block: 'center' });
                          target.classList.add(styles.highlightFlash);
                          setTimeout(() => target.classList.remove(styles.highlightFlash), 1500);
                        }
                      }}
                      title="Jump to quoted message"
                    >
                      <div className={styles.replyQuoteAuthor}>
                        ↩️ {msg.reply_to.sender_display_name || msg.reply_to.sender_username || 'User'}
                      </div>
                      <div className={styles.replyQuoteSnippet}>
                        {msg.reply_to.content}
                      </div>
                    </div>
                  )}
                  <FileMessageCard message={msg} currentUserId={currentUserId} />
                </div>
              ) : (
                <div
                  className={`${styles.bubble} ${
                    isSentByMe ? styles.bubbleSent : styles.bubbleReceived
                  } ${isMessageMatched(msg) ? styles.bubbleMatched : ''}`}
                >
                  {msg.reply_to && (
                    <div
                      className={styles.replyQuote}
                      onClick={() => {
                        const target = document.getElementById(`msg-${msg.reply_to?.id}`);
                        if (target) {
                          target.scrollIntoView({ behavior: 'smooth', block: 'center' });
                          target.classList.add(styles.highlightFlash);
                          setTimeout(() => target.classList.remove(styles.highlightFlash), 1500);
                        }
                      }}
                      title="Jump to quoted message"
                    >
                      <div className={styles.replyQuoteAuthor}>
                        ↩️ {msg.reply_to.sender_display_name || msg.reply_to.sender_username || 'User'}
                      </div>
                      <div className={styles.replyQuoteSnippet}>
                        {msg.reply_to.content}
                      </div>
                    </div>
                  )}
                  {highlightText(msg.content, searchQuery)}
                  <div
                    className={`${styles.metaRow} ${
                      isSentByMe ? styles.metaSent : styles.metaReceived
                    }`}
                  >
                    <span>
                      {new Date(msg.created_at).toLocaleTimeString([], {
                        hour: '2-digit',
                        minute: '2-digit',
                      })}
                    </span>
                    {isSentByMe && (
                      <span className={styles.readStatus}>
                        {renderReadReceipt(msg.id)}
                      </span>
                    )}
                  </div>
                </div>
              )}

              {/* Reaction chips */}
              {msg.reactions && msg.reactions.length > 0 && (
                <div className={styles.reactionsRow}>
                  {msg.reactions.map((rx) => {
                    const hasReacted = rx.user_ids.includes(currentUserId);
                    return (
                      <button
                        key={rx.emoji}
                        type="button"
                        className={`${styles.reactionChip} ${
                          hasReacted ? styles.reactionChipActive : ''
                        }`}
                        onClick={() => handleToggleReaction(msg.id, rx.emoji)}
                        title={`Reacted by: ${rx.usernames.join(', ')}`}
                      >
                        <span className={styles.reactionEmoji}>{rx.emoji}</span>
                        <span className={styles.reactionCount}>{rx.count}</span>
                      </button>
                    );
                  })}
                  <button
                    type="button"
                    className={styles.addReactionBtn}
                    onClick={() =>
                      setActiveEmojiPickerMsgId(
                        activeEmojiPickerMsgId === msg.id ? null : msg.id
                      )
                    }
                    title="Add reaction"
                  >
                    +
                  </button>
                </div>
              )}
            </div>
          );
        })}

        <div ref={messageEndRef} />
      </div>

      {renderTypingIndicator()}

      {isCurrentMemberActive ? (
        <div className={styles.composerWrapper}>
          {replyingToMessage && (
            <div className={styles.replyingBanner}>
              <div className={styles.replyingInfo}>
                <span className={styles.replyingIcon}>↩️</span>
                <div className={styles.replyingText}>
                  <span className={styles.replyingAuthor}>
                    Replying to {replyingToMessage.sender_display_name || replyingToMessage.sender_username || 'User'}
                  </span>
                  <span className={styles.replyingSnippet}>
                    {replyingToMessage.content.length > 80
                      ? `${replyingToMessage.content.slice(0, 80)}...`
                      : replyingToMessage.content}
                  </span>
                </div>
              </div>
              <button
                type="button"
                className={styles.replyingCloseBtn}
                onClick={() => setReplyingToMessage(null)}
                title="Cancel reply"
              >
                ✕
              </button>
            </div>
          )}
          {selectedFile && (
            <FileUploadProgress
              filename={selectedFile.name}
              filesize={selectedFile.size}
              progress={uploadProgress}
              uploading={uploading}
              error={uploadError}
              onCancel={handleCancelUpload}
            />
          )}
          <form className={styles.composer} onSubmit={handleSendMessage}>
            <input
              type="file"
              ref={fileInputRef}
              style={{ display: 'none' }}
              onChange={handleFileSelected}
              disabled={sending || uploading}
            />
            <button
              type="button"
              className={styles.attachBtn}
              onClick={() => fileInputRef.current?.click()}
              title="Attach a file (max 25 MB)"
              disabled={sending || uploading}
            >
              📎
            </button>
            <textarea
              className={styles.input}
              placeholder="Type a message... (Press Enter to send, Shift+Enter for newline)"
              value={inputContent}
              onChange={handleInputChange}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  handleSendMessage(e);
                }
              }}
              rows={1}
              disabled={sending || uploading}
            />
            <button
              type="submit"
              className={styles.sendBtn}
              disabled={sending || uploading || !inputContent.trim()}
            >
              {sending ? 'Sending...' : 'Send'}
            </button>
          </form>
        </div>
      ) : (
        <div className={styles.inactiveBanner}>
          You are no longer an active member of this conversation.
        </div>
      )}

      {isGroup && isDetailsOpen && (
        <GroupDetailsModal
          isOpen={isDetailsOpen}
          onClose={() => setIsDetailsOpen(false)}
          conversation={conversation}
          currentUserId={currentUserId}
          onlineUsers={onlineUsers}
          onConversationUpdated={(updated) => {
            if (onConversationUpdated) onConversationUpdated(updated);
          }}
          onLeaveGroup={async () => {
            if (onLeaveGroup) await onLeaveGroup();
          }}
        />
      )}
    </div>
  );
};
