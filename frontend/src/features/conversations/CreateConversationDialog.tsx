import React, { useState, useEffect } from 'react';
import styles from './CreateConversationDialog.module.css';
import { api } from '../../lib/api';
import type { User } from '../../types';

interface CreateConversationDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onDirectCreated: (targetUserId: number) => Promise<void>;
  onGroupCreated: (name: string, memberIds: number[]) => Promise<void>;
}

export const CreateConversationDialog: React.FC<CreateConversationDialogProps> = ({
  isOpen,
  onClose,
  onDirectCreated,
  onGroupCreated,
}) => {
  const [activeTab, setActiveTab] = useState<'direct' | 'group'>('direct');
  const [search, setSearch] = useState('');
  const [users, setUsers] = useState<User[]>([]);
  const [loadingUsers, setLoadingUsers] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  // Group creation state
  const [groupName, setGroupName] = useState('');
  const [selectedUserIds, setSelectedUserIds] = useState<number[]>([]);

  useEffect(() => {
    if (!isOpen) return;

    let isMounted = true;
    const fetchUsers = async () => {
      try {
        setLoadingUsers(true);
        const results = await api.searchUsers(search.trim() || undefined);
        if (isMounted) setUsers(results);
      } catch (err) {
        console.error('Failed to search users:', err);
      } finally {
        if (isMounted) setLoadingUsers(false);
      }
    };

    const timer = setTimeout(fetchUsers, 200);
    return () => {
      isMounted = false;
      clearTimeout(timer);
    };
  }, [isOpen, search]);

  if (!isOpen) return null;

  const handleStartDirect = async (targetId: number) => {
    try {
      setSubmitting(true);
      await onDirectCreated(targetId);
      onClose();
    } finally {
      setSubmitting(false);
    }
  };

  const handleCreateGroup = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!groupName.trim()) return;

    try {
      setSubmitting(true);
      await onGroupCreated(groupName.trim(), selectedUserIds);
      onClose();
    } finally {
      setSubmitting(false);
    }
  };

  const toggleSelectUser = (id: number) => {
    setSelectedUserIds((prev) =>
      prev.includes(id) ? prev.filter((uid) => uid !== id) : [...prev, id]
    );
  };

  return (
    <div className={styles.overlay}>
      <div className={styles.modal}>
        <div className={styles.header}>
          <h3 className={styles.title}>New Conversation</h3>
          <button className={styles.closeBtn} onClick={onClose} aria-label="Close">
            &times;
          </button>
        </div>

        <div className={styles.tabs}>
          <button
            className={`${styles.tab} ${activeTab === 'direct' ? styles.tabActive : ''}`}
            onClick={() => setActiveTab('direct')}
          >
            Direct Message
          </button>
          <button
            className={`${styles.tab} ${activeTab === 'group' ? styles.tabActive : ''}`}
            onClick={() => setActiveTab('group')}
          >
            Create Group
          </button>
        </div>

        {activeTab === 'direct' ? (
          <div className={styles.body}>
            <div className={styles.inputGroup}>
              <label className={styles.label} htmlFor="user-search">
                Search Users on LAN
              </label>
              <input
                id="user-search"
                type="text"
                className={styles.input}
                placeholder="Search username or display name..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>

            <ul className={styles.userList}>
              {loadingUsers && <li className={styles.emptyMsg}>Searching users...</li>}
              {!loadingUsers && users.length === 0 && (
                <li className={styles.emptyMsg}>No other active users found.</li>
              )}
              {users.map((u) => (
                <li key={u.id} className={styles.userItem}>
                  <div className={styles.userInfo}>
                    <span className={styles.userName}>{u.display_name}</span>
                    <span className={styles.userHandle}>@{u.username}</span>
                  </div>
                  <button
                    className={styles.actionBtn}
                    onClick={() => handleStartDirect(u.id)}
                    disabled={submitting}
                  >
                    Chat
                  </button>
                </li>
              ))}
            </ul>
          </div>
        ) : (
          <form onSubmit={handleCreateGroup}>
            <div className={styles.body}>
              <div className={styles.inputGroup}>
                <label className={styles.label} htmlFor="group-name">
                  Group Name
                </label>
                <input
                  id="group-name"
                  type="text"
                  className={styles.input}
                  placeholder="e.g. Study Group, Project Alpha..."
                  value={groupName}
                  onChange={(e) => setGroupName(e.target.value)}
                  required
                />
              </div>

              <div className={styles.inputGroup}>
                <label className={styles.label}>Select Initial Members</label>
                <ul className={styles.userList}>
                  {loadingUsers && <li className={styles.emptyMsg}>Loading users...</li>}
                  {!loadingUsers && users.length === 0 && (
                    <li className={styles.emptyMsg}>No other users found on LAN.</li>
                  )}
                  {users.map((u) => {
                    const isChecked = selectedUserIds.includes(u.id);
                    return (
                      <li
                        key={u.id}
                        className={styles.checkboxItem}
                        onClick={() => toggleSelectUser(u.id)}
                      >
                        <input
                          type="checkbox"
                          checked={isChecked}
                          onChange={() => {}}
                        />
                        <div className={styles.userInfo}>
                          <span className={styles.userName}>{u.display_name}</span>
                          <span className={styles.userHandle}>@{u.username}</span>
                        </div>
                      </li>
                    );
                  })}
                </ul>
              </div>
            </div>

            <div className={styles.footer}>
              <button
                type="button"
                className={styles.cancelBtn}
                onClick={onClose}
              >
                Cancel
              </button>
              <button
                type="submit"
                className={styles.createBtn}
                disabled={submitting || !groupName.trim()}
              >
                {submitting ? 'Creating...' : 'Create Group'}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
};
