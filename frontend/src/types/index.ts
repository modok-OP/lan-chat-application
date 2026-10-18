export interface HealthResponse {
  status: 'healthy' | 'degraded' | string;
  app_name: string;
  version: string;
  database: 'connected' | 'disconnected' | string;
  environment: string;
  lan_ips?: string[];
  timestamp: string;
}

export interface ApiErrorDetail {
  code: string;
  message: string;
  details?: unknown;
}

export interface ApiErrorResponse {
  error: ApiErrorDetail;
}

export class ApiError extends Error {
  code: string;
  details?: unknown;
  status: number;

  constructor(status: number, errorDetail: ApiErrorDetail) {
    super(errorDetail.message);
    this.name = 'ApiError';
    this.status = status;
    this.code = errorDetail.code;
    this.details = errorDetail.details;
  }
}

export interface User {
  id: number;
  username: string;
  display_name: string;
  role: string;
  is_active: boolean;
  created_at: string;
  last_seen_at?: string | null;
}

export interface RegisterPayload {
  username: string;
  password: string;
  display_name?: string;
}

export interface LoginPayload {
  username: string;
  password: string;
}

export interface AuthStatus {
  message: string;
}

export interface MemberSummary {
  user_id: number;
  username: string;
  display_name: string;
  role: string;
  is_active: boolean;
  joined_at: string;
  last_read_message_id?: number | null;
}

export interface Conversation {
  id: number;
  type: 'direct' | 'group';
  name?: string | null;
  created_by?: number | null;
  direct_key?: string | null;
  created_at: string;
  updated_at: string;
  members: MemberSummary[];
  unread_count?: number;
}

export interface Attachment {
  id: number;
  message_id?: number | null;
  original_filename: string;
  mime_type: string;
  size_bytes: number;
  sha256: string;
  uploaded_by: number;
  created_at: string;
  download_url: string;
}

export interface ReactionSummary {
  emoji: string;
  count: number;
  user_ids: number[];
  usernames: string[];
}

export interface ReplySummary {
  id: number;
  sender_username?: string | null;
  sender_display_name?: string | null;
  content: string;
  message_type: string;
}

export interface ReactionToggleResponse {
  message_id: number;
  conversation_id: number;
  action: 'added' | 'removed';
  reactions: ReactionSummary[];
}

export interface Message {
  id: number;
  conversation_id: number;
  sender_id?: number | null;
  sender_username?: string | null;
  sender_display_name?: string | null;
  client_message_id?: string | null;
  message_type: string;
  content: string;
  reply_to_message_id?: number | null;
  reply_to?: ReplySummary | null;
  reactions?: ReactionSummary[];
  created_at: string;
  edited_at?: string | null;
  deleted_at?: string | null;
  attachments?: Attachment[];
}

export interface PaginatedMessages {
  messages: Message[];
  has_more: boolean;
  oldest_id?: number | null;
}

export interface SearchMessagesResponse {
  conversation_id: number;
  query: string;
  total_matches: number;
  messages: Message[];
}

export type WebSocketStatus = 'connected' | 'connecting' | 'disconnected' | 'reconnecting';

export interface PresenceSnapshotPayload {
  online_users: number[];
}

export interface PresenceChangedPayload {
  user_id: number;
  status: 'online' | 'offline';
}

export interface MessageAckPayload {
  message_id: number;
  client_message_id?: string | null;
  conversation_id: number;
  created_at: string;
}

export interface MessageCreatedPayload {
  message_id: number;
  conversation_id: number;
  sender?: {
    id: number;
    username: string;
    display_name: string;
  } | null;
  message_type: string;
  content: string;
  client_message_id?: string | null;
  reply_to_message_id?: number | null;
  reply_to?: ReplySummary | null;
  reactions?: ReactionSummary[];
  created_at: string;
  attachments?: Attachment[];
}

export interface MessageReactionUpdatedPayload {
  conversation_id: number;
  message_id: number;
  reactions: ReactionSummary[];
}

export interface MessageReadUpdatedPayload {
  conversation_id: number;
  user_id: number;
  last_read_message_id: number;
}

export interface TypingUpdatedPayload {
  conversation_id: number;
  user_id: number;
  username: string;
  display_name: string;
  is_typing: boolean;
}

export interface WebSocketEnvelope<T = unknown> {
  type: string;
  request_id?: string;
  payload?: T;
}
