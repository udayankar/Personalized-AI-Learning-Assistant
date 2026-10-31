import React from 'react';
import { AlertCircle, CheckCircle2, AlertTriangle, Info, X } from 'lucide-react';
import styles from './Alert.module.css';

const ICONS = {
  error: AlertCircle,
  success: CheckCircle2,
  warning: AlertTriangle,
  info: Info,
};

export default function Alert({ type = 'info', message, children, onDismiss, className = '' }) {
  const Icon = ICONS[type] || Info;
  const content = message || children;

  if (!content) return null;

  return (
    <div
      className={`${styles.alert} ${styles[type] || styles.info} ${className}`}
      role={type === 'error' ? 'alert' : 'status'}
      aria-live="polite"
    >
      <Icon size={18} className={styles.icon} aria-hidden="true" />
      <div className={styles.message}>{content}</div>
      {onDismiss && (
        <button
          type="button"
          onClick={onDismiss}
          className={styles.dismissBtn}
          aria-label="Dismiss alert"
        >
          <X size={14} aria-hidden="true" />
        </button>
      )}
    </div>
  );
}
