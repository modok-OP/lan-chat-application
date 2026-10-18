import React from 'react';
import { useHealth } from '../hooks/useHealth';
import styles from './HealthStatus.module.css';

export const HealthStatus: React.FC = () => {
  const { health, loading, error, refetch } = useHealth(8000);

  const getStatusBadge = () => {
    if (error || !health) {
      return (
        <span className={`${styles.badge} ${styles.badgeError}`}>
          <span className={styles.dot} /> Offline
        </span>
      );
    }
    if (health.status === 'healthy' && health.database === 'connected') {
      return (
        <span className={`${styles.badge} ${styles.badgeHealthy}`}>
          <span className={styles.dot} /> Healthy
        </span>
      );
    }
    return (
      <span className={`${styles.badge} ${styles.badgeDegraded}`}>
        <span className={styles.dot} /> {health.status}
      </span>
    );
  };

  return (
    <div className={styles.container}>
      <div className={styles.card}>
        <div className={styles.header}>
          <h2 className={styles.title}>System Diagnostics (Milestone 0)</h2>
          {getStatusBadge()}
        </div>

        {error && (
          <div className={styles.errorBanner}>
            <strong>Connection Failed:</strong> {error}. Ensure FastAPI backend is running on port 8000.
          </div>
        )}

        <div className={styles.grid}>
          <div className={styles.statItem}>
            <div className={styles.statLabel}>Backend API</div>
            <div className={styles.statValue}>
              {loading && !health ? 'Checking...' : health ? 'Online' : 'Unreachable'}
            </div>
          </div>

          <div className={styles.statItem}>
            <div className={styles.statLabel}>SQLite Database</div>
            <div className={styles.statValue}>
              {health?.database === 'connected' ? 'Connected (aiosqlite)' : health?.database || 'Disconnected'}
            </div>
          </div>

          <div className={styles.statItem}>
            <div className={styles.statLabel}>Application Version</div>
            <div className={styles.statValue}>{health?.version || '0.1.0'}</div>
          </div>

          <div className={styles.statItem}>
            <div className={styles.statLabel}>Environment</div>
            <div className={styles.statValue}>{health?.environment || 'development'}</div>
          </div>
        </div>

        <div className={styles.footer}>
          <div>
            Last checked:{' '}
            <span className={styles.timestamp}>
              {health?.timestamp ? new Date(health.timestamp).toLocaleTimeString() : 'N/A'}
            </span>
          </div>
          <button
            className={styles.refreshButton}
            onClick={() => refetch()}
            disabled={loading}
          >
            {loading ? 'Refreshing...' : 'Recheck Status'}
          </button>
        </div>
      </div>

      <div className={styles.infoCard}>
        <div className={styles.infoTitle}>LAN Readiness Verification</div>
        <ul className={styles.infoList}>
          <li><strong>Architecture:</strong> Client-Server over TCP/IP (FastAPI backend + React SPA frontend).</li>
          <li><strong>Zero Cloud Dependencies:</strong> No remote CDNs, no external auth, and fully local disk persistence.</li>
          <li><strong>Real-time Pathway:</strong> WebSockets ready for Milestone 3 (/ws endpoint).</li>
          <li><strong>Next Step:</strong> Milestone 1 (Account registration, login, Argon2 password hashing, session cookies).</li>
        </ul>
      </div>
    </div>
  );
};
