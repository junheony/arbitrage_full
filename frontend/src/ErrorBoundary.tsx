import { Component } from 'react';
import type { ErrorInfo, ReactNode } from 'react';

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false,
    error: null
  };

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('Uncaught error:', error, errorInfo);
  }

  public render() {
    if (this.state.hasError) {
      return (
        <div style={{
          padding: '40px',
          maxWidth: '600px',
          margin: '100px auto',
          textAlign: 'center',
          background: '#1e1e1e',
          borderRadius: '8px',
          border: '1px solid #ef4444'
        }}>
          <h1 style={{ color: '#ef4444', marginBottom: '16px' }}>
            ⚠️ Something went wrong / 오류가 발생했습니다
          </h1>
          <p style={{ color: '#9ca3af', marginBottom: '24px' }}>
            The application encountered an error. Please refresh the page.
            <br />
            애플리케이션에서 오류가 발생했습니다. 페이지를 새로고침하세요.
          </p>
          {this.state.error && (
            <details style={{
              background: '#2d2d2d',
              padding: '16px',
              borderRadius: '4px',
              textAlign: 'left',
              marginBottom: '24px'
            }}>
              <summary style={{ cursor: 'pointer', color: '#ef4444', marginBottom: '8px' }}>
                Error Details / 오류 상세
              </summary>
              <pre style={{
                fontSize: '12px',
                color: '#9ca3af',
                overflow: 'auto',
                maxHeight: '200px'
              }}>
                {this.state.error.toString()}
                {'\n'}
                {this.state.error.stack}
              </pre>
            </details>
          )}
          <button
            onClick={() => window.location.reload()}
            style={{
              padding: '12px 24px',
              background: '#3b82f6',
              color: 'white',
              border: 'none',
              borderRadius: '4px',
              cursor: 'pointer',
              fontSize: '16px'
            }}
          >
            Reload Page / 페이지 새로고침
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary;
