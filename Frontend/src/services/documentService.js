/**
 * Document Service
 *
 * Wraps the authenticated document catalog and upload endpoints.
 *
 * Backend contract (verified against Backend/App/Routers/documents.py):
 *   GET    /documents
 *   GET    /documents/{id}
 *   DELETE /documents/{id}
 *   POST   /documents/upload
 *
 * Note:
 * - The backend performs synchronous FAISS re-indexing before returning 201.
 *   This can take several seconds for large PDFs.
 */

import apiClient from './apiClient';

export async function getDocuments() {
  const response = await apiClient.get('/documents');
  return response.data.documents;
}

export async function getDocument(documentId) {
  const response = await apiClient.get(`/documents/${encodeURIComponent(documentId)}`);
  return response.data;
}

export async function deleteDocument(documentId) {
  await apiClient.delete(`/documents/${encodeURIComponent(documentId)}`, { timeout: 120000 });
}

/**
 * Upload a PDF document to the knowledge base.
 * @param {File} file - The PDF file to upload
 * @param {function(number): void} [onUploadProgress] - Upload progress callback (0-100)
 * @returns {Promise<{ message: string, filename: string }>}
 */
export async function uploadDocument(file, onUploadProgress) {
  const formData = new FormData();
  formData.append('file', file); // Field name 'file' is required by the backend

  const response = await apiClient.post('/documents/upload', formData, {
    headers: {
      // Let Axios set Content-Type with multipart boundary automatically
      'Content-Type': 'multipart/form-data',
    },
    onUploadProgress: (progressEvent) => {
      if (onUploadProgress && progressEvent.total) {
        const percent = Math.round((progressEvent.loaded * 100) / progressEvent.total);
        onUploadProgress(percent);
      }
    },
    // Override default timeout for large PDFs + RAG indexing time
    timeout: 120000, // 2 minutes
  });

  return response.data;
}
