/**
 * Document Redux Slice
 *
 * Manages PDF upload state and the list of documents
 * indexed in the current session.
 *
 * IMPORTANT LIMITATION:
 * The backend has no document listing or deletion endpoint.
 * uploadedFiles tracks only documents uploaded in THIS session.
 * On page reload, this list is lost (it lives only in Redux memory).
 * The actual knowledge base on the backend persists across restarts.
 */

import { createSlice, createAsyncThunk } from '@reduxjs/toolkit';
import { uploadDocument as uploadDocumentAPI } from '../../services/documentService';
import { logoutUser } from './authSlice';

// ─── Async Thunks ─────────────────────────────────────────────

/**
 * Upload a PDF document and wait for backend indexing.
 * Two phases:
 *   1. "uploading" — file bytes being transmitted (0→100%)
 *   2. "indexing"  — backend processing FAISS embeddings (indeterminate)
 */
export const uploadDocument = createAsyncThunk(
  'documents/uploadDocument',
  async ({ file, onProgress }, { dispatch, rejectWithValue }) => {
    try {
      const data = await uploadDocumentAPI(file, (percent) => {
        dispatch(setUploadProgress(percent));
        if (percent === 100) {
          // Transfer complete — now backend is indexing
          dispatch(setUploadPhase('indexing'));
        }
      });
      return {
        filename: data.filename,
        message: data.message,
        uploadedAt: new Date().toISOString(),
        size: file.size,
      };
    } catch (error) {
      return rejectWithValue(error.message);
    }
  }
);

// ─── Slice ────────────────────────────────────────────────────

const documentSlice = createSlice({
  name: 'documents',
  initialState: {
    uploadedFiles: [], // [{ filename, uploadedAt, size }]
    uploadPhase: 'idle',    // 'idle' | 'uploading' | 'indexing' | 'succeeded' | 'failed'
    uploadProgress: 0,      // 0–100 during 'uploading' phase
    error: null,
    lastUploadedFilename: null,
  },
  reducers: {
    setUploadProgress(state, action) {
      state.uploadProgress = action.payload;
    },
    setUploadPhase(state, action) {
      state.uploadPhase = action.payload;
    },
    clearUploadError(state) {
      state.error = null;
      state.uploadPhase = 'idle';
      state.uploadProgress = 0;
    },
    clearDocuments(state) {
      state.uploadedFiles = [];
      state.uploadPhase = 'idle';
      state.uploadProgress = 0;
      state.error = null;
      state.lastUploadedFilename = null;
    },
    resetUploadState(state) {
      state.uploadedFiles = [];
      state.uploadPhase = 'idle';
      state.uploadProgress = 0;
      state.error = null;
      state.lastUploadedFilename = null;
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(uploadDocument.pending, (state) => {
        state.uploadPhase = 'uploading';
        state.uploadProgress = 0;
        state.error = null;
        state.lastUploadedFilename = null;
      })
      .addCase(uploadDocument.fulfilled, (state, action) => {
        state.uploadPhase = 'succeeded';
        state.uploadProgress = 100;
        state.lastUploadedFilename = action.payload.filename;
        state.uploadedFiles.push({
          filename: action.payload.filename,
          uploadedAt: action.payload.uploadedAt,
          size: action.payload.size,
        });
      })
      .addCase(uploadDocument.rejected, (state, action) => {
        state.uploadPhase = 'failed';
        state.error = action.payload || 'Upload failed. Please try again.';
        state.uploadProgress = 0;
      })
      .addCase(logoutUser.fulfilled, (state) => {
        state.uploadedFiles = [];
        state.uploadPhase = 'idle';
        state.uploadProgress = 0;
        state.error = null;
        state.lastUploadedFilename = null;
      })
      .addCase(logoutUser.rejected, (state) => {
        state.uploadedFiles = [];
        state.uploadPhase = 'idle';
        state.uploadProgress = 0;
        state.error = null;
        state.lastUploadedFilename = null;
      });
  },
});

// ─── Selectors ────────────────────────────────────────────────

export const selectUploadedFiles = (state) => state.documents.uploadedFiles;
export const selectUploadPhase = (state) => state.documents.uploadPhase;
export const selectUploadProgress = (state) => state.documents.uploadProgress;
export const selectDocumentError = (state) => state.documents.error;
export const selectLastUploadedFilename = (state) => state.documents.lastUploadedFilename;

export const { setUploadProgress, setUploadPhase, clearUploadError, clearDocuments, resetUploadState } =
  documentSlice.actions;
export default documentSlice.reducer;
