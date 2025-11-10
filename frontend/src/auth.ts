/**
 * Authentication utilities
 * 인증 유틸리티
 */

const TOKEN_KEY = 'arbitrage_token';

export interface AuthToken {
  access_token: string;
  token_type: string;
}

export interface UserInfo {
  id: number;
  email: string;
  full_name: string | null;
  is_active: boolean;
  is_superuser: boolean;
}

/**
 * Save auth token to localStorage
 * 인증 토큰을 로컬스토리지에 저장
 */
export function saveToken(token: AuthToken): void {
  localStorage.setItem(TOKEN_KEY, JSON.stringify(token));
}

/**
 * Get auth token from localStorage
 * 로컬스토리지에서 인증 토큰 가져오기
 */
export function getToken(): AuthToken | null {
  const stored = localStorage.getItem(TOKEN_KEY);
  if (!stored) return null;

  try {
    return JSON.parse(stored);
  } catch {
    return null;
  }
}

/**
 * Remove auth token from localStorage
 * 로컬스토리지에서 인증 토큰 제거
 */
export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

/**
 * Check if user is authenticated
 * 사용자 인증 여부 확인
 */
export function isAuthenticated(): boolean {
  return getToken() !== null;
}

/**
 * Get authorization header for API requests
 * API 요청용 인증 헤더 가져오기
 */
export function getAuthHeader(): Record<string, string> {
  const token = getToken();
  if (!token) return {};

  return {
    'Authorization': `${token.token_type} ${token.access_token}`
  };
}
