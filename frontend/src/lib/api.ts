import { ApiError } from '../types';
import type {
  ApiErrorResponse,
  HealthResponse,
  User,
  RegisterPayload,
  LoginPayload,
  AuthStatus,
  Conversation,
  MemberSummary,
  PaginatedMessages,
  SearchMessagesResponse,
  Message,
  Attachment,
  ReactionToggleResponse,
} from '../types';

const API_BASE_URL = '/api';

interface RequestOptions extends RequestInit {
  params?: Record<string, string | number | boolean | undefined>;
}

export async function request<T>(endpoint: string, options: RequestOptions = {}): Promise<T> {
  const { params, headers, ...customConfig } = options;

  let url = `${API_BASE_URL}${endpoint.startsWith('/') ? endpoint : `/${endpoint}`}`;

  if (params) {
    const query = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined) {
        query.append(key, String(value));
      }
    });
    const queryString = query.toString();
    if (queryString) {
      url += `?${queryString}`;
    }
  }

  const config: RequestInit = {
    method: options.method || 'GET',
    headers: {
      'Content-Type': 'application/json',
      ...headers,
    },
    credentials: 'include', // Includes session cookie for LAN auth
    ...customConfig,
  };

  const response = await fetch(url, config);

  if (!response.ok) {
    let errorDetail = {
      code: `HTTP_${response.status}`,
      message: response.statusText || 'Request failed',
    };

    try {
      const errorJson: ApiErrorResponse = await response.json();
      if (errorJson?.error) {
        errorDetail = errorJson.error;
      }
    } catch {
      // Fallback to HTTP status text if not JSON
    }

    throw new ApiError(response.status, errorDetail);
  }

  return response.json();
}

