/**
 * Authentication Redux Slice
 *
 * Manages:
 * - Current user profile from GET /users/me
 * - Session status (idle → loading → authenticated/unauthenticated)
 * - Login, signup, session check, and logout operations
 *
 * SECURITY:
 * - No JWT tokens, passwords, or credentials stored in state
 * - Authentication state is derived exclusively from backend session checks
 * - User profile data (name, email, ID) is safe to store in Redux
 */

import { createSlice, createAsyncThunk } from '@reduxjs/toolkit';
import { signup as signupAPI, login as loginAPI, getMe, logout as logoutAPI } from '../../services/authService';

// ─── Async Thunks ─────────────────────────────────────────────

/**
 * Check for an existing authenticated session at app startup.
 * Calls GET /users/me — returns null if no valid session.
 */
export const checkAuth = createAsyncThunk('auth/checkAuth', async () => {
  const user = await getMe();
  return user; // null if unauthenticated
});

/**
 * Log in with email and password.
 * On success, immediately fetches /users/me to populate the profile.
 */
export const loginUser = createAsyncThunk(
  'auth/loginUser',
  async ({ Email, Password }, { dispatch, rejectWithValue }) => {
    try {
      await loginAPI({ Email, Password });
      // Cookie is now set — fetch user profile
      const user = await getMe();
      return user;
    } catch (error) {
      return rejectWithValue(error.message);
    }
  }
);

/**
 * Register a new account, then automatically log in.
 * Signup does not set the auth cookie — we must login explicitly after.
 */
export const signupUser = createAsyncThunk(
  'auth/signupUser',
  async ({ Name, Email, Password }, { dispatch, rejectWithValue }) => {
    try {
      await signupAPI({ Name, Email, Password });
      // Signup succeeded — now log in to establish the session
      await loginAPI({ Email, Password });
      const user = await getMe();
      return user;
    } catch (error) {
      return rejectWithValue(error.message);
    }
  }
);

/**
 * Log out the current user.
 * Clears the server-side cookie; Redux state is cleared immediately.
 */
export const logoutUser = createAsyncThunk(
  'auth/logoutUser',
  async (_, { rejectWithValue }) => {
    try {
      const data = await logoutAPI();
      return data;
    } catch (error) {
      return rejectWithValue(error.message || 'Logout failed on server');
    }
  }
);

// ─── Slice ────────────────────────────────────────────────────

const authSlice = createSlice({
  name: 'auth',
  initialState: {
    user: null,           // { ID, Name, Email, Created_at }
    isAuthenticated: false,
    status: 'idle',       // 'idle' | 'loading' | 'succeeded' | 'failed'
    isInitialized: false, // true once initial session check resolves
    error: null,
    currentRequestId: null,
  },
  reducers: {
    clearError(state) {
      state.error = null;
    },
  },
  extraReducers: (builder) => {
    // ── checkAuth ──
    builder
      .addCase(checkAuth.pending, (state, action) => {
        state.status = 'loading';
        state.currentRequestId = action.meta.requestId;
      })
      .addCase(checkAuth.fulfilled, (state, action) => {
        if (action.meta.requestId !== state.currentRequestId) return;
        state.isInitialized = true;
        state.status = 'succeeded';
        state.currentRequestId = null;
        if (action.payload) {
          state.user = action.payload;
          state.isAuthenticated = true;
        } else {
          state.user = null;
          state.isAuthenticated = false;
        }
      })
      .addCase(checkAuth.rejected, (state, action) => {
        if (action.meta.requestId !== state.currentRequestId) return;
        state.isInitialized = true;
        state.status = 'failed';
        state.isAuthenticated = false;
        state.user = null;
        state.currentRequestId = null;
      });

    // ── loginUser ──
    builder
      .addCase(loginUser.pending, (state, action) => {
        state.status = 'loading';
        state.error = null;
        state.currentRequestId = action.meta.requestId;
      })
      .addCase(loginUser.fulfilled, (state, action) => {
        if (action.meta.requestId !== state.currentRequestId) return;
        state.isInitialized = true;
        state.status = 'succeeded';
        state.user = action.payload;
        state.isAuthenticated = true;
        state.error = null;
        state.currentRequestId = null;
      })
      .addCase(loginUser.rejected, (state, action) => {
        if (action.meta.requestId !== state.currentRequestId) return;
        state.status = 'failed';
        state.error = action.payload || 'Login failed. Please try again.';
        state.isAuthenticated = false;
        state.currentRequestId = null;
      });

    // ── signupUser ──
    builder
      .addCase(signupUser.pending, (state, action) => {
        state.status = 'loading';
        state.error = null;
        state.currentRequestId = action.meta.requestId;
      })
      .addCase(signupUser.fulfilled, (state, action) => {
        if (action.meta.requestId !== state.currentRequestId) return;
        state.isInitialized = true;
        state.status = 'succeeded';
        state.user = action.payload;
        state.isAuthenticated = true;
        state.error = null;
        state.currentRequestId = null;
      })
      .addCase(signupUser.rejected, (state, action) => {
        if (action.meta.requestId !== state.currentRequestId) return;
        state.status = 'failed';
        state.error = action.payload || 'Registration failed. Please try again.';
        state.isAuthenticated = false;
        state.currentRequestId = null;
      });

    // ── logoutUser ──
    builder
      .addCase(logoutUser.pending, (state, action) => {
        state.status = 'loading';
        state.currentRequestId = action.meta.requestId;
      })
      .addCase(logoutUser.fulfilled, (state) => {
        state.user = null;
        state.isAuthenticated = false;
        state.status = 'succeeded';
        state.error = null;
        state.currentRequestId = null;
      })
      .addCase(logoutUser.rejected, (state, action) => {
        state.user = null;
        state.isAuthenticated = false;
        state.status = 'failed';
        state.error = action.payload || 'Logout failed on server';
        state.currentRequestId = null;
      });
  },
});

// ─── Selectors ────────────────────────────────────────────────

export const selectUser = (state) => state.auth.user;
export const selectIsAuthenticated = (state) => state.auth.isAuthenticated;
export const selectAuthStatus = (state) => state.auth.status;
export const selectAuthError = (state) => state.auth.error;
export const selectIsAuthInitialized = (state) => state.auth.isInitialized;
export const selectIsAuthLoading = (state) =>
  state.auth.status === 'loading' || (!state.auth.isInitialized && state.auth.status === 'idle');

export const { clearError } = authSlice.actions;
export default authSlice.reducer;
