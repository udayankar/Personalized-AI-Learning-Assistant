import React from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft, Home } from 'lucide-react';
import styles from './NotFoundPage.module.css';

export default function NotFoundPage() {
  return (
    <div className={styles.container} role="region" aria-label="Page not found">
      <div className={styles.code}>404</div>
      <h1 className={styles.title}>Academic Page Not Found</h1>
      <p className={styles.description}>
        The study page or resource you requested could not be located. It may have been relocated or
        does not exist in the assistant repository.
      </p>

      <div className={styles.actions}>
        <Link
          to="/"
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '8px',
            backgroundColor: 'var(--color-navy-800)',
            color: 'var(--color-cream-50)',
            padding: '10px 20px',
            borderRadius: '9999px',
            fontSize: '14px',
            fontWeight: 600,
            textDecoration: 'none',
          }}
        >
          <Home size={16} />
          <span>Return Home</span>
        </Link>
        <Link
          to="/app"
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '8px',
            backgroundColor: 'var(--color-amber-600)',
            color: '#ffffff',
            padding: '10px 20px',
            borderRadius: '9999px',
            fontSize: '14px',
            fontWeight: 600,
            textDecoration: 'none',
          }}
        >
          <span>Open Dashboard</span>
        </Link>
      </div>
    </div>
  );
}