export const api = {
  get: <T>(endpoint: string, options?: RequestOptions) =>
    request<T>(endpoint, { ...options, method: 'GET' }),

  post: <T>(endpoint: string, body?: unknown, options?: RequestOptions) =>
    request<T>(endpoint, {
      ...options,
      method: 'POST',
      body: body ? JSON.stringify(body) : undefined,
    }),

  patch: <T>(endpoint: string, body?: unknown, options?: RequestOptions) =>
    request<T>(endpoint, {
      ...options,
      method: 'PATCH',
      body: body ? JSON.stringify(body) : undefined,
    }),

  delete: <T>(endpoint: string, options?: RequestOptions) =>
    request<T>(endpoint, { ...options, method: 'DELETE' }),

  getHealth: () => request<HealthResponse>('/health'),

  // Authentication API methods
  register: (payload: RegisterPayload) =>
    request<User>('/auth/register', { method: 'POST', body: JSON.stringify(payload) }),
  login: (payload: LoginPayload) =>
    request<User>('/auth/login', { method: 'POST', body: JSON.stringify(payload) }),
  logout: () => request<AuthStatus>('/auth/logout', { method: 'POST' }),
  getCurrentUser: () => request<User>('/me', { method: 'GET' }),

  // User search
  searchUsers: (search?: string) =>
    request<User[]>('/users', { method: 'GET', params: { search } }),

  // Conversations API methods
  getConversations: () => request<Conversation[]>('/conversations', { method: 'GET' }),
  getConversation: (id: number) => request<Conversation>(`/conversations/${id}`, { method: 'GET' }),
  createDirectConversation: (targetUserId: number) =>
    request<Conversation>('/conversations/direct', {
      method: 'POST',
      body: JSON.stringify({ target_user_id: targetUserId }),
    }),
  createGroupConversation: (name: string, memberIds: number[]) =>
    request<Conversation>('/conversations/groups', {
      method: 'POST',
      body: JSON.stringify({ name, member_ids: memberIds }),
    }),
  renameGroup: (id: number, name: string) =>
    request<Conversation>(`/conversations/${id}`, {
      method: 'PATCH',
      body: JSON.stringify({ name }),
    }),
  addGroupMember: (id: number, userId: number, role: string = 'member') =>
    request<MemberSummary>(`/conversations/${id}/members`, {
      method: 'POST',
      body: JSON.stringify({ user_id: userId, role }),
    }),
  removeGroupMember: (id: number, userId: number) =>
    request<AuthStatus>(`/conversations/${id}/members/${userId}`, { method: 'DELETE' }),
  leaveGroup: (id: number) =>
    request<AuthStatus>(`/conversations/${id}/leave`, { method: 'POST' }),
  transferOwnership: (id: number, newOwnerId: number) =>
    request<Conversation>(`/conversations/${id}/transfer-ownership`, {
      method: 'POST',
      body: JSON.stringify({ new_owner_id: newOwnerId }),
    }),
  markConversationRead: (conversationId: number, lastReadMessageId?: number) =>
    request<{ conversation_id: number; last_read_message_id: number; unread_count: number }>(
      `/conversations/${conversationId}/read`,
      {
        method: 'POST',
        body: JSON.stringify({ last_read_message_id: lastReadMessageId }),
      }
    ),

  // Messages API methods
  getMessages: (conversationId: number, before?: number, limit: number = 50) =>
    request<PaginatedMessages>(`/conversations/${conversationId}/messages`, {
      method: 'GET',
      params: { before, limit },
    }),
  postMessage: (
    conversationId: number,
    content: string,
    clientMessageId?: string,
    replyToMessageId?: number
  ) =>
    request<Message>(`/conversations/${conversationId}/messages`, {
      method: 'POST',
      body: JSON.stringify({
        content,
        client_message_id: clientMessageId,
        reply_to_message_id: replyToMessageId,
      }),
    }),
  toggleReaction: (messageId: number, emoji: string) =>
    request<ReactionToggleResponse>(`/messages/${messageId}/reactions`, {
      method: 'POST',
      body: JSON.stringify({ emoji }),
    }),
  searchMessages: (conversationId: number, query: string, limit: number = 50) =>
    request<SearchMessagesResponse>(`/conversations/${conversationId}/messages/search`, {
      method: 'GET',
      params: { q: query, limit },
    }),

  // Attachments API methods
  uploadAttachment: (
    conversationId: number,
    file: File,
    clientMessageId?: string,
    onProgress?: (percent: number) => void
  ): Promise<Message> => {
    return new Promise((resolve, reject) => {
      const formData = new FormData();
      formData.append('file', file);
      if (clientMessageId) {
        formData.append('client_message_id', clientMessageId);
      }

      const xhr = new XMLHttpRequest();
      xhr.open('POST', `/api/conversations/${conversationId}/attachments`);
      xhr.withCredentials = true;

      if (onProgress && xhr.upload) {
        xhr.upload.onprogress = (event) => {
          if (event.lengthComputable && event.total > 0) {
            const percent = Math.min(100, Math.round((event.loaded / event.total) * 100));
            onProgress(percent);
          }
        };
      }

      xhr.onload = () => {
        try {
          const data = JSON.parse(xhr.responseText);
          if (xhr.status >= 200 && xhr.status < 300) {
            resolve(data as Message);
          } else {
            const errorDetail = data?.error || {
              code: 'HTTP_ERROR',
              message: `Upload failed with status ${xhr.status}`,
            };
            reject(new ApiError(xhr.status, errorDetail));
          }
        } catch {
          reject(
            new ApiError(xhr.status, {
              code: 'PARSE_ERROR',
              message: 'Invalid response from server',
            })
          );
        }
      };

      xhr.onerror = () => {
        reject(
          new ApiError(0, {
            code: 'NETWORK_ERROR',
            message: 'Network error occurred during file upload',
          })
        );
      };

      xhr.send(formData);
    });
  },

  getAttachmentMetadata: (attachmentId: number): Promise<Attachment> =>
    request<Attachment>(`/attachments/${attachmentId}`, { method: 'GET' }),
};

/**
 * Format raw byte size into human-readable string (KB, MB, GB).
 */
export function formatBytes(bytes: number, decimals: number = 1): string {
  if (bytes === 0) return '0 Bytes';
  const k = 1024;
  const dm = decimals < 0 ? 0 : decimals;
  const sizes = ['Bytes', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(dm))} ${sizes[i]}`;
}

/**
 * Choose a clean descriptive icon based on file extension or MIME type.
 */
export function getFileIcon(filename: string): string {
  const ext = filename.split('.').pop()?.toLowerCase() || '';
  if (['png', 'jpg', 'jpeg', 'gif', 'webp', 'svg', 'bmp'].includes(ext)) return '🖼️';
  if (['pdf'].includes(ext)) return '📕';
  if (['doc', 'docx', 'odt', 'rtf'].includes(ext)) return '📝';
  if (['xls', 'xlsx', 'csv'].includes(ext)) return '📊';
  if (['zip', 'tar', 'gz', '7z', 'rar'].includes(ext)) return '📦';
  if (['mp3', 'wav', 'ogg', 'flac'].includes(ext)) return '🎵';
  if (['mp4', 'mkv', 'webm', 'mov', 'avi'].includes(ext)) return '🎬';
  if (['py', 'js', 'ts', 'tsx', 'jsx', 'json', 'html', 'css', 'c', 'cpp'].includes(ext)) return '💻';
  return '📄';
}
