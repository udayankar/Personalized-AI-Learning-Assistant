import React from 'react';
import { useDispatch, useSelector } from 'react-redux';
import { useNavigate } from 'react-router-dom';
import {
  User,
  Shield,
  Activity,
  LogOut,
  Database,
  Cpu,
  CheckCircle2,
  Info,
} from 'lucide-react';
import { selectUser, logoutUser } from '../../store/slices/authSlice';
import { addToast } from '../../store/slices/uiSlice';
import Button from '../../components/Button/Button';
import styles from './SettingsPage.module.css';

export default function SettingsPage() {
  const dispatch = useDispatch();
  const navigate = useNavigate();
  const user = useSelector(selectUser);

  const handleLogout = async () => {
    await dispatch(logoutUser());
    dispatch(addToast({ type: 'success', message: 'You have been signed out successfully.' }));
    navigate('/login', { replace: true });
  };

  const formattedDate = user?.Created_at
    ? new Date(user.Created_at).toLocaleDateString(undefined, {
        year: 'numeric',
        month: 'long',
        day: 'numeric',
      })
    : 'Active session';

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h1 className={styles.title}>Account &amp; Platform Settings</h1>
        <p className={styles.subtitle}>
          View your authenticated account information and platform configuration.
        </p>
      </div>

      {/* ── User Profile Section ────────────────────────────── */}
      <section className={styles.section} aria-label="User profile">
        <div className={styles.sectionHeader}>
          <User size={20} className={styles.sectionIcon} aria-hidden="true" />
          <h2 className={styles.sectionTitle}>User Profile</h2>
        </div>

        <div className={styles.profileGrid}>
          <div className={styles.profileItem}>
            <span className={styles.profileLabel}>Account Name</span>
            <span className={styles.profileValue}>{user?.Name || 'Learner'}</span>
          </div>

          <div className={styles.profileItem}>
            <span className={styles.profileLabel}>Email Address</span>
            <span className={styles.profileValue}>{user?.Email || 'Not available'}</span>
          </div>

          <div className={styles.profileItem}>
            <span className={styles.profileLabel}>User ID</span>
            <span className={styles.profileValue}>#{user?.ID ?? '—'}</span>
          </div>

          <div className={styles.profileItem}>
            <span className={styles.profileLabel}>Member Since</span>
            <span className={styles.profileValue}>{formattedDate}</span>
          </div>

          <div className={styles.profileItem}>
            <span className={styles.profileLabel}>Authentication Status</span>
            <div className={styles.profileBadge}>
              <CheckCircle2 size={12} aria-hidden="true" />
              <span>HttpOnly Session Active</span>
            </div>
          </div>
        </div>

        <p className={styles.noticeText}>
          <Info size={12} style={{ display: 'inline', marginRight: '4px' }} />
          Profile editing and password change endpoints are in active development and will be enabled
          in a future backend release.
        </p>
      </section>

      {/* ── Platform Architecture & Diagnostics ─────────────── */}
      <section className={styles.section} aria-label="System diagnostics">
        <div className={styles.sectionHeader}>
          <Activity size={20} className={styles.sectionIcon} aria-hidden="true" />
          <h2 className={styles.sectionTitle}>System Architecture &amp; Diagnostics</h2>
        </div>

        <div className={styles.diagnosticList}>
          <div className={styles.diagnosticRow}>
            <span className={styles.diagnosticKey}>Backend API Base URL</span>
            <span className={styles.diagnosticValue}>
              {process.env.API_BASE_URL || 'http://localhost:8000'}
            </span>
          </div>

          <div className={styles.diagnosticRow}>
            <span className={styles.diagnosticKey}>Authentication Mechanism</span>
            <span className={styles.diagnosticValue}>JWT via HttpOnly Cookie (access_token)</span>
          </div>

          <div className={styles.diagnosticRow}>
            <span className={styles.diagnosticKey}>Vector Database Index</span>
            <span className={styles.diagnosticValue}>FAISS (IndexFlatL2)</span>
          </div>

          <div className={styles.diagnosticRow}>
            <span className={styles.diagnosticKey}>AI Generation Model</span>
            <span className={styles.diagnosticValue}>Google Gemini (gemini-3.6-flash)</span>
          </div>

          <div className={styles.diagnosticRow}>
            <span className={styles.diagnosticKey}>Document Ingestion Pipeline</span>
            <span className={styles.diagnosticValue}>PyPDF Loader + Recursive Text Chunker</span>
          </div>
        </div>
      </section>

      {/* ── Session & Sign Out ──────────────────────────────── */}
      <section className={styles.section} aria-label="Session management">
        <div className={styles.sectionHeader}>
          <Shield size={20} className={styles.sectionIcon} aria-hidden="true" />
          <h2 className={styles.sectionTitle}>Session Management</h2>
        </div>

        <p style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)', margin: 0 }}>
          Signing out terminates your authenticated session cookie and clears in-memory study state.
        </p>

        <div className={styles.logoutArea}>
          <Button
            type="button"
            variant="danger"
            size="md"
            onClick={handleLogout}
          >
            <LogOut size={16} style={{ marginRight: '8px' }} />
            Sign Out of Account
          </Button>
        </div>
      </section>
    </div>
  );
}
