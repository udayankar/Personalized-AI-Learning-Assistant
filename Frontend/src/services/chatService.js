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
 *     answer_mode: 'DOCUMENT_SUPPORTED'|'INSUFFICIENT_CONFIDENCE',
 *     message: string|null,
 *     reliability: 'HIGH'|'MODERATE'|'LOW', conflict_status: string,
 *     claims: Array<{ text: string, classification: string, sources: Array }>,
 *     sources: Array<{ reference: string, source: string, page: number|null, text: string }>
 *   }
 *
 * The backend requires cookie authentication; the frontend also routes chat
 * within the authenticated application layout. Chat history is session-only in Redux.
 */

import apiClient from './apiClient';

/**
 * Submit a learning question to the RAG pipeline.
 * @param {string} query - The user's question
 * @returns {Promise<{ answer: string, answer_mode: string, message: string|null, reliability: string, claims: Array, sources: Array }>}
 */
export async function sendQuery(query) {
  // Retrieval and multiple Gemini operations may take several minutes.
  const response = await apiClient.post('/chat/query', { query }, { timeout: 900000 });
  return response.data;
}
