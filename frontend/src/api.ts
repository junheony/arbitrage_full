/**
 * API client utilities
 * API 클라이언트 유틸리티
 */

import { API_HTTP_BASE } from './config';
import { getAuthHeader, clearToken } from './auth';

/**
 * Make an authenticated API request
 * 인증된 API 요청 실행
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

  const response = await fetch(url, {
    ...options,
    headers,
  });

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
