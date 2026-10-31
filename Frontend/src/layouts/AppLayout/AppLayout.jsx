import React, { useState } from 'react';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { useDispatch, useSelector } from 'react-redux';
import {
  LayoutDashboard,
  MessageSquare,
  FileText,
  Settings,
  LogOut,
  Menu,
  X,
  ChevronLeft,
  ChevronRight,
  BookOpen,
} from 'lucide-react';
import { logoutUser } from '../../store/slices/authSlice';
import { selectUser } from '../../store/slices/authSlice';
import { selectSidebarCollapsed, toggleSidebar } from '../../store/slices/uiSlice';
import { addToast } from '../../store/slices/uiSlice';
import styles from './AppLayout.module.css';

const NAV_ITEMS = [
  { to: '/app', icon: LayoutDashboard, label: 'Dashboard', end: true },
  { to: '/app/chat', icon: MessageSquare, label: 'AI Chat' },
  { to: '/app/documents', icon: FileText, label: 'Documents' },
  { to: '/app/settings', icon: Settings, label: 'Settings' },
];

// Derive the page title from the current nav item
function getPageTitle(pathname) {
  if (pathname === '/app') return 'Dashboard';
  if (pathname.startsWith('/app/chat')) return 'AI Learning Workspace';
  if (pathname.startsWith('/app/documents')) return 'Document Library';
  if (pathname.startsWith('/app/settings')) return 'Settings';
  return 'AI Learning Assistant';
}

function AppLayout() {
  const dispatch = useDispatch();
  const navigate = useNavigate();
  const user = useSelector(selectUser);
  const collapsed = useSelector(selectSidebarCollapsed);
  const [mobileOpen, setMobileOpen] = useState(false);

  const pathname = window.location.pathname;

  const handleLogout = async () => {
    try {
      await dispatch(logoutUser()).unwrap();
      dispatch(addToast({ type: 'success', message: 'Signed out successfully.' }));
    } catch {
      dispatch(
        addToast({
          type: 'warning',
          message: 'Signed out locally. Server could not be reached to invalidate session.',
        })
      );
    } finally {
      navigate('/login', { replace: true });
    }
  };

  const closeMobileMenu = () => setMobileOpen(false);

  // Get user initials for avatar
  const initials = user?.Name
    ? user.Name.split(' ').map((n) => n[0]).join('').slice(0, 2).toUpperCase()
    : '?';

  return (
    <div className={styles.shell}>
      {/* ── Sidebar ── */}
      <aside
        className={[
          styles.sidebar,
          collapsed ? styles.collapsed : '',
          mobileOpen ? styles.mobileOpen : '',
        ].filter(Boolean).join(' ')}
        aria-label="Application navigation"
      >
        {/* Collapse toggle (desktop only) */}
        <button
          className={styles.collapseBtn}
          onClick={() => dispatch(toggleSidebar())}
          aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          {collapsed ? <ChevronRight size={12} /> : <ChevronLeft size={12} />}
        </button>

        {/* Logo */}
        <NavLink to="/app" className={styles.sidebarLogo} onClick={closeMobileMenu}>
          <span className={styles.sidebarLogoMark} aria-hidden="true">
            <BookOpen size={16} color="#fdfbf7" />
          </span>
          {!collapsed && (
            <span className={styles.sidebarLogoText}>
              AI Learning<br />Assistant
            </span>
          )}
        </NavLink>

        {/* Navigation */}
        <nav className={styles.nav} aria-label="Primary navigation">
          {NAV_ITEMS.map(({ to, icon: Icon, label, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              onClick={closeMobileMenu}
              className={({ isActive }) =>
                [styles.navItem, isActive ? styles.active : ''].filter(Boolean).join(' ')
              }
              title={collapsed ? label : undefined}
              aria-label={label}
            >
              <Icon size={18} aria-hidden="true" />
              <span className={styles.navLabel}>{label}</span>
            </NavLink>
          ))}
        </nav>

        {/* Sidebar footer: user info + logout */}
        <div className={styles.sidebarFooter}>
          <div className={styles.sidebarUserInfo}>
            <div className={styles.userAvatar} aria-hidden="true">
              {initials}
            </div>
            <div className={styles.userMeta}>
              <p className={styles.userName}>{user?.Name || 'User'}</p>
              <p className={styles.userEmail}>{user?.Email || ''}</p>
            </div>
          </div>
          <button
            className={styles.logoutButton}
            onClick={handleLogout}
            title="Sign out"
            aria-label="Sign out"
          >
            <LogOut size={18} aria-hidden="true" />
            <span className={styles.logoutLabel}>Sign out</span>
          </button>
        </div>
      </aside>

      {/* Mobile overlay */}
      <div
        className={[styles.mobileOverlay, mobileOpen ? styles.visible : ''].filter(Boolean).join(' ')}
        onClick={closeMobileMenu}
        aria-hidden="true"
      />

      {/* ── Main Area ── */}
      <div className={[styles.main, collapsed ? styles.sidebarCollapsed : ''].filter(Boolean).join(' ')}>
        {/* Header */}
        <header className={styles.header}>
          <div className={styles.headerLeft}>
            <button
              className={styles.mobileMenuBtn}
              onClick={() => setMobileOpen(!mobileOpen)}
              aria-label={mobileOpen ? 'Close navigation menu' : 'Open navigation menu'}
              aria-expanded={mobileOpen}
            >
              {mobileOpen ? <X size={20} /> : <Menu size={20} />}
            </button>
            <h1 className={styles.pageTitle}>{getPageTitle(pathname)}</h1>
          </div>
          <div className={styles.headerRight}>
            <span className={styles.headerUserBadge} aria-label={`Signed in as ${user?.Name}`}>
              <div className={styles.userAvatar} aria-hidden="true" style={{ width: 28, height: 28, fontSize: '0.7rem' }}>
                {initials}
              </div>
            </span>
          </div>
        </header>

        {/* Page content */}
        <main className={styles.content}>
          <Outlet />
        </main>
      </div>
    </div>
  );
}

export default AppLayout;
