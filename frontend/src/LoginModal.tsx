import { useState } from 'react';
import { login, register, type LoginRequest, type RegisterRequest } from './api';
import { saveToken } from './auth';
import './LoginModal.css';

interface LoginModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

export function LoginModal({ isOpen, onClose, onSuccess }: LoginModalProps) {
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [fullName, setFullName] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setError(null);

    try {
      if (mode === 'login') {
        const credentials: LoginRequest = { email, password };
        const response = await login(credentials);
        saveToken(response);
        onSuccess();
      } else {
        const data: RegisterRequest = { email, password, full_name: fullName || undefined };
        await register(data);
        // Auto-login after registration
        const response = await login({ email, password });
        saveToken(response);
        onSuccess();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <button className="modal-close" onClick={onClose}>✕</button>

        <h2>{mode === 'login' ? 'Login / 로그인' : 'Register / 회원가입'}</h2>

        <form onSubmit={handleSubmit}>
          {mode === 'register' && (
            <div className="form-group">
              <label htmlFor="fullName">Full Name / 이름 (optional)</label>
              <input
                id="fullName"
                type="text"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                placeholder="John Doe"
              />
            </div>
          )}

          <div className="form-group">
            <label htmlFor="email">Email / 이메일 *</label>
            <input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              placeholder="user@example.com"
            />
          </div>

          <div className="form-group">
            <label htmlFor="password">Password / 비밀번호 *</label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              placeholder="••••••••"
              minLength={6}
            />
          </div>

          {error && <div className="form-error">{error}</div>}

          <button type="submit" className="form-submit" disabled={isLoading}>
            {isLoading ? '⏳ Processing...' : mode === 'login' ? 'Login / 로그인' : 'Register / 회원가입'}
          </button>
        </form>

        <div className="form-footer">
          <button
            type="button"
            onClick={() => {
              setMode(mode === 'login' ? 'register' : 'login');
              setError(null);
            }}
            className="mode-toggle"
          >
            {mode === 'login'
              ? '계정이 없으신가요? 회원가입 / No account? Register'
              : '이미 계정이 있으신가요? 로그인 / Have an account? Login'}
          </button>
        </div>
      </div>
    </div>
  );
}
