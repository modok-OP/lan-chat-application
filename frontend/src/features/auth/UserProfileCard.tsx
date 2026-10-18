import React from 'react';
import styles from './UserProfileCard.module.css';
import type { User } from '../../types';

interface UserProfileCardProps {
  user: User;
  onLogout: () => Promise<void>;
  loading: boolean;
}

export const UserProfileCard: React.FC<UserProfileCardProps> = ({
  user,
  onLogout,
  loading,
}) => {
  const initial = (user.display_name || user.username || '?').charAt(0);

  return (
    <div className={styles.card}>
      <div className={styles.header}>
        <div className={styles.userProfile}>
          <div className={styles.avatar}>{initial}</div>
          <div className={styles.userInfo}>
            <h3 className={styles.displayName}>{user.display_name}</h3>
            <p className={styles.username}>@{user.username}</p>
          </div>
        </div>

        <button
          className={styles.logoutBtn}
          onClick={() => onLogout()}
          disabled={loading}
        >
          {loading ? 'Logging out...' : 'Log Out'}
        </button>
      </div>

      <div className={styles.detailsGrid}>
        <div className={styles.detailItem}>
          <div className={styles.detailLabel}>User ID</div>
          <div className={styles.detailValue}>#{user.id}</div>
        </div>

        <div className={styles.detailItem}>
          <div className={styles.detailLabel}>Role</div>
          <div className={styles.detailValue}>{user.role}</div>
        </div>

        <div className={styles.detailItem}>
          <div className={styles.detailLabel}>Account Status</div>
          <div className={styles.detailValue}>
            {user.is_active ? 'Active' : 'Disabled'}
          </div>
        </div>

        <div className={styles.detailItem}>
          <div className={styles.detailLabel}>Member Since</div>
          <div className={styles.detailValue}>
            {new Date(user.created_at).toLocaleDateString()}
          </div>
        </div>
      </div>

      <div className={styles.milestoneSuccess}>
        <div className={styles.milestoneTitle}>
          Authenticated Session Active (Milestone 1 Completed)
        </div>
        <div>
          Your session cookie is active and verified by <code>GET /api/me</code>. Database persistence,
          Argon2 password hashing, and cookie management are operational.
        </div>
      </div>
    </div>
  );
};
