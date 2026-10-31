import React from 'react';
import styles from './Badge.module.css';

export default function Badge({ variant = 'default', children, className = '' }) {
  return (
    <span className={`${styles.badge} ${styles[variant] || styles.default} ${className}`}>
      {children}
    </span>
  );
}
