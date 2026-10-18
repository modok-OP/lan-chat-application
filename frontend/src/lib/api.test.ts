import { describe, it, expect, vi, beforeEach } from 'vitest';
import { api, formatBytes, getFileIcon } from './api';

describe('API Client', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('fetches health check endpoint with /api/health', async () => {
    const mockHealth = {
      status: 'healthy',
      app_name: 'LAN Chat Application',
      version: '0.1.0',
      database: 'connected',
      environment: 'development',
      timestamp: new Date().toISOString(),
    };

    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockHealth,
    });
    globalThis.fetch = fetchMock;

    const result = await api.getHealth();

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/health',
      expect.objectContaining({
        method: 'GET',
        credentials: 'include',
      })
    );
    expect(result).toEqual(mockHealth);
  });

  it('calls /api/auth/login with credentials: include', async () => {
    const mockUser = {
      id: 1,
      username: 'alice',
      display_name: 'Alice',
      role: 'user',
      is_active: true,
      created_at: new Date().toISOString(),
    };

    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockUser,
    });
    globalThis.fetch = fetchMock;

    const result = await api.login({ username: 'alice', password: 'password123' });

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/auth/login',
      expect.objectContaining({
        method: 'POST',
        credentials: 'include',
        body: JSON.stringify({ username: 'alice', password: 'password123' }),
      })
    );
    expect(result).toEqual(mockUser);
  });

  it('calls /api/conversations to list conversations', async () => {
    const mockConversations = [
      {
        id: 1,
        type: 'direct',
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        members: [],
      },
    ];

    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockConversations,
    });
    globalThis.fetch = fetchMock;

    const result = await api.getConversations();

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/conversations',
      expect.objectContaining({ method: 'GET', credentials: 'include' })
    );
    expect(result).toEqual(mockConversations);
  });

  it('calls /api/conversations/direct to create a direct chat', async () => {
    const mockConv = {
      id: 2,
      type: 'direct',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      members: [],
    };

    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockConv,
    });
    globalThis.fetch = fetchMock;

    const result = await api.createDirectConversation(5);

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/conversations/direct',
      expect.objectContaining({
        method: 'POST',
        credentials: 'include',
        body: JSON.stringify({ target_user_id: 5 }),
      })
    );
    expect(result).toEqual(mockConv);
  });

  it('calls /api/conversations/{id}/messages to get and post messages', async () => {
    const mockHistory = {
      messages: [],
      has_more: false,
    };
    const mockNewMsg = {
      id: 1,
      conversation_id: 2,
      content: 'Hello World',
      message_type: 'text',
      created_at: new Date().toISOString(),
    };

    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => mockHistory,
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => mockNewMsg,
      });
    globalThis.fetch = fetchMock;

    const history = await api.getMessages(2);
    expect(history).toEqual(mockHistory);

    const posted = await api.postMessage(2, 'Hello World');
    expect(posted).toEqual(mockNewMsg);
  });

  it('calls group administration endpoints (rename, add, remove, leave, transfer)', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ status: 'success' }),
    });
    globalThis.fetch = fetchMock;

    await api.renameGroup(10, 'New Team Name');
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/conversations/10',
      expect.objectContaining({
        method: 'PATCH',
        body: JSON.stringify({ name: 'New Team Name' }),
      })
    );

    await api.addGroupMember(10, 4, 'admin');
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/conversations/10/members',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ user_id: 4, role: 'admin' }),
      })
    );

    await api.removeGroupMember(10, 4);
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/conversations/10/members/4',
      expect.objectContaining({ method: 'DELETE' })
    );

    await api.leaveGroup(10);
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/conversations/10/leave',
      expect.objectContaining({ method: 'POST' })
    );

    await api.transferOwnership(10, 5);
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/conversations/10/transfer-ownership',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ new_owner_id: 5 }),
      })
    );
  });

  it('formats bytes correctly with formatBytes', () => {
    expect(formatBytes(0)).toBe('0 Bytes');
    expect(formatBytes(1024)).toBe('1 KB');
    expect(formatBytes(1048576)).toBe('1 MB');
    expect(formatBytes(26214400)).toBe('25 MB');
  });

  it('returns appropriate file icons with getFileIcon', () => {
    expect(getFileIcon('document.pdf')).toBe('📕');
    expect(getFileIcon('photo.png')).toBe('🖼️');
    expect(getFileIcon('archive.zip')).toBe('📦');
    expect(getFileIcon('script.py')).toBe('💻');
    expect(getFileIcon('unknown.xyz')).toBe('📄');
  });

  it('calls /api/attachments/{id} for metadata', async () => {
    const mockAtt = {
      id: 42,
      original_filename: 'spec.pdf',
      mime_type: 'application/pdf',
      size_bytes: 12345,
      sha256: 'abcd1234',
      uploaded_by: 1,
      created_at: new Date().toISOString(),
      download_url: '/api/attachments/42/download',
    };

    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockAtt,
    });
    globalThis.fetch = fetchMock;

    const result = await api.getAttachmentMetadata(42);
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/attachments/42',
      expect.objectContaining({ method: 'GET' })
    );
    expect(result).toEqual(mockAtt);
  });

  it('calls /api/conversations/{id}/messages with reply_to_message_id', async () => {
    const mockMsg = {
      id: 10,
      conversation_id: 1,
      content: 'This is a reply',
      reply_to_message_id: 5,
      created_at: new Date().toISOString(),
    };

    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockMsg,
    });
    globalThis.fetch = fetchMock;

    const result = await api.postMessage(1, 'This is a reply', 'client-123', 5);
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/conversations/1/messages',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({
          content: 'This is a reply',
          client_message_id: 'client-123',
          reply_to_message_id: 5,
        }),
      })
    );
    expect(result).toEqual(mockMsg);
  });

  it('calls /api/messages/{id}/reactions to toggle emoji reactions', async () => {
    const mockRes = {
      message_id: 10,
      conversation_id: 1,
      action: 'added',
      reactions: [{ emoji: '👍', count: 1, user_ids: [1], usernames: ['alice'] }],
    };

    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockRes,
    });
    globalThis.fetch = fetchMock;

    const result = await api.toggleReaction(10, '👍');
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/messages/10/reactions',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ emoji: '👍' }),
      })
    );
    expect(result).toEqual(mockRes);
  });
});
