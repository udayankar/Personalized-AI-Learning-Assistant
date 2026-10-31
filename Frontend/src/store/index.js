/**
 * Redux Store Configuration
 *
 * Combines all feature slices into a single store.
 * Logout action from authSlice clears chat and document state
 * via the reset middleware pattern.
 */

import { configureStore } from '@reduxjs/toolkit';
import authReducer from './slices/authSlice';
import chatReducer, { clearChat } from './slices/chatSlice';
import documentReducer, { resetUploadState } from './slices/documentSlice';
import uiReducer, { clearAllToasts } from './slices/uiSlice';
import { logoutUser } from './slices/authSlice';

const store = configureStore({
  reducer: {
    auth: authReducer,
    chat: chatReducer,
    documents: documentReducer,
    ui: uiReducer,
  },
  middleware: (getDefaultMiddleware) => {
    return getDefaultMiddleware({
      // Serialize dates in Redux state is fine for our use case
      serializableCheck: {
        ignoredActions: ['chat/sendMessage/pending'],
      },
    }).concat(logoutCleanupMiddleware);
  },
});

/**
 * Middleware that clears in-memory session data on logout.
 * Chat history and upload records are session-only data.
 */
function logoutCleanupMiddleware(storeAPI) {
  return (next) => (action) => {
    const result = next(action);
    if (
      action.type === logoutUser.fulfilled.type ||
      action.type === logoutUser.rejected.type
    ) {
      storeAPI.dispatch(clearChat());
      storeAPI.dispatch(resetUploadState());
      storeAPI.dispatch(clearAllToasts());
    }
    return result;
  };
}

export default store;
