import React from 'react';
import styles from './LoadingScreen.module.css';

function LoadingScreen({ message = 'Loading...' }) {
  return (
    <div className={styles.screen} role="status" aria-live="polite">
      <div className={styles.logo}>
        <div className={styles.logoMark} aria-hidden="true">
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
            <path d="M4 10h12M10 4l6 6-6 6" stroke="#fdfbf7" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </div>
        <span className={styles.logoText}>AI Learning Assistant</span>
      </div>
      <div className={styles.spinner} aria-hidden="true" />
      <p className={styles.message}>{message}</p>
    </div>
  );
}

export default LoadingScreen;
