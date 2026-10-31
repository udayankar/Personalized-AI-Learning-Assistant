import React from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';

// Layouts
import PublicLayout from '../layouts/PublicLayout/PublicLayout';
import AppLayout from '../layouts/AppLayout/AppLayout';

// Route Guards
import ProtectedRoute from './ProtectedRoute';
import PublicOnlyRoute from './PublicOnlyRoute';

// Feature Pages
import LandingPage from '../features/landing/LandingPage';
import LoginPage from '../features/auth/LoginPage';
import SignupPage from '../features/auth/SignupPage';
import DashboardPage from '../features/dashboard/DashboardPage';
import ChatWorkspacePage from '../features/chat/ChatWorkspacePage';
import DocumentLibraryPage from '../features/documents/DocumentLibraryPage';
import SettingsPage from '../features/settings/SettingsPage';
import NotFoundPage from '../features/notfound/NotFoundPage';
import ToastContainer from '../components/Toast/ToastContainer';

export default function AppRoutes() {
  return (
    <>
      <Routes>
        {/* ── Public Routes (Navbar + Footer) ── */}
        <Route path="/" element={<PublicLayout />}>
          <Route index element={<LandingPage />} />
          <Route
            path="login"
            element={
              <PublicOnlyRoute>
                <LoginPage />
              </PublicOnlyRoute>
            }
          />
          <Route
            path="signup"
            element={
              <PublicOnlyRoute>
                <SignupPage />
              </PublicOnlyRoute>
            }
          />
          <Route path="*" element={<NotFoundPage />} />
        </Route>

        {/* ── Authenticated Routes (App Shell) ── */}
        <Route
          path="/app"
          element={
            <ProtectedRoute>
              <AppLayout />
            </ProtectedRoute>
          }
        >
          <Route index element={<DashboardPage />} />
          <Route path="chat" element={<ChatWorkspacePage />} />
          <Route path="documents" element={<DocumentLibraryPage />} />
          <Route path="settings" element={<SettingsPage />} />
        </Route>
      </Routes>
      <ToastContainer />
    </>
  );
}
