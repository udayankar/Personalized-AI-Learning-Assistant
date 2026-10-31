/**
 * Document Service
 *
 * Wraps the PDF document upload endpoint.
 *
 * Backend contract (verified against Backend/App/Routers/documents.py):
 *   POST /documents/upload
 *   Request:  multipart/form-data — field name: "file"
 *   Response: 201 { message: string, filename: string }
 *   Errors:
 *     400 - No file / not PDF / invalid content type
 *     409 - Filename already exists in the backend documents directory
 *     500 - Failed to upload and process (FAISS indexing error)
 *
 * Note:
 * - The backend performs synchronous FAISS re-indexing before returning 201.
 *   This can take several seconds for large PDFs.
 * - There is NO document listing or deletion endpoint in the current backend.
 */

import apiClient from './apiClient';

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
