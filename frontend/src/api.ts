/**
 * API client utilities
 * API 클라이언트 유틸리티
 */

import { API_HTTP_BASE } from './config';
import { getAuthHeader, clearToken } from './auth';

/**
 * Make an authenticated API request with timeout
 * 타임아웃이 있는 인증된 API 요청 실행
 */
export async function apiRequest<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `${API_HTTP_BASE}${endpoint}`;

  const headers = {
    'Content-Type': 'application/json',
    ...getAuthHeader(),
    ...options.headers,
  };

  // Create AbortController for timeout
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 10000); // 10 second timeout

  try {
    const response = await fetch(url, {
      ...options,
      headers,
      signal: controller.signal,
    });

    clearTimeout(timeoutId);

    // Handle auth errors
    if (response.status === 401) {
      clearToken();
      throw new Error('Unauthorized - please login / 인증되지 않음 - 로그인하세요');
    }

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
      throw new Error(errorData.detail || `HTTP ${response.status}`);
    }

    return response.json();
  } catch (error) {
    clearTimeout(timeoutId);

    if (error instanceof Error && error.name === 'AbortError') {
      throw new Error('Request timeout - please try again / 요청 시간 초과 - 다시 시도하세요');
    }

    throw error;
  }
}

/**
 * Execute an opportunity
 * 기회 실행
 */
export interface ExecuteOpportunityRequest {
  opportunity_id: string;
  dry_run?: boolean;
}

export interface ExecuteOpportunityResponse {
  status: string;
  opportunity_id: string;
  message: string;
  orders: Array<{
    id: number;
    exchange: string;
    symbol: string;
    side: string;
    quantity: number;
    status: string;
  }>;
}

export async function executeOpportunity(
  request: ExecuteOpportunityRequest
): Promise<ExecuteOpportunityResponse> {
  return apiRequest<ExecuteOpportunityResponse>('/execution/execute', {
    method: 'POST',
    body: JSON.stringify(request),
  });
}

/**
 * Get portfolio summary
 * 포트폴리오 요약 조회
 */
export async function getPortfolioSummary(): Promise<any> {
  return apiRequest('/portfolio/summary');
}

/**
 * Login
 * 로그인
 */
export interface LoginRequest {
  email: string;
  password: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
}

export async function login(credentials: LoginRequest): Promise<LoginResponse> {
  const response = await fetch(`${API_HTTP_BASE}/auth/login`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(credentials),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Login failed' }));
    throw new Error(error.detail);
  }

  return response.json();
}

/**
 * Register
 * 회원가입
 */
export interface RegisterRequest {
  email: string;
  password: string;
  full_name?: string;
}

export async function register(data: RegisterRequest): Promise<any> {
  const response = await fetch(`${API_HTTP_BASE}/auth/register`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(data),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Registration failed' }));
    throw new Error(error.detail);
  }

  return response.json();
}

/**
 * Position management
 * 포지션 관리
 */

export interface Position {
  id: number;
  opportunity_id: string;
  position_type: string;
  symbol: string;
  status: string;
  entry_time: string;
  entry_notional: number;
  current_pnl_pct: number;
  current_pnl_usd: number;
  target_profit_pct: number;
  stop_loss_pct: number;
  entry_legs: Array<{
    exchange: string;
    venue_type: string;
    side: string;
    price: number;
    quantity: number;
  }>;
  exit_legs?: Array<any>;
  exit_time?: string;
  realized_pnl_pct?: number;
  realized_pnl_usd?: number;
  exit_reason?: string;
  last_update?: string;
}

export interface PositionListResponse {
  count: number;
  positions: Position[];
}

export interface PositionStatsResponse {
  total_positions: number;
  open_positions: number;
  closed_positions: number;
  total_pnl_usd: number;
  open_pnl_usd: number;
  realized_pnl_usd: number;
  win_rate: number;
  avg_pnl_pct: number;
}

export async function getPositions(status?: string): Promise<PositionListResponse> {
  const params = status ? `?status=${status}` : '';
  return apiRequest<PositionListResponse>(`/positions/list${params}`);
}

export async function getPositionStats(): Promise<PositionStatsResponse> {
  return apiRequest<PositionStatsResponse>('/positions/summary/stats');
}

export async function closePosition(positionId: number): Promise<any> {
  return apiRequest('/positions/close', {
    method: 'POST',
    body: JSON.stringify({ position_id: positionId }),
  });
}
