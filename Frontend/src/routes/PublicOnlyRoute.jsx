/**
 * Public-Only Route Guard
 *
 * Redirects already-authenticated users away from login/signup
 * back to the application dashboard.
 *
 * Shows loading state while session check is in progress
 * to prevent flickering the login page briefly for auth users.
 */

import React from 'react';
import { Navigate } from 'react-router-dom';
import { useSelector } from 'react-redux';
import { selectIsAuthenticated, selectIsAuthInitialized } from '../store/slices/authSlice';
import LoadingScreen from '../components/LoadingScreen/LoadingScreen';

function PublicOnlyRoute({ children }) {
  const isAuthenticated = useSelector(selectIsAuthenticated);
  const isInitialized = useSelector(selectIsAuthInitialized);

  if (!isInitialized) {
    return <LoadingScreen message="Loading..." />;
  }

  if (isAuthenticated) {
    return <Navigate to="/app" replace />;
  }

  return children;
}

export default PublicOnlyRoute;
