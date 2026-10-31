/**
 * Authentication Service
 *
 * Wraps all /users/* API endpoints.
 * Authentication uses HttpOnly cookies — never stored in JavaScript.
 *
 * Backend contracts (verified against Backend/App/Routers/auth.py and signup.py):
 *   POST /users/signup  → { Name, Email, Password } → 201 { ID, Name, Email, Created_at }
 *   POST /users/login   → { Email, Password }       → 200 { message } + sets cookie
 *   GET  /users/me      → 200 { ID, Name, Email, Created_at } | 401
 *   POST /users/logout  → 200 { message } + clears cookie
 *
 * Note: Signup does NOT automatically log in the user.
 *       The frontend handles post-signup login explicitly.
 */

import apiClient from './apiClient';

/**
 * Register a new user account.
 * @param {{ Name: string, Email: string, Password: string }} credentials
 * @returns {Promise<{ ID: number, Name: string, Email: string, Created_at: string }>}
 */
export async function signup({ Name, Email, Password }) {
  const response = await apiClient.post('/users/signup', { Name, Email, Password });
  return response.data;
}

/**
 * Log in with email and password.
 * On success, the server sets an HttpOnly 'access_token' cookie.
 * @param {{ Email: string, Password: string }} credentials
 * @returns {Promise<{ message: string }>}
 */
export async function login({ Email, Password }) {
  const response = await apiClient.post('/users/login', { Email, Password });
  return response.data;
}

/**
 * Retrieve the current authenticated user from their session cookie.
 * Used at application startup to restore session state.
 * Returns null if not authenticated (401) rather than throwing.
 * @returns {Promise<{ ID: number, Name: string, Email: string, Created_at: string } | null>}
 */
export async function getMe() {
  try {
    const response = await apiClient.get('/users/me');
    return response.data;
  } catch (error) {
    // 401 means no valid session — not an error from the frontend perspective
    return null;
  }
}

/**
 * Log out the current user.
 * The server clears the HttpOnly 'access_token' cookie.
 * @returns {Promise<{ message: string }>}
 */
export async function logout() {
  const response = await apiClient.post('/users/logout');
  return response.data;
}
