import { useState, useEffect, useCallback } from 'react';
import { api } from '../lib/api';
import { ApiError } from '../types';
import type { User, LoginPayload, RegisterPayload } from '../types';

export interface UseAuthReturn {
  user: User | null;
  loading: boolean;
  authError: string | null;
  login: (payload: LoginPayload) => Promise<User>;
  register: (payload: RegisterPayload) => Promise<User>;
  logout: () => Promise<void>;
  clearError: () => void;
  refreshUser: () => Promise<void>;
}

export function useAuth(): UseAuthReturn {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [authError, setAuthError] = useState<string | null>(null);

  const refreshUser = useCallback(async () => {
    try {
      setLoading(true);
      const currentUser = await api.getCurrentUser();
      setUser(currentUser);
      setAuthError(null);
    } catch (err: unknown) {
      // 401 is normal for unauthenticated state; do not log an error banner
      if (err instanceof ApiError && err.status === 401) {
        setUser(null);
      } else if (err instanceof Error) {
        setAuthError(err.message);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshUser();
  }, [refreshUser]);

  const login = async (payload: LoginPayload): Promise<User> => {
    try {
      setLoading(true);
      setAuthError(null);
      const authenticatedUser = await api.login(payload);
      setUser(authenticatedUser);
      return authenticatedUser;
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Login failed';
      setAuthError(msg);
      throw err;
    } finally {
      setLoading(false);
    }
  };

  const register = async (payload: RegisterPayload): Promise<User> => {
    try {
      setLoading(true);
      setAuthError(null);
      const newUser = await api.register(payload);
      setUser(newUser);
      return newUser;
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Registration failed';
      setAuthError(msg);
      throw err;
    } finally {
      setLoading(false);
    }
  };

  const logout = async (): Promise<void> => {
    try {
      setLoading(true);
      await api.logout();
      setUser(null);
      setAuthError(null);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Logout failed';
      setAuthError(msg);
      throw err;
    } finally {
      setLoading(false);
    }
  };

  const clearError = () => setAuthError(null);

  return {
    user,
    loading,
    authError,
    login,
    register,
    logout,
    clearError,
    refreshUser,
  };
}
