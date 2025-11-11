import { useState } from 'react';
import { login, register, type LoginRequest, type RegisterRequest } from './api';
import { saveToken } from './auth';

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
    <div className="modal modal-open" onClick={onClose}>
      <div className="modal-box max-w-md bg-base-200 border border-base-300 shadow-2xl" onClick={(e) => e.stopPropagation()}>
        {/* Close Button */}
        <button
          className="btn btn-sm btn-circle btn-ghost absolute right-4 top-4"
          onClick={onClose}
        >
          ✕
        </button>

        {/* Title */}
        <h2 className="text-2xl font-bold text-white mb-6">
          {mode === 'login' ? '🔐 Login / 로그인' : '👤 Register / 회원가입'}
        </h2>

        {/* Form */}
        <form onSubmit={handleSubmit} className="space-y-4">
          {mode === 'register' && (
            <div className="form-control">
              <label htmlFor="fullName" className="label">
                <span className="label-text">
                  Full Name / 이름 (optional)
                </span>
              </label>
              <input
                id="fullName"
                type="text"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                placeholder="John Doe"
                className="input input-bordered bg-base-300 w-full focus:input-primary"
              />
            </div>
          )}

          <div className="form-control">
            <label htmlFor="email" className="label">
              <span className="label-text">
                📧 Email / 이메일 *
              </span>
            </label>
            <input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              placeholder="user@example.com"
              className="input input-bordered bg-base-300 w-full focus:input-primary"
            />
          </div>

          <div className="form-control">
            <label htmlFor="password" className="label">
              <span className="label-text">
                🔒 Password / 비밀번호 *
              </span>
            </label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              placeholder="••••••••"
              minLength={6}
              className="input input-bordered bg-base-300 w-full focus:input-primary"
            />
            <label className="label">
              <span className="label-text-alt text-base-content/60">
                Minimum 6 characters / 최소 6자
              </span>
            </label>
          </div>

          {error && (
            <div className="alert alert-error">
              <span className="text-sm">⚠️ {error}</span>
            </div>
          )}

          <button
            type="submit"
            className="btn btn-primary w-full"
            disabled={isLoading}
          >
            {isLoading ? (
              <>
                <span className="loading loading-spinner loading-sm"></span>
                Processing...
              </>
            ) : (
              mode === 'login' ? 'Login / 로그인' : 'Register / 회원가입'
            )}
          </button>
        </form>

        {/* Mode Toggle */}
        <div className="divider"></div>
        <div className="text-center">
          <button
            type="button"
            onClick={() => {
              setMode(mode === 'login' ? 'register' : 'login');
              setError(null);
            }}
            className="btn btn-ghost btn-sm text-primary"
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
