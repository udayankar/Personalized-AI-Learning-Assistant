import React from 'react';
import { Link } from 'react-router-dom';
import { useSelector } from 'react-redux';
import {
  MessageSquare,
  FileUp,
  BookOpen,
  Database,
  ArrowRight,
  Info,
  Zap,
} from 'lucide-react';
import { selectUser } from '../../store/slices/authSlice';
import styles from './DashboardPage.module.css';

function DashboardPage() {
  const user = useSelector(selectUser);
  const firstName = user?.Name?.split(' ')[0] || 'Learner';

  // Friendly time-of-day greeting
  const hour = new Date().getHours();
  const timeGreeting =
    hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening';

  return (
    <div className={styles.page}>
      {/* ── Welcome Banner ── */}
      <div className={styles.welcome} role="region" aria-label="Welcome section">
        <p className={styles.welcomeGreeting}>{timeGreeting}</p>
        <h2 className={styles.welcomeTitle}>Welcome back, {firstName}.</h2>
        <p className={styles.welcomeSubtitle}>
          Your AI-powered learning assistant is ready. Upload study materials and ask questions.
          Answers use retrieved passages from your documents. If the documents do not contain relevant
          information, the assistant will say so instead of filling gaps from general knowledge.
        </p>
      </div>

      {/* ── Quick Actions ── */}
      <h3 className={styles.sectionTitle}>Start Studying</h3>
      <div className={styles.actionsGrid}>
        <Link
          to="/app/chat"
          className={styles.actionCard}
          aria-label="Go to AI Chat workspace"
        >
          <div className={`${styles.actionIconWrap} ${styles.chat}`}>
            <MessageSquare size={24} aria-hidden="true" />
          </div>
          <p className={styles.actionCardTitle}>Ask a Question</p>
          <p className={styles.actionCardDesc}>
            Ask anything about your study materials. The AI assistant retrieves
            relevant passages and can include source references when document evidence is available.
          </p>
          <span className={styles.actionArrow} aria-hidden="true">
            <ArrowRight size={18} />
          </span>
        </Link>

        <Link
          to="/app/documents"
          className={styles.actionCard}
          aria-label="Go to Document upload"
        >
          <div className={`${styles.actionIconWrap} ${styles.docs}`}>
            <FileUp size={24} aria-hidden="true" />
          </div>
          <p className={styles.actionCardTitle}>Upload Study Material</p>
          <p className={styles.actionCardDesc}>
            Add text-based PDFs to your account's search index. Scanned PDFs are not currently OCR-processed.
          </p>
          <span className={styles.actionArrow} aria-hidden="true">
            <ArrowRight size={18} />
          </span>
        </Link>
      </div>

      {/* ── How It Works ── */}
      <h3 className={styles.sectionTitle}>How It Works</h3>
      <div className={styles.infoGrid}>
        <div className={styles.infoCard}>
          <div className={styles.infoCardHeader}>
            <FileUp size={20} className={styles.infoCardIcon} aria-hidden="true" />
            <p className={styles.infoCardTitle}>1. Upload Documents</p>
          </div>
          <p className={styles.infoCardText}>
            Upload text-based textbooks, lecture notes, or other PDFs. Scanned PDFs are not currently
            OCR-processed. Extracted text is added to your account's searchable index.
          </p>
        </div>

        <div className={styles.infoCard}>
          <div className={styles.infoCardHeader}>
            <MessageSquare size={20} className={styles.infoCardIcon} aria-hidden="true" />
            <p className={styles.infoCardTitle}>2. Ask Questions</p>
          </div>
          <p className={styles.infoCardText}>
            Type your question in plain language. The system retrieves the most
            relevant sections from your uploaded documents when available.
          </p>
        </div>

        <div className={styles.infoCard}>
          <div className={styles.infoCardHeader}>
            <BookOpen size={20} className={styles.infoCardIcon} aria-hidden="true" />
            <p className={styles.infoCardTitle}>3. Review Answers and Sources</p>
          </div>
          <p className={styles.infoCardText}>
            Answers may include excerpts from your documents, with filenames and page details when available.
          </p>
        </div>

        <div className={styles.infoCard}>
          <div className={styles.infoCardHeader}>
            <Database size={20} className={styles.infoCardIcon} aria-hidden="true" />
            <p className={styles.infoCardTitle}>Account-Specific Document Storage</p>
          </div>
          <p className={styles.infoCardText}>
            PDFs and their search index are stored on the server's local filesystem. They remain available
            across sessions while that storage is retained; persistence across deployments depends on the host.
            New uploads are added to the index after processing.
          </p>
        </div>

        <div className={styles.infoCard}>
          <div className={styles.infoCardHeader}>
            <Zap size={20} className={styles.infoCardIcon} aria-hidden="true" />
            <p className={styles.infoCardTitle}>RAG-Powered AI</p>
          </div>
          <p className={styles.infoCardText}>
            Gemini helps assess and explain retrieved passages, but factual answer claims must be supported
            by those passages. If no relevant support is found, the assistant reports that limitation.
          </p>
        </div>
      </div>

      {/* ── Development Notice ── */}
      <div className={styles.notice} role="note" aria-label="Platform status notice">
        <Info size={18} className={styles.noticeIcon} aria-hidden="true" />
        <p className={styles.noticeText}>
          <strong>Platform Status:</strong> This platform currently supports
          PDF upload, knowledge base indexing, and RAG-powered Q&amp;A with source references when available.
          Personalized learning profiles, ML recommendations, and assessment tracking
          are planned for future releases.
        </p>
      </div>
    </div>
  );
}

export default DashboardPage;
