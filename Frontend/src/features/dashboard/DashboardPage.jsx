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
          Your AI-powered learning assistant is ready. Upload study materials and
          ask questions — every answer is grounded in your documents.
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
            relevant passages and provides source-cited answers.
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
            Add PDF documents to your knowledge base. The assistant will index
            them and answer questions from their content.
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
            Upload your textbooks, lecture notes, or any PDF study material. The
            system processes and indexes the content into a searchable knowledge base.
          </p>
        </div>

        <div className={styles.infoCard}>
          <div className={styles.infoCardHeader}>
            <MessageSquare size={20} className={styles.infoCardIcon} aria-hidden="true" />
            <p className={styles.infoCardTitle}>2. Ask Questions</p>
          </div>
          <p className={styles.infoCardText}>
            Type your question in plain language. The system retrieves the most
            relevant sections from your uploaded documents.
          </p>
        </div>

        <div className={styles.infoCard}>
          <div className={styles.infoCardHeader}>
            <BookOpen size={20} className={styles.infoCardIcon} aria-hidden="true" />
            <p className={styles.infoCardTitle}>3. Get Cited Answers</p>
          </div>
          <p className={styles.infoCardText}>
            Receive AI-generated answers backed by specific passages from your
            materials, with source filenames and page numbers.
          </p>
        </div>

        <div className={styles.infoCard}>
          <div className={styles.infoCardHeader}>
            <Database size={20} className={styles.infoCardIcon} aria-hidden="true" />
            <p className={styles.infoCardTitle}>Persistent Knowledge Base</p>
          </div>
          <p className={styles.infoCardText}>
            Uploaded documents persist in the knowledge base across sessions.
            The vector index is rebuilt automatically when new materials are added.
          </p>
        </div>

        <div className={styles.infoCard}>
          <div className={styles.infoCardHeader}>
            <Zap size={20} className={styles.infoCardIcon} aria-hidden="true" />
            <p className={styles.infoCardTitle}>RAG-Powered AI</p>
          </div>
          <p className={styles.infoCardText}>
            Retrieval-Augmented Generation combines semantic search with Gemini's
            language model — answers come from your documents, not generic knowledge.
          </p>
        </div>
      </div>

      {/* ── Development Notice ── */}
      <div className={styles.notice} role="note" aria-label="Platform status notice">
        <Info size={18} className={styles.noticeIcon} aria-hidden="true" />
        <p className={styles.noticeText}>
          <strong>Active Development Notice:</strong> This platform currently supports
          PDF upload, knowledge base indexing, and RAG-powered Q&A with source citations.
          Personalized learning profiles, ML recommendations, and assessment tracking
          are planned for future releases.
        </p>
      </div>
    </div>
  );
}

export default DashboardPage;
