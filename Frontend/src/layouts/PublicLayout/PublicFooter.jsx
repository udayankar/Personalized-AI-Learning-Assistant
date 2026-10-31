import React from 'react';
import { Link } from 'react-router-dom';
import { BookOpenCheck } from 'lucide-react';
import styles from './PublicFooter.module.css';

/**
 * PublicFooter
 * Navy background footer with:
 * – Left column: logo + tagline
 * – Right column: nav links (Sign In, Get Started)
 * – Bottom row: copyright
 */
export default function PublicFooter() {
  const year = new Date().getFullYear();

  return (
    <footer className={styles.footer} role="contentinfo">
      <div className={styles.inner}>
        {/* ── Main columns ─────────────────────────────────── */}
        <div className={styles.columns}>
          {/* Left: brand */}
          <div className={styles.brand}>
            <Link to="/" className={styles.logo} aria-label="AI Learning Assistant home">
              <span className={styles.logoIcon} aria-hidden="true">
                <BookOpenCheck size={20} strokeWidth={2.2} />
              </span>
              <span className={styles.logoText}>AI Learning Assistant</span>
            </Link>
            <p className={styles.tagline}>
              RAG-powered Q&amp;A grounded in your own study materials.
              Ask anything — get cited answers.
            </p>
          </div>

          {/* Right: links */}
          <nav className={styles.links} aria-label="Footer navigation">
            <p className={styles.linksHeading}>Quick Links</p>
            <Link to="/login" className={styles.link}>Sign In</Link>
            <Link to="/signup" className={styles.linkCta}>Get Started</Link>
          </nav>
        </div>

        {/* ── Divider ──────────────────────────────────────── */}
        <div className={styles.divider} aria-hidden="true" />

        {/* ── Copyright ────────────────────────────────────── */}
        <p className={styles.copyright}>
          &copy; {year} AI Learning Assistant. Built to help you learn smarter.
        </p>
      </div>
    </footer>
  );
}
