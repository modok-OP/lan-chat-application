import React, { useState, useEffect, useCallback } from 'react';
import { useAuth } from '../hooks/useAuth';
import { useWebSocket } from '../hooks/useWebSocket';
import { AuthCard } from '../features/auth';
import {
  ConversationList,
  CreateConversationDialog,
  ConversationView,
} from '../features/conversations';
import { api } from '../lib/api';
import type { Conversation } from '../types';
import './App.css';

export const App: React.FC = () => {
  const {
    user,
    loading: authLoading,
    authError,
    login,
    register,
    logout,
    clearError,
  } = useAuth();

  const {
    status: wsStatus,
    onlineUsers,
    lastMessage,
    lastConversationUpdate,
    lastReadUpdate,
    lastTypingUpdate,
    lastReactionUpdate,
    sendMessage,
    sendMarkRead,
    sendTyping,
    reconnect,
  } = useWebSocket(user);

  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeConvId, setActiveConvId] = useState<number | null>(null);
  const [loadingConversations, setLoadingConversations] = useState(false);
  const [isNewDialogOpen, setIsNewDialogOpen] = useState(false);
  const [hostIp, setHostIp] = useState<string>(window.location.host || '0.0.0.0:8000');
  const [copiedIp, setCopiedIp] = useState(false);

  // Discover reachable host LAN IP on initial mount
  useEffect(() => {
    api.getHealth()
      .then((health) => {
        if (health.lan_ips && health.lan_ips.length > 0) {
          const currentIsLoopback = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
          if (currentIsLoopback) {
            setHostIp(`${health.lan_ips[0]}:8000`);
          }
        }
      })
      .catch(() => {});
  }, []);

  const handleCopyIp = () => {
    const url = `http://${hostIp}`;
    if (navigator?.clipboard?.writeText) {
      navigator.clipboard.writeText(url)
        .then(() => {
          setCopiedIp(true);
          setTimeout(() => setCopiedIp(false), 2000);
        })
        .catch(() => {});
    }
  };

  // Fetch conversations when user is authenticated
  const loadConversations = useCallback(async () => {
    if (!user) return;
    try {
      setLoadingConversations(true);
      const data = await api.getConversations();
      setConversations(data);
      if (data.length > 0 && activeConvId === null) {
        setActiveConvId(data[0].id);
      }
    } catch (err) {
      console.error('Failed to load conversations:', err);
    } finally {
      setLoadingConversations(false);
    }
  }, [user, activeConvId]);

  useEffect(() => {
    if (user) {
      loadConversations();
    } else {
      setConversations([]);
      setActiveConvId(null);
    }
  }, [user, loadConversations]);

  // Mark active conversation as read when selected
  useEffect(() => {
    if (!activeConvId || !user) return;
    api.markConversationRead(activeConvId).catch((err) => {
      console.warn('Failed to mark conversation read via HTTP:', err);
    });
    sendMarkRead(activeConvId);
    setConversations((prev) =>
      prev.map((c) => (c.id === activeConvId ? { ...c, unread_count: 0 } : c))
    );
  }, [activeConvId, user, sendMarkRead]);

  // When a new message arrives via WebSocket, update unread counts or mark active chat as read
  useEffect(() => {
    if (!lastMessage) return;

    if (activeConvId === lastMessage.conversation_id) {
      api.markConversationRead(activeConvId).catch(() => {});
      sendMarkRead(activeConvId, lastMessage.message_id);
      setConversations((prev) =>
        prev.map((c) => (c.id === activeConvId ? { ...c, unread_count: 0 } : c))
      );
    } else {
      setConversations((prev) =>
        prev.map((c) => {
          if (c.id === lastMessage.conversation_id) {
            return {
              ...c,
              unread_count: (c.unread_count || 0) + 1,
            };
          }
          return c;
        })
      );
    }
  }, [lastMessage, activeConvId, sendMarkRead]);

  // Handle conversation metadata update from WebSocket
  useEffect(() => {
    if (!lastConversationUpdate) return;
    loadConversations();
  }, [lastConversationUpdate, loadConversations]);

  // When a peer marks messages read, update our local conversation model
  useEffect(() => {
    if (!lastReadUpdate || !user) return;
    const { conversation_id, user_id, last_read_message_id } = lastReadUpdate;

    setConversations((prev) =>
      prev.map((c) => {
        if (c.id === conversation_id) {
          const updatedMembers = c.members.map((m) =>
            m.user_id === user_id
              ? { ...m, last_read_message_id }
              : m
          );
          return {
            ...c,
            members: updatedMembers,
            unread_count: user_id === user.id ? 0 : c.unread_count,
          };
        }
        return c;
      })
    );
  }, [lastReadUpdate, user]);

  const handleDirectCreated = async (targetUserId: number) => {
    const newConv = await api.createDirectConversation(targetUserId);
    await loadConversations();
    setActiveConvId(newConv.id);
  };

  const handleGroupCreated = async (name: string, memberIds: number[]) => {
    const newGroup = await api.createGroupConversation(name, memberIds);
    await loadConversations();
    setActiveConvId(newGroup.id);
  };

  const activeConversation = conversations.find((c) => c.id === activeConvId);

  const renderWsBadge = () => {
    let label = 'Disconnected';
    if (wsStatus === 'connected') label = 'Online';
    else if (wsStatus === 'connecting') label = 'Connecting...';
    else if (wsStatus === 'reconnecting') label = 'Reconnecting...';

    return (
      <div className={`wsBadge wsBadge_${wsStatus}`} title={`WebSocket status: ${wsStatus}`}>
        <span className="wsDot" />
        <span>{label}</span>
      </div>
    );
  };

  return (
    <div className="appContainer">
      <header className="navbar">
        <div className="brand">
          <div className="logoIcon">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
            </svg>
          </div>
          <div className="brandText">
            <h1 className="brandTitle">LAN Chat</h1>
            <span className="brandBadge">OFFLINE LAN</span>
          </div>
        </div>

        <div className="navActions">
          {user && (
            <>
              {renderWsBadge()}
              <div className="userPill">
                <span className="userAvatar">
                  {(user.display_name || user.username).slice(0, 1).toUpperCase()}
                </span>
                <span className="userName">{user.display_name || user.username}</span>
                <span className="userHandle">@{user.username}</span>
              </div>
              <button className="logoutBtn" onClick={logout} disabled={authLoading} title="Sign out of your account">
                Sign Out
              </button>
            </>
          )}
          <button
            type="button"
            className="lanTagBtn"
            onClick={handleCopyIp}
            title="Click to copy host URL for other devices on your local network"
          >
            <span className="lanTagIcon">📡</span>
            <span className="lanTagText">{hostIp}</span>
            <span className="lanTagCopy">{copiedIp ? '✓ Copied!' : 'Copy'}</span>
          </button>
        </div>
      </header>

      {user && wsStatus !== 'connected' && (
        <div className={`networkBanner networkBanner_${wsStatus}`}>
          <span className="networkBannerText">
            {wsStatus === 'reconnecting'
              ? '⚠️ Connection lost. Attempting to reconnect to LAN server...'
              : wsStatus === 'connecting'
              ? '🔄 Connecting to LAN chat server...'
              : '❌ Disconnected from LAN server.'}
          </span>
          <button
            type="button"
            className="networkRetryBtn"
            onClick={reconnect}
          >
            Retry Now
          </button>
        </div>
      )}

      <main className="mainContent">
        {user ? (
          <div className="dashboard">
            <div className={`sidebarPane ${activeConvId ? 'sidebarPane_mobileHidden' : ''}`}>
              <ConversationList
                conversations={conversations}
                activeId={activeConvId}
                currentUserId={user.id}
                onlineUsers={onlineUsers}
                onSelect={(id) => setActiveConvId(id)}
                onOpenNewDialog={() => setIsNewDialogOpen(true)}
                loading={loadingConversations}
              />
            </div>

            <div className={`chatPane ${!activeConvId ? 'chatPane_mobileHidden' : ''}`}>
              {activeConversation ? (
                <ConversationView
                  key={activeConversation.id}
                  conversation={activeConversation}
                  currentUserId={user.id}
                  onlineUsers={onlineUsers}
                  lastMessage={lastMessage}
                  lastTypingUpdate={lastTypingUpdate}
                  lastReactionUpdate={lastReactionUpdate}
                  onSendMessage={sendMessage}
                  onSendTyping={sendTyping}
                  onConversationUpdated={(updated) => {
                    setConversations((prev) =>
                      prev.map((c) => (c.id === updated.id ? updated : c))
                    );
                  }}
                  onLeaveGroup={async () => {
                    await api.leaveGroup(activeConversation.id);
                    await loadConversations();
                    setActiveConvId(null);
                  }}
                  onBack={() => setActiveConvId(null)}
                />
              ) : (
                <div className="noChatSelected">
                  <div className="noChatIconWrapper">
                    <div className="noChatIcon">💬</div>
                  </div>
                  <h3 className="noChatTitle">Select a Conversation</h3>
                  <p className="noChatText">
                    Pick a conversation from the sidebar or start a new direct or group chat to begin real-time messaging.
                  </p>
                  <button
                    type="button"
                    className="noChatActionBtn"
                    onClick={() => setIsNewDialogOpen(true)}
                  >
                    + Start New Conversation
                  </button>

                  <div className="noChatFeatureGrid">
                    <div className="noChatFeatureItem">
                      <span className="noChatFeatureIcon">⚡</span>
                      <div>
                        <strong>Instant WebSockets</strong>
                        <p>Zero lag real-time messaging over local TCP</p>
                      </div>
                    </div>
                    <div className="noChatFeatureItem">
                      <span className="noChatFeatureIcon">📎</span>
                      <div>
                        <strong>File Sharing</strong>
                        <p>Share photos and documents up to 25MB locally</p>
                      </div>
                    </div>
                    <div className="noChatFeatureItem">
                      <span className="noChatFeatureIcon">👥</span>
                      <div>
                        <strong>Group Chats</strong>
                        <p>Create teams, manage admins, and assign roles</p>
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </div>

            <CreateConversationDialog
              isOpen={isNewDialogOpen}
              onClose={() => setIsNewDialogOpen(false)}
              onDirectCreated={handleDirectCreated}
              onGroupCreated={handleGroupCreated}
            />
          </div>
        ) : (
          <div className="landingContent">
            <div className="landingHero">
              <div className="landingBadge">
                <span className="landingBadgeDot" />
                <span>100% Offline Local Network Messaging</span>
              </div>
              <h2 className="landingTitle">Fast, Private LAN Chat</h2>
              <p className="landingSubtitle">
                Connect instantly with anyone on your local Wi-Fi or Ethernet network.
                Zero cloud servers, zero external telemetry, and completely self-hosted.
              </p>

              <div className="landingFeatureGrid">
                <div className="landingFeatureCard">
                  <div className="landingFeatureIcon">⚡</div>
                  <div className="landingFeatureTitle">Instant Messaging</div>
                  <div className="landingFeatureDesc">Ultra low-latency real-time chat powered by persistent TCP WebSockets.</div>
                </div>
                <div className="landingFeatureCard">
                  <div className="landingFeatureIcon">👥</div>
                  <div className="landingFeatureTitle">Direct &amp; Groups</div>
                  <div className="landingFeatureDesc">One-on-one direct messages or collaborative groups with admin permissions.</div>
                </div>
                <div className="landingFeatureCard">
                  <div className="landingFeatureIcon">📁</div>
                  <div className="landingFeatureTitle">Local File Sharing</div>
                  <div className="landingFeatureDesc">Send photos, PDFs, and documents up to 25MB directly between local devices.</div>
                </div>
              </div>
            </div>

            <div className="landingAuthCardWrapper">
              <AuthCard
                onLogin={login}
                onRegister={register}
                authError={authError}
                loading={authLoading}
                onClearError={clearError}
              />
            </div>
          </div>
        )}
      </main>
    </div>
  );
};

export default App;
