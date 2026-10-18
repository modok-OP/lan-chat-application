import { useState, useEffect, useCallback } from 'react';
import { api } from '../lib/api';
import type { HealthResponse } from '../types';

export interface UseHealthReturn {
  health: HealthResponse | null;
  loading: boolean;
  error: string | null;
  refetch: () => Promise<void>;
}

export function useHealth(autoRefreshIntervalMs: number = 10000): UseHealthReturn {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const fetchHealth = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await api.getHealth();
      setHealth(data);
    } catch (err: unknown) {
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError('Failed to reach backend API');
      }
      setHealth(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchHealth();

    if (autoRefreshIntervalMs > 0) {
      const interval = setInterval(fetchHealth, autoRefreshIntervalMs);
      return () => clearInterval(interval);
    }
  }, [fetchHealth, autoRefreshIntervalMs]);

  return { health, loading, error, refetch: fetchHealth };
}
