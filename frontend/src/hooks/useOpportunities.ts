import { useEffect, useMemo, useState } from "react";
import { API_HTTP_BASE, API_WS_BASE } from "../config";
import type { Opportunity } from "../types";

interface UseOpportunitiesResult {
  opportunities: Opportunity[];
  isLoading: boolean;
  error: string | null;
  lastUpdated: Date | null;
}

const WS_ENDPOINT = `${API_WS_BASE}/ws/opportunities`;
const HTTP_ENDPOINT = `${API_HTTP_BASE}/opportunities`;

export function useOpportunities(): UseOpportunitiesResult {
  const [opportunities, setOpportunities] = useState<Opportunity[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  useEffect(() => {
    let ws: WebSocket | null = null;
    let timeoutId: number | null = null;
    let cancelled = false;

    const fetchInitial = async () => {
      try {
        const response = await fetch(HTTP_ENDPOINT);
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        const data: Opportunity[] = await response.json();
        if (!cancelled) {
          setOpportunities(data);
          setLastUpdated(new Date());
        }
      } catch (err) {
        console.error("Failed to load opportunities:", err);
        if (!cancelled) {
          setError("Failed to load opportunities / 기회를 불러오지 못했습니다.");
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    };

    const connectWs = () => {
      ws = new WebSocket(WS_ENDPOINT);
      ws.onmessage = (event) => {
        try {
          const data: Opportunity[] = JSON.parse(event.data);
          setOpportunities(data);
          setLastUpdated(new Date());
          setError(null);
        } catch (err) {
          console.error("Malformed websocket payload:", err);
        }
      };
      ws.onopen = () => setError(null);
      ws.onerror = () => {
        setError("Realtime connection error / 실시간 연결 오류");
      };
      ws.onclose = () => {
        if (cancelled) {
          return;
        }
        timeoutId = window.setTimeout(connectWs, 3000);
      };
    };

    fetchInitial();
    connectWs();

    return () => {
      cancelled = true;
      if (timeoutId) {
        window.clearTimeout(timeoutId);
      }
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.close();
      }
    };
  }, []);

  return useMemo(
    () => ({
      opportunities,
      isLoading,
      error,
      lastUpdated,
    }),
    [opportunities, isLoading, error, lastUpdated],
  );
}
