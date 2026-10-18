import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { LANWebSocketClient } from './websocket';

// Mock WebSocket class for unit tests
class MockWebSocket {
  public static instances: MockWebSocket[] = [];
  public readyState: number = WebSocket.CONNECTING;
  public url: string;
  public onopen: (() => void) | null = null;
  public onmessage: ((e: { data: string }) => void) | null = null;
  public onclose: (() => void) | null = null;
  public onerror: ((err: unknown) => void) | null = null;
  public sent: string[] = [];

  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
    // Simulate async connection open
    setTimeout(() => {
      this.readyState = WebSocket.OPEN;
      if (this.onopen) this.onopen();
    }, 10);
  }

  send(data: string) {
    this.sent.push(data);
  }

  close() {
    this.readyState = WebSocket.CLOSED;
    if (this.onclose) this.onclose();
  }
}

describe('LANWebSocketClient', () => {
  let originalWebSocket: typeof WebSocket;

  beforeEach(() => {
    MockWebSocket.instances = [];
    originalWebSocket = globalThis.WebSocket;
    globalThis.WebSocket = MockWebSocket as unknown as typeof WebSocket;
  });

  afterEach(() => {
    globalThis.WebSocket = originalWebSocket;
    vi.restoreAllMocks();
  });

  it('connects and transitions status to connected', async () => {
    const client = new LANWebSocketClient('ws://localhost:8000/ws');
    const statuses: string[] = [];
    client.onStatusChange((s) => statuses.push(s));

    client.connect();
    expect(client.getStatus()).toBe('connecting');

    // Wait for mock connection to open
    await new Promise((r) => setTimeout(r, 20));

    expect(client.getStatus()).toBe('connected');
    expect(statuses).toContain('connected');

    client.disconnect();
    expect(client.getStatus()).toBe('disconnected');
  });

  it('handles presence.snapshot and presence.changed', async () => {
    const client = new LANWebSocketClient('ws://localhost:8000/ws');
    let currentOnline = new Set<number>();
    client.onPresence((users) => {
      currentOnline = users;
    });

    client.connect();
    await new Promise((r) => setTimeout(r, 20));

    const mockWs = MockWebSocket.instances[0];

    // Simulate presence.snapshot from server
    mockWs.onmessage!({
      data: JSON.stringify({
        type: 'presence.snapshot',
        payload: { online_users: [1, 2, 5] },
      }),
    });

    expect(Array.from(currentOnline).sort()).toEqual([1, 2, 5]);

    // Simulate presence.changed (user 3 comes online)
    mockWs.onmessage!({
      data: JSON.stringify({
        type: 'presence.changed',
        payload: { user_id: 3, status: 'online' },
      }),
    });

    expect(currentOnline.has(3)).toBe(true);

    // Simulate presence.changed (user 1 goes offline)
    mockWs.onmessage!({
      data: JSON.stringify({
        type: 'presence.changed',
        payload: { user_id: 1, status: 'offline' },
      }),
    });

    expect(currentOnline.has(1)).toBe(false);
    expect(currentOnline.has(2)).toBe(true);

    client.disconnect();
  });

  it('receives and dispatches message.created events', async () => {
    const client = new LANWebSocketClient('ws://localhost:8000/ws');
    const receivedMessages: unknown[] = [];
    client.onMessageCreated((msg) => receivedMessages.push(msg));

    client.connect();
    await new Promise((r) => setTimeout(r, 20));

    const mockWs = MockWebSocket.instances[0];
    const incomingPayload = {
      message_id: 42,
      conversation_id: 10,
      sender: { id: 1, username: 'alice', display_name: 'Alice' },
      message_type: 'text',
      content: 'Real-time greetings!',
      created_at: new Date().toISOString(),
    };

    mockWs.onmessage!({
      data: JSON.stringify({
        type: 'message.created',
        payload: incomingPayload,
      }),
    });

    expect(receivedMessages).toHaveLength(1);
    expect(receivedMessages[0]).toEqual(incomingPayload);

    client.disconnect();
  });

  it('sends message and resolves on matching message.ack', async () => {
    const client = new LANWebSocketClient('ws://localhost:8000/ws');
    client.connect();
    await new Promise((r) => setTimeout(r, 20));

    const mockWs = MockWebSocket.instances[0];

    const sendPromise = client.sendMessage(5, 'Hello LAN', 'cid-123');

    // Verify message was formatted and sent
    expect(mockWs.sent).toHaveLength(1);
    const sentData = JSON.parse(mockWs.sent[0]);
    expect(sentData.type).toBe('message.send');
    expect(sentData.payload.conversation_id).toBe(5);
    expect(sentData.payload.content).toBe('Hello LAN');
    expect(sentData.payload.client_message_id).toBe('cid-123');

    // Simulate server message.ack response
    mockWs.onmessage!({
      data: JSON.stringify({
        type: 'message.ack',
        request_id: sentData.request_id,
        payload: {
          message_id: 99,
          client_message_id: 'cid-123',
          conversation_id: 5,
          created_at: new Date().toISOString(),
        },
      }),
    });

    const ackResult = await sendPromise;
    expect(ackResult.message_id).toBe(99);
    expect(ackResult.conversation_id).toBe(5);

    client.disconnect();
  });

  it('rejects sendMessage when server responds with error for that request', async () => {
    const client = new LANWebSocketClient('ws://localhost:8000/ws');
    client.connect();
    await new Promise((r) => setTimeout(r, 20));

    const mockWs = MockWebSocket.instances[0];

    const sendPromise = client.sendMessage(999, 'Unauthorized chat');
    const sentData = JSON.parse(mockWs.sent[0]);

    // Simulate server error response
    mockWs.onmessage!({
      data: JSON.stringify({
        type: 'error',
        request_id: sentData.request_id,
        payload: {
          code: 'CONVERSATION_ACCESS_DENIED',
          message: 'You are not a member of this conversation',
        },
      }),
    });

    await expect(sendPromise).rejects.toThrow('You are not a member of this conversation');

    client.disconnect();
  });

  it('handles message.reaction.updated events and dispatches to listeners', async () => {
    const client = new LANWebSocketClient('ws://localhost:8000/ws');
    client.connect();
    await new Promise((r) => setTimeout(r, 20));

    const mockWs = MockWebSocket.instances[0];
    let receivedPayload: any = null;
    client.onReactionUpdated((payload) => {
      receivedPayload = payload;
    });

    mockWs.onmessage!({
      data: JSON.stringify({
        type: 'message.reaction.updated',
        payload: {
          conversation_id: 1,
          message_id: 42,
          reactions: [{ emoji: '🔥', count: 1, user_ids: [10], usernames: ['bob'] }],
        },
      }),
    });

    expect(receivedPayload).toEqual({
      conversation_id: 1,
      message_id: 42,
      reactions: [{ emoji: '🔥', count: 1, user_ids: [10], usernames: ['bob'] }],
    });

    client.disconnect();
  });

  it('sends reaction.toggle via toggleReaction', async () => {
    const client = new LANWebSocketClient('ws://localhost:8000/ws');
    client.connect();
    await new Promise((r) => setTimeout(r, 20));

    const mockWs = MockWebSocket.instances[0];
    client.toggleReaction(42, '🎉');

    expect(mockWs.sent).toHaveLength(1);
    const sentData = JSON.parse(mockWs.sent[0]);
    expect(sentData.type).toBe('reaction.toggle');
    expect(sentData.payload.message_id).toBe(42);
    expect(sentData.payload.emoji).toBe('🎉');

    client.disconnect();
  });
});
