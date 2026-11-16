/**
 * Document Redux Slice
 *
 * Manages upload progress and the authenticated user's server-backed catalog.
 */

import { createSlice, createAsyncThunk } from '@reduxjs/toolkit';
import {
  deleteDocument as deleteDocumentAPI,
  getDocument,
  getDocuments,
  uploadDocument as uploadDocumentAPI,
} from '../../services/documentService';
import { checkAuth, loginUser, logoutUser, signupUser } from './authSlice';

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
      return { filename: data.filename, message: data.message };
    } catch (error) {
      return rejectWithValue(error.message);
    }
  }
);

export const fetchDocuments = createAsyncThunk(
  'documents/fetchDocuments',
  async (userId, { rejectWithValue }) => {
    try {
      return { userId, documents: await getDocuments() };
    } catch (error) {
      return rejectWithValue({ userId, message: error.message });
    }
  }
);

export const fetchDocumentDetails = createAsyncThunk(
  'documents/fetchDocumentDetails',
  async ({ documentId, userId }, { rejectWithValue }) => {
    try {
      return { userId, document: await getDocument(documentId) };
    } catch (error) {
      return rejectWithValue({ userId, documentId, message: error.message });
    }
  }
);

export const deleteDocument = createAsyncThunk(
  'documents/deleteDocument',
  async ({ documentId, userId }, { rejectWithValue }) => {
    try {
      await deleteDocumentAPI(documentId);
      return { userId, documentId };
    } catch (error) {
      return rejectWithValue({ userId, documentId, message: error.message });
    }
  }
);

// ─── Slice ────────────────────────────────────────────────────

const documentSlice = createSlice({
  name: 'documents',
  initialState: {
    uploadedFiles: [], // Authenticated user's server-backed document records
    uploadPhase: 'idle',    // 'idle' | 'uploading' | 'indexing' | 'succeeded' | 'failed'
    uploadProgress: 0,      // 0–100 during 'uploading' phase
    error: null,
    lastUploadedFilename: null,
    catalogStatus: 'idle',
    catalogError: null,
    catalogUserId: null,
    selectedDocument: null,
    detailsStatus: 'idle',
    detailsError: null,
    detailsUserId: null,
    deletingDocumentIds: [],
    deleteErrors: {},
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
    clearCatalogState(state) {
      state.uploadedFiles = [];
      state.catalogStatus = 'idle';
      state.catalogError = null;
      state.catalogUserId = null;
      state.selectedDocument = null;
      state.detailsStatus = 'idle';
      state.detailsError = null;
      state.detailsUserId = null;
      state.deletingDocumentIds = [];
      state.deleteErrors = {};
    },
    clearDocumentDetails(state) {
      state.selectedDocument = null;
      state.detailsStatus = 'idle';
      state.detailsError = null;
      state.detailsUserId = null;
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
      })
      .addCase(uploadDocument.rejected, (state, action) => {
        state.uploadPhase = 'failed';
        state.error = action.payload || 'Upload failed. Please try again.';
        state.uploadProgress = 0;
      })
      .addCase(fetchDocuments.pending, (state, action) => {
        const userId = action.meta.arg;
        if (state.catalogUserId !== userId) resetCatalog(state);
        state.catalogUserId = userId;
        state.catalogStatus = 'loading';
        state.catalogError = null;
      })
      .addCase(fetchDocuments.fulfilled, (state, action) => {
        if (state.catalogUserId !== action.payload.userId) return;
        state.uploadedFiles = action.payload.documents;
        state.catalogStatus = 'succeeded';
        state.catalogError = null;
      })
      .addCase(fetchDocuments.rejected, (state, action) => {
        const userId = action.payload?.userId ?? action.meta.arg;
        if (state.catalogUserId !== userId) return;
        state.catalogStatus = 'failed';
        state.catalogError = action.payload?.message || 'Could not load your documents.';
      })
      .addCase(fetchDocumentDetails.pending, (state, action) => {
        state.selectedDocument = null;
        state.detailsUserId = action.meta.arg.userId;
        state.detailsStatus = 'loading';
        state.detailsError = null;
      })
      .addCase(fetchDocumentDetails.fulfilled, (state, action) => {
        if (state.detailsUserId !== action.payload.userId) return;
        state.selectedDocument = action.payload.document;
        state.detailsStatus = 'succeeded';
      })
      .addCase(fetchDocumentDetails.rejected, (state, action) => {
        const userId = action.payload?.userId ?? action.meta.arg.userId;
        if (state.detailsUserId !== userId) return;
        state.detailsStatus = 'failed';
        state.detailsError = action.payload?.message || 'Could not load document details.';
      })
      .addCase(deleteDocument.pending, (state, action) => {
        const { documentId } = action.meta.arg;
        state.deletingDocumentIds.push(documentId);
        delete state.deleteErrors[documentId];
      })
      .addCase(deleteDocument.fulfilled, (state, action) => {
        const { documentId, userId } = action.payload;
        state.deletingDocumentIds = state.deletingDocumentIds.filter((id) => id !== documentId);
        if (state.catalogUserId !== userId) return;
        state.uploadedFiles = state.uploadedFiles.filter((document) => document.id !== documentId);
        if (state.selectedDocument?.id === documentId) {
          state.selectedDocument = null;
          state.detailsStatus = 'idle';
        }
      })
      .addCase(deleteDocument.rejected, (state, action) => {
        const { documentId, userId, message } = action.payload || {};
        const id = documentId ?? action.meta.arg.documentId;
        state.deletingDocumentIds = state.deletingDocumentIds.filter((item) => item !== id);
        if (state.catalogUserId === (userId ?? action.meta.arg.userId)) {
          state.deleteErrors[id] = message || 'Could not delete this document.';
        }
      })
      .addCase(checkAuth.fulfilled, (state, action) => {
        if (!action.payload || state.catalogUserId !== action.payload.ID) {
          resetCatalog(state);
        }
      })
      .addCase(loginUser.fulfilled, (state, action) => {
        if (state.catalogUserId !== action.payload.ID) resetCatalog(state);
      })
      .addCase(signupUser.fulfilled, (state, action) => {
        if (state.catalogUserId !== action.payload.ID) resetCatalog(state);
      })
      .addCase(logoutUser.fulfilled, (state) => {
        resetCatalog(state);
        resetUpload(state);
      })
      .addCase(logoutUser.rejected, (state) => {
        resetCatalog(state);
        resetUpload(state);
      });
  },
});

