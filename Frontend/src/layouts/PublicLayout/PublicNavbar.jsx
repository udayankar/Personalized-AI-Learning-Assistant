import React, { useState, useEffect, useRef } from 'react';
import { Link } from 'react-router-dom';
import { Menu, X, BookOpenCheck } from 'lucide-react';
import styles from './PublicNavbar.module.css';

/**
 * PublicNavbar
 * Fixed sticky navigation for all public pages.
 * – Navy background, cream text
 * – Logo (amber icon + serif brand name)
 * – Desktop: Sign In link + Get Started amber button
 * – Mobile: hamburger → dropdown with same links
 */
export default function PublicNavbar() {
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef(null);

  /* Close dropdown when clicking outside */
  useEffect(() => {
    function handleClickOutside(e) {
      if (menuRef.current && !menuRef.current.contains(e.target)) {
        setMenuOpen(false);
      }
    }
    if (menuOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [menuOpen]);

  /* Close on route changes */
  const closeMenu = () => setMenuOpen(false);

  return (
    <header className={styles.navbar} role="banner">
      <div className={styles.inner}>
        {/* ── Logo ─────────────────────────────────────────── */}
        <Link to="/" className={styles.logo} onClick={closeMenu} aria-label="AI Learning Assistant home">
          <span className={styles.logoIcon} aria-hidden="true">
            <BookOpenCheck size={22} strokeWidth={2.2} />
          </span>
          <span className={styles.logoText}>AI Learning Assistant</span>
        </Link>

        {/* ── Desktop Nav ──────────────────────────────────── */}
        <nav className={styles.desktopNav} aria-label="Main navigation">
          <Link to="/login" className={styles.navLink}>
            Sign In
          </Link>
          <Link to="/signup" className={styles.ctaButton}>
            Get Started
          </Link>
        </nav>

        {/* ── Mobile Hamburger ─────────────────────────────── */}
        <button
          className={styles.hamburger}
          onClick={() => setMenuOpen((prev) => !prev)}
          aria-label={menuOpen ? 'Close menu' : 'Open menu'}
          aria-expanded={menuOpen}
          aria-controls="mobile-menu"
        >
          {menuOpen ? <X size={24} /> : <Menu size={24} />}
        </button>
      </div>

      {/* ── Mobile Dropdown ──────────────────────────────────── */}
      {menuOpen && (
        <nav
          id="mobile-menu"
          className={styles.mobileMenu}
          ref={menuRef}
          aria-label="Mobile navigation"
        >
          <Link to="/login" className={styles.mobileLink} onClick={closeMenu}>
            Sign In
          </Link>
          <Link to="/signup" className={styles.mobileCtaButton} onClick={closeMenu}>
            Get Started
          </Link>
        </nav>
      )}
    </header>
  );
}
