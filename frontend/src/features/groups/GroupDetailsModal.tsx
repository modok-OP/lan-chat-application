import React, { useState, useEffect } from 'react';
import styles from './GroupDetailsModal.module.css';
import { api } from '../../lib/api';
import type { Conversation, MemberSummary, User } from '../../types';

interface GroupDetailsModalProps {
  isOpen: boolean;
  onClose: () => void;
  conversation: Conversation;
  currentUserId: number;
  onlineUsers?: Set<number>;
  onConversationUpdated: (updatedConv: Conversation) => void;
  onLeaveGroup: () => Promise<void>;
}

export const GroupDetailsModal: React.FC<GroupDetailsModalProps> = ({
  isOpen,
  onClose,
  conversation,
  currentUserId,
  onlineUsers = new Set(),
  onConversationUpdated,
  onLeaveGroup,
}) => {
  const [isEditingName, setIsEditingName] = useState(false);
  const [newName, setNewName] = useState(conversation.name || '');
  const [isAddingMember, setIsAddingMember] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [candidateUsers, setCandidateUsers] = useState<User[]>([]);
  const [selectedRole, setSelectedRole] = useState<'member' | 'admin'>('member');
  const [loadingSearch, setLoadingSearch] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Sync newName when conversation changes
  useEffect(() => {
    setNewName(conversation.name || '');
    setError(null);
  }, [conversation]);

  // Search candidate users when add member is open
  useEffect(() => {
    if (!isAddingMember) return;

    let isMounted = true;
    const fetchCandidates = async () => {
      try {
        setLoadingSearch(true);
        const results = await api.searchUsers(searchQuery.trim() || undefined);
        if (isMounted) {
          // Filter out users who are already active members
          const activeMemberUserIds = new Set(
            conversation.members.filter((m) => m.is_active).map((m) => m.user_id)
          );
          setCandidateUsers(results.filter((u) => !activeMemberUserIds.has(u.id)));
        }
      } catch (err) {
        console.error('Failed to search candidate users:', err);
      } finally {
        if (isMounted) setLoadingSearch(false);
      }
    };

    const timer = setTimeout(fetchCandidates, 200);
    return () => {
      isMounted = false;
      clearTimeout(timer);
    };
  }, [isAddingMember, searchQuery, conversation.members]);

  if (!isOpen) return null;

  const currentMember = conversation.members.find((m) => m.user_id === currentUserId);
  const isOwner = currentMember?.role === 'owner';
  const isAdmin = currentMember?.role === 'admin';
  const canManage = isOwner || isAdmin;

  const activeMembers = conversation.members.filter((m) => m.is_active);
  const otherMembersCount = activeMembers.filter((m) => m.user_id !== currentUserId).length;

  const handleSaveName = async () => {
    const clean = newName.trim();
    if (!clean || clean === conversation.name) {
      setIsEditingName(false);
      return;
    }

    try {
      setActionLoading(true);
      setError(null);
      const updated = await api.renameGroup(conversation.id, clean);
      onConversationUpdated(updated);
      setIsEditingName(false);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to rename group');
    } finally {
      setActionLoading(false);
    }
  };

  const handleAddMember = async (userId: number) => {
    try {
      setActionLoading(true);
      setError(null);
      await api.addGroupMember(conversation.id, userId, selectedRole);
      const refreshed = await api.getConversation(conversation.id);
      onConversationUpdated(refreshed);
      setSearchQuery('');
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to add member');
    } finally {
      setActionLoading(false);
    }
  };

  const handleRemoveMember = async (member: MemberSummary) => {
    if (!window.confirm(`Are you sure you want to remove ${member.display_name} from the group?`)) {
      return;
    }

    try {
      setActionLoading(true);
      setError(null);
      await api.removeGroupMember(conversation.id, member.user_id);
      const refreshed = await api.getConversation(conversation.id);
      onConversationUpdated(refreshed);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to remove member');
    } finally {
      setActionLoading(false);
    }
  };

  const handleToggleRole = async (member: MemberSummary) => {
    const targetRole = member.role === 'admin' ? 'member' : 'admin';
    try {
      setActionLoading(true);
      setError(null);
      await api.addGroupMember(conversation.id, member.user_id, targetRole);
      const refreshed = await api.getConversation(conversation.id);
      onConversationUpdated(refreshed);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to change member role');
    } finally {
      setActionLoading(false);
    }
  };

  const handleTransferOwnership = async (member: MemberSummary) => {
    if (
      !window.confirm(
        `Are you sure you want to transfer ownership of this group to ${member.display_name}? You will become an admin.`
      )
    ) {
      return;
    }

    try {
      setActionLoading(true);
      setError(null);
      const updated = await api.transferOwnership(conversation.id, member.user_id);
      onConversationUpdated(updated);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to transfer ownership');
    } finally {
      setActionLoading(false);
    }
  };

  const handleLeaveGroup = async () => {
    if (!window.confirm('Are you sure you want to leave this group?')) {
      return;
    }

    try {
      setActionLoading(true);
      setError(null);
      await onLeaveGroup();
      onClose();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to leave group');
    } finally {
      setActionLoading(false);
    }
  };

  const getInitials = (name: string): string => {
    return name.slice(0, 2).toUpperCase();
  };

  return (
    <div className={styles.overlay}>
      <div className={styles.modal}>
        <div className={styles.header}>
          <div className={styles.titleArea}>
            {isEditingName ? (
              <>
                <input
                  type="text"
                  className={styles.renameInput}
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  autoFocus
                  disabled={actionLoading}
                />
                <button
                  className={`${styles.renameActionBtn} ${styles.saveBtn}`}
                  onClick={handleSaveName}
                  disabled={actionLoading || !newName.trim()}
                >
                  Save
                </button>
                <button
                  className={`${styles.renameActionBtn} ${styles.cancelBtn}`}
                  onClick={() => {
                    setIsEditingName(false);
                    setNewName(conversation.name || '');
                  }}
                  disabled={actionLoading}
                >
                  Cancel
                </button>
              </>
            ) : (
              <>
                <h3 className={styles.title}>{conversation.name || 'Group Chat'}</h3>
                {canManage && (
                  <button
                    className={styles.editNameBtn}
                    onClick={() => setIsEditingName(true)}
                    title="Rename Group"
                  >
                    ✏️ Rename
                  </button>
                )}
              </>
            )}
          </div>
          <button className={styles.closeBtn} onClick={onClose} aria-label="Close">
            &times;
          </button>
        </div>

        <div className={styles.body}>
          {error && <div className={styles.errorMsg}>{error}</div>}

          <div className={styles.metaCard}>
            <span>
              <strong>{activeMembers.length}</strong> active members
            </span>
            <span className={styles.myRoleBadge}>
              Your role:{' '}
              {isOwner ? '👑 Owner' : isAdmin ? '⭐ Admin' : 'Member'}
            </span>
          </div>

          <div className={styles.sectionHeader}>
            <h4 className={styles.sectionTitle}>Members</h4>
            {canManage && (
              <button
                className={styles.toggleAddBtn}
                onClick={() => setIsAddingMember(!isAddingMember)}
              >
                {isAddingMember ? 'Hide Search' : '+ Add Members'}
              </button>
            )}
          </div>

          {isAddingMember && (
            <div className={styles.addMemberCard}>
              <div className={styles.addInputRow}>
                <input
                  type="text"
                  className={styles.addSearchInput}
                  placeholder="Search user to add..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                />
                {isOwner && (
                  <select
                    className={styles.roleSelect}
                    value={selectedRole}
                    onChange={(e) => setSelectedRole(e.target.value as 'member' | 'admin')}
                  >
                    <option value="member">Member</option>
                    <option value="admin">Admin</option>
                  </select>
                )}
              </div>

              <ul className={styles.candidateList}>
                {loadingSearch && <li className={styles.candidateItem}>Searching users...</li>}
                {!loadingSearch && candidateUsers.length === 0 && (
                  <li className={styles.candidateItem}>
                    No eligible users found on LAN.
                  </li>
                )}
                {candidateUsers.map((u) => (
                  <li key={u.id} className={styles.candidateItem}>
                    <div>
                      <strong>{u.display_name}</strong> <small>@{u.username}</small>
                    </div>
                    <button
                      className={styles.candidateAddBtn}
                      onClick={() => handleAddMember(u.id)}
                      disabled={actionLoading}
                    >
                      Add
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}

          <ul className={styles.memberList}>
            {activeMembers.map((member) => {
              const isSelf = member.user_id === currentUserId;
              const isMemberOnline = onlineUsers.has(member.user_id);
              const isTargetOwner = member.role === 'owner';
              const isTargetAdmin = member.role === 'admin';

              return (
                <li key={member.user_id} className={styles.memberItem}>
                  <div className={styles.memberLeft}>
                    <div className={styles.avatarWrapper}>
                      <div className={styles.avatar}>{getInitials(member.display_name)}</div>
                      {isMemberOnline && <span className={styles.onlineDot} title="Online" />}
                    </div>

                    <div className={styles.memberInfo}>
                      <div className={styles.memberNameRow}>
                        <span className={styles.memberName}>
                          {member.display_name} {isSelf && '(You)'}
                        </span>
                        <span
                          className={
                            isTargetOwner
                              ? styles.roleBadge_owner
                              : isTargetAdmin
                              ? styles.roleBadge_admin
                              : styles.roleBadge_member
                          }
                        >
                          {isTargetOwner ? 'Owner 👑' : isTargetAdmin ? 'Admin ⭐' : 'Member'}
                        </span>
                      </div>
                      <span className={styles.memberHandle}>@{member.username}</span>
                    </div>
                  </div>

                  {!isSelf && canManage && (
                    <div className={styles.memberActions}>
                      {isOwner && (
                        <>
                          <button
                            className={styles.actionBtn}
                            onClick={() => handleTransferOwnership(member)}
                            disabled={actionLoading}
                            title="Make Owner"
                          >
                            👑 Transfer
                          </button>
                          <button
                            className={styles.actionBtn}
                            onClick={() => handleToggleRole(member)}
                            disabled={actionLoading}
                            title={isTargetAdmin ? 'Demote to Member' : 'Promote to Admin'}
                          >
                            {isTargetAdmin ? 'Demote' : 'Promote'}
                          </button>
                        </>
                      )}

                      {/* Remove button: Owner can remove non-owners; Admin can only remove non-admins */}
                      {(isOwner || (!isTargetAdmin && !isTargetOwner)) && (
                        <button
                          className={`${styles.actionBtn} ${styles.removeBtn}`}
                          onClick={() => handleRemoveMember(member)}
                          disabled={actionLoading}
                          title="Remove from group"
                        >
                          Remove
                        </button>
                      )}
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        </div>

        <div className={styles.footer}>
          <button
            className={styles.leaveBtn}
            onClick={handleLeaveGroup}
            disabled={actionLoading || (isOwner && otherMembersCount > 0)}
            title={
              isOwner && otherMembersCount > 0
                ? 'Transfer group ownership before leaving'
                : 'Leave group'
            }
          >
            {isOwner && otherMembersCount > 0
              ? 'Transfer Ownership to Leave'
              : 'Leave Group'}
          </button>

          <button className={styles.actionBtn} onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