function resetUpload(state) {
  state.uploadPhase = 'idle';
  state.uploadProgress = 0;
  state.error = null;
  state.lastUploadedFilename = null;
}

function resetCatalog(state) {
  state.uploadedFiles = [];
  state.catalogStatus = 'idle';
  state.catalogError = null;
  state.catalogUserId = null;
  state.selectedDocument = null;
  state.detailsStatus = 'idle';
  state.detailsError = null;
  state.detailsUserId = null;
  state.deletingDocumentIds = [];
  state.deleteErrors = {};
}

// ─── Selectors ────────────────────────────────────────────────

export const selectUploadedFiles = (state) => state.documents.uploadedFiles;
export const selectUploadPhase = (state) => state.documents.uploadPhase;
export const selectUploadProgress = (state) => state.documents.uploadProgress;
export const selectDocumentError = (state) => state.documents.error;
export const selectLastUploadedFilename = (state) => state.documents.lastUploadedFilename;
export const selectCatalogStatus = (state) => state.documents.catalogStatus;
export const selectCatalogError = (state) => state.documents.catalogError;
export const selectSelectedDocument = (state) => state.documents.selectedDocument;
export const selectDetailsStatus = (state) => state.documents.detailsStatus;
export const selectDetailsError = (state) => state.documents.detailsError;
export const selectDeletingDocumentIds = (state) => state.documents.deletingDocumentIds;
export const selectDeleteErrors = (state) => state.documents.deleteErrors;

export const {
  setUploadProgress, setUploadPhase, clearUploadError, clearDocuments, resetUploadState,
  clearCatalogState, clearDocumentDetails,
} =
  documentSlice.actions;
export default documentSlice.reducer;
