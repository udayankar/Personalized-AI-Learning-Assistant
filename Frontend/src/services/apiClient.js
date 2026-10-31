/**
 * Centralized Axios API Client
 *
 * Configuration:
 * - withCredentials: true  — required for HttpOnly cookie transmission
 * - baseURL from environment variable (falls back to localhost:8000)
 * - 60s timeout to accommodate RAG document indexing
 * - Response interceptor normalizes FastAPI error formats
 */

import axios from 'axios';

const API_BASE_URL = process.env.API_BASE_URL || 'http://localhost:8000';

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  withCredentials: true, // REQUIRED — sends/receives HttpOnly 'access_token' cookie
  headers: {
    'Content-Type': 'application/json',
    Accept: 'application/json',
  },
  timeout: 60000, // 60s — document indexing can take several seconds
});

/**
 * Normalizes FastAPI error responses into readable strings.
 *
 * FastAPI returns errors in two formats:
 *   1. String detail:  { "detail": "Wrong info" }
 *   2. Array detail (Pydantic validation):
 *      { "detail": [{ "loc": ["body", "Password"], "msg": "..." }] }
 */
function normalizeError(error) {
  if (!error.response) {
    // Network failure — backend unreachable
    return new Error(
      'Unable to connect to the server. Please ensure the backend is running.'
    );
  }

  const { data, status } = error.response;

  if (data && typeof data.detail === 'string') {
    return new Error(data.detail);
  }

  if (data && Array.isArray(data.detail)) {
    // Pydantic validation errors — format each field error
    const messages = data.detail.map((err) => {
      const field = err.loc && err.loc.length > 1 ? err.loc.slice(1).join('.') : 'Field';
      return `${field}: ${err.msg}`;
    });
    return new Error(messages.join(' · '));
  }

  // Fallback for specific HTTP status codes
  const statusMessages = {
    400: 'Invalid request. Please check your input.',
    401: 'Your session has expired. Please log in again.',
    403: 'You do not have permission to perform this action.',
    404: 'The requested resource was not found.',
    409: 'A conflict occurred. This item may already exist.',
    422: 'The provided data is invalid. Please check your input.',
    500: 'An internal server error occurred. Please try again later.',
    503: 'The AI service is temporarily unavailable. Please try again in a moment.',
  };

  return new Error(
    statusMessages[status] || `Server returned an error (${status}). Please try again.`
  );
}

apiClient.interceptors.response.use(
  (response) => response,
  (error) => Promise.reject(normalizeError(error))
);

export default apiClient;
