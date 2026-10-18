import { useState, useEffect, useCallback } from 'react';
import { wsClient } from '../lib/websocket';
import type {
  User,
  WebSocketStatus,
  MessageCreatedPayload,
  MessageAckPayload,
  MessageReadUpdatedPayload,
  TypingUpdatedPayload,
  MessageReactionUpdatedPayload,
} from '../types';

export function useWebSocket(user: User | null) {
  const [status, setStatus] = useState<WebSocketStatus>(wsClient.getStatus());
  const [onlineUsers, setOnlineUsers] = useState<Set<number>>(wsClient.getOnlineUsers());
  const [lastMessage, setLastMessage] = useState<MessageCreatedPayload | null>(null);
  const [lastConversationUpdate, setLastConversationUpdate] = useState<{ conversation_id: number } | null>(null);
  const [lastReadUpdate, setLastReadUpdate] = useState<MessageReadUpdatedPayload | null>(null);
  const [lastTypingUpdate, setLastTypingUpdate] = useState<TypingUpdatedPayload | null>(null);
  const [lastReactionUpdate, setLastReactionUpdate] = useState<MessageReactionUpdatedPayload | null>(null);

  useEffect(() => {
    if (!user) {
      wsClient.disconnect();
      setStatus('disconnected');
      setOnlineUsers(new Set());
      setLastMessage(null);
      setLastConversationUpdate(null);
      setLastReadUpdate(null);
      setLastTypingUpdate(null);
      setLastReactionUpdate(null);
      return;
    }

    // Connect to WebSocket endpoint
    wsClient.connect();

    const unsubStatus = wsClient.onStatusChange((newStatus) => {
      setStatus(newStatus);
    });

    const unsubPresence = wsClient.onPresence((users) => {
      setOnlineUsers(users);
    });

    const unsubMessage = wsClient.onMessageCreated((msg) => {
      setLastMessage(msg);
    });

    const unsubConv = wsClient.onConversationUpdated((update) => {
      setLastConversationUpdate(update);
    });

    const unsubRead = wsClient.onMessageRead((read) => {
      setLastReadUpdate(read);
    });

    const unsubTyping = wsClient.onTyping((typing) => {
      setLastTypingUpdate(typing);
    });

    const unsubReaction = wsClient.onReactionUpdated((reaction) => {
      setLastReactionUpdate(reaction);
    });

    return () => {
      unsubStatus();
      unsubPresence();
      unsubMessage();
      unsubConv();
      unsubRead();
      unsubTyping();
      unsubReaction();
    };
  }, [user]);

  const sendMessage = useCallback(
    async (
      conversationId: number,
      content: string,
      clientMessageId?: string,
      replyToMessageId?: number
    ): Promise<MessageAckPayload> => {
      return wsClient.sendMessage(conversationId, content, clientMessageId, replyToMessageId);
    },
    []
  );

  const sendMarkRead = useCallback((conversationId: number, lastReadMessageId?: number) => {
    wsClient.sendMarkRead(conversationId, lastReadMessageId);
  }, []);

  const sendTyping = useCallback((conversationId: number, isTyping: boolean) => {
    wsClient.sendTyping(conversationId, isTyping);
  }, []);

  const toggleReaction = useCallback((messageId: number, emoji: string) => {
    wsClient.toggleReaction(messageId, emoji);
  }, []);

  const reconnect = useCallback(() => {
    wsClient.connect();
  }, []);

  return {
    status,
    onlineUsers,
    lastMessage,
    lastConversationUpdate,
    lastReadUpdate,
    lastTypingUpdate,
    lastReactionUpdate,
    sendMessage,
    sendMarkRead,
    sendTyping,
    toggleReaction,
    reconnect,
    isOnline: useCallback((userId: number) => onlineUsers.has(userId), [onlineUsers]),
  };
}
