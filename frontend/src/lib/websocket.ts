import type {
  WebSocketStatus,
  WebSocketEnvelope,
  PresenceSnapshotPayload,
  PresenceChangedPayload,
  MessageAckPayload,
  MessageCreatedPayload,
  MessageReadUpdatedPayload,
  TypingUpdatedPayload,
  MessageReactionUpdatedPayload,
} from '../types';

export function getWebSocketUrl(): string {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${protocol}//${window.location.host}/ws`;
}

type StatusListener = (status: WebSocketStatus) => void;
type MessageCreatedListener = (message: MessageCreatedPayload) => void;
type PresenceListener = (onlineUsers: Set<number>) => void;
type ErrorListener = (error: { code: string; message: string; details?: unknown }) => void;
type ConversationUpdatedListener = (payload: { conversation_id: number }) => void;
type MessageReadListener = (payload: MessageReadUpdatedPayload) => void;
type TypingListener = (payload: TypingUpdatedPayload) => void;
type MessageReactionListener = (payload: MessageReactionUpdatedPayload) => void;

interface PendingRequest {
  resolve: (ack: MessageAckPayload) => void;
  reject: (err: Error) => void;
  timer: ReturnType<typeof setTimeout>;
}

export class LANWebSocketClient {
  private ws: WebSocket | null = null;
  private url: string;
  private status: WebSocketStatus = 'disconnected';
  private manualClose = false;
  private reconnectAttempt = 0;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private heartbeatTimer: ReturnType<typeof setInterval> | null = null;

  private onlineUsers = new Set<number>();
  private pendingRequests = new Map<string, PendingRequest>();

  private statusListeners = new Set<StatusListener>();
  private messageListeners = new Set<MessageCreatedListener>();
  private presenceListeners = new Set<PresenceListener>();
  private errorListeners = new Set<ErrorListener>();
  private conversationListeners = new Set<ConversationUpdatedListener>();
  private readListeners = new Set<MessageReadListener>();
  private typingListeners = new Set<TypingListener>();
  private reactionListeners = new Set<MessageReactionListener>();

  constructor(url?: string) {
    this.url = url || (typeof window !== 'undefined' ? getWebSocketUrl() : 'ws://localhost:8000/ws');
  }

  public getStatus(): WebSocketStatus {
    return this.status;
  }

  public getOnlineUsers(): Set<number> {
    return new Set(this.onlineUsers);
  }

  public onStatusChange(listener: StatusListener): () => void {
    this.statusListeners.add(listener);
    listener(this.status);
    return () => this.statusListeners.delete(listener);
  }

  public onMessageCreated(listener: MessageCreatedListener): () => void {
    this.messageListeners.add(listener);
    return () => this.messageListeners.delete(listener);
  }

  public onPresence(listener: PresenceListener): () => void {
    this.presenceListeners.add(listener);
    listener(new Set(this.onlineUsers));
    return () => this.presenceListeners.delete(listener);
  }

  public onError(listener: ErrorListener): () => void {
    this.errorListeners.add(listener);
    return () => this.errorListeners.delete(listener);
  }

  public onConversationUpdated(listener: ConversationUpdatedListener): () => void {
    this.conversationListeners.add(listener);
    return () => this.conversationListeners.delete(listener);
  }

  public onMessageRead(listener: MessageReadListener): () => void {
    this.readListeners.add(listener);
    return () => this.readListeners.delete(listener);
  }

  public onTyping(listener: TypingListener): () => void {
    this.typingListeners.add(listener);
    return () => this.typingListeners.delete(listener);
  }

  public onReactionUpdated(listener: MessageReactionListener): () => void {
    this.reactionListeners.add(listener);
    return () => this.reactionListeners.delete(listener);
  }

  private setStatus(newStatus: WebSocketStatus): void {
    if (this.status !== newStatus) {
      this.status = newStatus;
      for (const listener of this.statusListeners) {
        listener(newStatus);
      }
    }
  }

  public connect(): void {
    if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) {
      return;
    }

    this.manualClose = false;
    this.setStatus(this.reconnectAttempt > 0 ? 'reconnecting' : 'connecting');

    try {
      this.ws = new WebSocket(this.url);
    } catch {
      this.setStatus('disconnected');
      this.scheduleReconnect();
      return;
    }

    this.ws.onopen = () => {
      this.reconnectAttempt = 0;
      this.setStatus('connected');
      this.startHeartbeat();
    };

    this.ws.onmessage = (event: MessageEvent) => {
      this.handleIncoming(event.data);
    };

    this.ws.onclose = () => {
      this.stopHeartbeat();
      this.rejectAllPending(new Error('WebSocket connection closed'));
      if (!this.manualClose) {
        this.setStatus('disconnected');
        this.scheduleReconnect();
      } else {
        this.setStatus('disconnected');
      }
    };

