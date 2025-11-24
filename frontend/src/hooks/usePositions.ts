import { useState, useEffect } from 'react';
import { getPositions, getPositionStats } from '../api';
import type { Position, PositionStatsResponse } from '../api';
import { isAuthenticated } from '../auth';

export function usePositions() {
  const [positions, setPositions] = useState<Position[]>([]);
  const [stats, setStats] = useState<PositionStatsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isAuthenticated()) {
      setLoading(false);
      return;
    }

    const fetchPositions = async () => {
      try {
        setError(null);
        const [positionsData, statsData] = await Promise.all([
          getPositions('open'), // Only fetch open positions
          getPositionStats(),
        ]);

        setPositions(positionsData.positions);
        setStats(statsData);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to fetch positions');
        console.error('Error fetching positions:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchPositions();

    // Poll every 5 seconds
    const interval = setInterval(fetchPositions, 5000);

    return () => clearInterval(interval);
  }, []);

  return { positions, stats, loading, error };
}
