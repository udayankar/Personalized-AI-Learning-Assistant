import React, { useEffect } from 'react';
import { useSelector, useDispatch } from 'react-redux';
import { AlertCircle, CheckCircle2, AlertTriangle, Info, X } from 'lucide-react';
import { selectToasts, removeToast } from '../../store/slices/uiSlice';
import styles from './Toast.module.css';

const ICONS = {
  error: AlertCircle,
  success: CheckCircle2,
  warning: AlertTriangle,
  info: Info,
};

function ToastItem({ toast }) {
  const dispatch = useDispatch();
  const Icon = ICONS[toast.type] || Info;

  useEffect(() => {
    if (toast.duration) {
      const timer = setTimeout(() => {
        dispatch(removeToast(toast.id));
      }, toast.duration);
      return () => clearTimeout(timer);
    }
  }, [toast.id, toast.duration, dispatch]);

  return (
    <div
      className={`${styles.toast} ${styles[toast.type] || styles.info}`}
      role="status"
      aria-live="polite"
    >
      <Icon size={18} className={styles.toastIcon} aria-hidden="true" />
      <div className={styles.toastMessage}>{toast.message}</div>
      <button
        type="button"
        className={styles.dismissBtn}
        onClick={() => dispatch(removeToast(toast.id))}
        aria-label="Close notification"
      >
        <X size={14} aria-hidden="true" />
      </button>
    </div>
  );
}

export default function ToastContainer() {
  const toasts = useSelector(selectToasts);

  if (!toasts || toasts.length === 0) return null;

  return (
    <div className={styles.toastContainer} aria-label="Notifications" role="region">
      {toasts.map((toast) => (
        <ToastItem key={toast.id} toast={toast} />
      ))}
    </div>
  );
}
