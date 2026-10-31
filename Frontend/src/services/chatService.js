/**
 * Chat Service
 *
 * Wraps the RAG chat query endpoint.
 *
 * Backend contract (verified against Backend/App/Routers/chat.py):
 *   POST /chat/query
 *   Request:  { query: string }
 *   Response: {
 *     answer: string,
 *     sources: Array<{ source: string, page: number, text: string }>
 *   }
 *
 * Note: The endpoint is currently not authentication-gated on the backend.
 *       The frontend routes it within the authenticated application layout.
 *       Chat history is not persisted by the backend — session-only in Redux.
 */

import apiClient from './apiClient';

/**
 * Submit a learning question to the RAG pipeline.
 * @param {string} query - The user's question
 * @returns {Promise<{ answer: string, sources: Array<{ source: string, page: number, text: string }> }>}
 */
export async function sendQuery(query) {
  const response = await apiClient.post('/chat/query', { query });
  return response.data;
}
