import React from 'react';

export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error('ErrorBoundary caught an unhandled error:', error, errorInfo);
  }

  handleReload = () => {
    window.location.reload();
  };

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

      return (
        <div
          style={{
            minHeight: '100vh',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            backgroundColor: '#fdfbf7',
            color: '#1a365d',
            fontFamily: 'Inter, sans-serif',
            padding: '24px',
            textAlign: 'center',
          }}
          role="alert"
        >
          <div
            style={{
              width: '64px',
              height: '64px',
              borderRadius: '16px',
              backgroundColor: '#fee2e2',
              color: '#b91c1c',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: '28px',
              marginBottom: '20px',
            }}
          >
            ⚠️
          </div>
          <h1
            style={{
              fontFamily: 'Lora, serif',
              fontSize: '28px',
              fontWeight: 700,
              marginBottom: '12px',
              color: '#1a365d',
            }}
          >
            Something unexpected occurred
          </h1>
          <p
            style={{
              fontSize: '15px',
              color: '#4a5568',
              maxWidth: '460px',
              lineHeight: 1.6,
              marginBottom: '28px',
            }}
          >
            An application error occurred. We apologize for the disruption. You can reload the page to restore your study session.
          </p>
          <button
            onClick={this.handleReload}
            style={{
              backgroundColor: '#d97706',
              color: '#ffffff',
              border: 'none',
              borderRadius: '9999px',
              padding: '12px 28px',
              fontSize: '15px',
              fontWeight: 600,
              cursor: 'pointer',
              boxShadow: '0 4px 14px rgba(217, 119, 6, 0.35)',
            }}
          >
            Reload Application
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}