    this.ws.onerror = () => {
      // Browser handles onError followed by onClose
    };
  }

  public disconnect(): void {
    this.manualClose = true;
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.stopHeartbeat();
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
    this.onlineUsers.clear();
    this.rejectAllPending(new Error('WebSocket manually disconnected'));
    this.setStatus('disconnected');
  }

  private scheduleReconnect(): void {
    if (this.manualClose || this.reconnectTimer) return;

    this.reconnectAttempt++;
    // Exponential backoff: min(1000 * 2^attempt, 8000) + jitter
    const delay = Math.min(1000 * Math.pow(1.5, this.reconnectAttempt - 1), 8000) + Math.random() * 500;
    this.setStatus('reconnecting');

    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.connect();
    }, delay);
  }

  private startHeartbeat(): void {
    this.stopHeartbeat();
    this.heartbeatTimer = setInterval(() => {
      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        this.ws.send(JSON.stringify({ type: 'ping', request_id: `ping-${Date.now()}` }));
      }
    }, 30000);
  }

  private stopHeartbeat(): void {
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
  }

  private handleIncoming(rawData: string): void {
    try {
      const data: WebSocketEnvelope = JSON.parse(rawData);
      const reqId = data.request_id;

      switch (data.type) {
        case 'connection.ready':
          // Handshake acknowledged by server
          break;

        case 'presence.snapshot': {
          const payload = data.payload as PresenceSnapshotPayload;
          this.onlineUsers = new Set(payload.online_users || []);
          this.notifyPresence();
          break;
        }

        case 'presence.changed': {
          const payload = data.payload as PresenceChangedPayload;
          if (payload.status === 'online') {
            this.onlineUsers.add(payload.user_id);
          } else {
            this.onlineUsers.delete(payload.user_id);
          }
          this.notifyPresence();
          break;
        }

        case 'message.ack': {
          if (reqId && this.pendingRequests.has(reqId)) {
            const pending = this.pendingRequests.get(reqId)!;
            clearTimeout(pending.timer);
            this.pendingRequests.delete(reqId);
            pending.resolve(data.payload as MessageAckPayload);
          }
          break;
        }

        case 'message.created': {
          const payload = data.payload as MessageCreatedPayload;
          for (const listener of this.messageListeners) {
            listener(payload);
          }
          break;
        }

        case 'error': {
          const errPayload = data.payload as { code: string; message: string; details?: unknown };
          if (reqId && this.pendingRequests.has(reqId)) {
            const pending = this.pendingRequests.get(reqId)!;
            clearTimeout(pending.timer);
            this.pendingRequests.delete(reqId);
            pending.reject(new Error(errPayload.message || 'WebSocket request failed'));
          }
          for (const listener of this.errorListeners) {
            listener(errPayload);
          }
          break;
        }

        case 'conversation.updated': {
          const payload = data.payload as { conversation_id: number };
          for (const listener of this.conversationListeners) {
            listener(payload);
          }
          break;
        }

        case 'message.read.updated': {
          const payload = data.payload as MessageReadUpdatedPayload;
          for (const listener of this.readListeners) {
            listener(payload);
          }
          break;
        }

        case 'typing.updated': {
          const payload = data.payload as TypingUpdatedPayload;
          for (const listener of this.typingListeners) {
            listener(payload);
          }
          break;
        }

        case 'message.reaction.updated': {
          const payload = data.payload as MessageReactionUpdatedPayload;
          for (const listener of this.reactionListeners) {
            listener(payload);
          }
          break;
        }

        case 'pong':
          // Heartbeat pong received
          break;

        default:
          break;
      }
    } catch (err) {
      console.warn('Failed to parse incoming WebSocket message:', err);
    }
  }

  private notifyPresence(): void {
    const copy = new Set(this.onlineUsers);
    for (const listener of this.presenceListeners) {
      listener(copy);
    }
  }

  private rejectAllPending(err: Error): void {
    for (const [, pending] of this.pendingRequests) {
      clearTimeout(pending.timer);
      pending.reject(err);
    }
    this.pendingRequests.clear();
  }

  public async sendMessage(
    conversationId: number,
    content: string,
    clientMessageId?: string,
    replyToMessageId?: number
  ): Promise<MessageAckPayload> {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      throw new Error('WebSocket is not connected');
    }

    const requestId = `req-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;

    return new Promise<MessageAckPayload>((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pendingRequests.delete(requestId);
        reject(new Error('WebSocket message send timed out'));
      }, 10000);

      this.pendingRequests.set(requestId, { resolve, reject, timer });

      try {
        this.ws!.send(
          JSON.stringify({
            type: 'message.send',
            request_id: requestId,
            payload: {
              conversation_id: conversationId,
              content,
              client_message_id: clientMessageId,
              reply_to_message_id: replyToMessageId,
            },
          })
        );
      } catch (err) {
        clearTimeout(timer);
        this.pendingRequests.delete(requestId);
        reject(err instanceof Error ? err : new Error(String(err)));
      }
    });
  }

  public sendMarkRead(conversationId: number, lastReadMessageId?: number): void {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return;
    try {
      this.ws.send(
        JSON.stringify({
          type: 'message.read',
          payload: {
            conversation_id: conversationId,
            last_read_message_id: lastReadMessageId,
          },
        })
      );
    } catch (err) {
      console.warn('Failed to send message.read via WebSocket:', err);
    }
  }

  public sendTyping(conversationId: number, isTyping: boolean): void {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return;
    try {
      this.ws.send(
        JSON.stringify({
          type: isTyping ? 'typing.start' : 'typing.stop',
          payload: {
            conversation_id: conversationId,
          },
        })
      );
    } catch (err) {
      console.warn('Failed to send typing status via WebSocket:', err);
    }
  }

  public toggleReaction(messageId: number, emoji: string): void {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return;
    try {
      this.ws.send(
        JSON.stringify({
          type: 'reaction.toggle',
          payload: {
            message_id: messageId,
            emoji,
          },
        })
      );
    } catch (err) {
      console.warn('Failed to send reaction.toggle via WebSocket:', err);
    }
  }
}

// Global default singleton instance
export const wsClient = new LANWebSocketClient();
