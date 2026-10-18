import React, { useState } from 'react';
import styles from './AuthCard.module.css';
import type { LoginPayload, RegisterPayload } from '../../types';

interface AuthCardProps {
  onLogin: (payload: LoginPayload) => Promise<unknown>;
  onRegister: (payload: RegisterPayload) => Promise<unknown>;
  authError: string | null;
  loading: boolean;
  onClearError: () => void;
}

export const AuthCard: React.FC<AuthCardProps> = ({
  onLogin,
  onRegister,
  authError,
  loading,
  onClearError,
}) => {
  const [activeTab, setActiveTab] = useState<'login' | 'register'>('login');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [localError, setLocalError] = useState<string | null>(null);

  const handleTabChange = (tab: 'login' | 'register') => {
    setActiveTab(tab);
    setLocalError(null);
    onClearError();
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLocalError(null);

    const cleanUsername = username.trim();
    if (!cleanUsername) {
      setLocalError('Please enter a username.');
      return;
    }

    if (activeTab === 'register') {
      if (cleanUsername.length < 3 || cleanUsername.length > 30) {
        setLocalError('Username must be between 3 and 30 characters.');
        return;
      }
      if (!/^[a-zA-Z0-9_]+$/.test(cleanUsername)) {
        setLocalError('Username can only contain letters, numbers, and underscores.');
        return;
      }
      if (password.length < 8) {
        setLocalError('Password must be at least 8 characters.');
        return;
      }

      try {
        await onRegister({
          username: cleanUsername,
          password,
          display_name: displayName.trim() || undefined,
        });
      } catch {
        // Error is set in parent auth state
      }
    } else {
      if (!password) {
        setLocalError('Please enter your password.');
        return;
      }

      try {
        await onLogin({
          username: cleanUsername,
          password,
        });
      } catch {
        // Error is set in parent auth state
      }
    }
  };

  const displayedError = localError || authError;

  return (
    <div className={styles.container}>
      <div className={styles.tabs}>
        <button
          type="button"
          className={`${styles.tab} ${activeTab === 'login' ? styles.tabActive : ''}`}
          onClick={() => handleTabChange('login')}
        >
          Sign In
        </button>
        <button
          type="button"
          className={`${styles.tab} ${activeTab === 'register' ? styles.tabActive : ''}`}
          onClick={() => handleTabChange('register')}
        >
          Create Account
        </button>
      </div>

      <form className={styles.formContent} onSubmit={handleSubmit} noValidate>
        {displayedError && (
          <div className={styles.errorAlert} role="alert">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10"></circle>
              <line x1="12" y1="8" x2="12" y2="12"></line>
              <line x1="12" y1="16" x2="12.01" y2="16"></line>
            </svg>
            <span>{displayedError}</span>
          </div>
        )}

        <div className={styles.formGroup}>
          <label className={styles.label} htmlFor="auth-username">
            Username
          </label>
          <input
            id="auth-username"
            type="text"
            className={styles.input}
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder="e.g. alice"
            autoComplete="username"
            disabled={loading}
            required
          />
          {activeTab === 'register' && (
            <span className={styles.helperText}>
              3–30 characters (letters, numbers, underscores)
            </span>
          )}
        </div>

        {activeTab === 'register' && (
          <div className={styles.formGroup}>
            <label className={styles.label} htmlFor="auth-display-name">
              Display Name (Optional)
            </label>
            <input
              id="auth-display-name"
              type="text"
              className={styles.input}
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              placeholder="e.g. Alice Wonderland"
              disabled={loading}
            />
          </div>
        )}

        <div className={styles.formGroup}>
          <label className={styles.label} htmlFor="auth-password">
            Password
          </label>
          <input
            id="auth-password"
            type="password"
            className={styles.input}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="••••••••"
            autoComplete={activeTab === 'login' ? 'current-password' : 'new-password'}
            disabled={loading}
            required
          />
          {activeTab === 'register' && (
            <span className={styles.helperText}>Minimum 8 characters</span>
          )}
        </div>

        <button
          type="submit"
          className={styles.submitBtn}
          disabled={loading}
        >
          {loading
            ? 'Processing...'
            : activeTab === 'login'
            ? 'Log In'
            : 'Register & Sign In'}
        </button>

        <div className={styles.footerInfo}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect>
            <path d="M7 11V7a5 5 0 0 1 10 0v4"></path>
          </svg>
          <span>Secured with Argon2id &amp; local server session cookies</span>
        </div>
      </form>
    </div>
  );
};
