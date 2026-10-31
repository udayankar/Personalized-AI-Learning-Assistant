import React from 'react';
import { Outlet } from 'react-router-dom';
import PublicNavbar from './PublicNavbar';
import PublicFooter from './PublicFooter';
import styles from './PublicLayout.module.css';

/**
 * PublicLayout
 * Shell for all public routes (landing, login, signup).
 * Renders: <PublicNavbar> → <main><Outlet /></main> → <PublicFooter>
 */
export default function PublicLayout() {
  return (
    <>
      <PublicNavbar />
      <main className={styles.main}>
        <Outlet />
      </main>
      <PublicFooter />
    </>
  );
}
