/**
 * Protected Route Guard
 *
 * Redirects unauthenticated users to /login.
 * Preserves the attempted destination so users can be
 * returned there after successful login.
 *
 * Shows a loading spinner while session check is in progress.
 */

import React from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useSelector } from 'react-redux';
import { selectIsAuthenticated, selectAuthStatus, selectIsAuthInitialized } from '../store/slices/authSlice';
import LoadingScreen from '../components/LoadingScreen/LoadingScreen';

function ProtectedRoute({ children }) {
  const isAuthenticated = useSelector(selectIsAuthenticated);
  const isInitialized = useSelector(selectIsAuthInitialized);
  const status = useSelector(selectAuthStatus);
  const location = useLocation();

  // Wait for initial session check to complete before deciding route access
  if (!isInitialized || (status === 'loading' && !isAuthenticated)) {
    return <LoadingScreen message="Checking your session..." />;
  }

  if (!isAuthenticated) {
    // Preserve the intended destination for post-login redirect
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  return children;
}

export default ProtectedRoute;
