/**
 * UI Redux Slice
 *
 * Manages shared UI state:
 * - Toast notifications (global alerts)
 * - Sidebar collapsed state (mobile/desktop)
 */

import { createSlice } from '@reduxjs/toolkit';
import { nanoid } from '@reduxjs/toolkit';

const uiSlice = createSlice({
  name: 'ui',
  initialState: {
    toasts: [],          // [{ id, type, message, duration }]
    sidebarCollapsed: false,
  },
  reducers: {
    addToast(state, action) {
      const { type = 'info', message, duration = 4000 } = action.payload;
      state.toasts.push({
        id: nanoid(),
        type, // 'info' | 'success' | 'error' | 'warning'
        message,
        duration,
      });
    },
    removeToast(state, action) {
      state.toasts = state.toasts.filter((t) => t.id !== action.payload);
    },
    clearAllToasts(state) {
      state.toasts = [];
    },
    setSidebarCollapsed(state, action) {
      state.sidebarCollapsed = action.payload;
    },
    toggleSidebar(state) {
      state.sidebarCollapsed = !state.sidebarCollapsed;
    },
  },
});

// ─── Selectors ────────────────────────────────────────────────

export const selectToasts = (state) => state.ui.toasts;
export const selectSidebarCollapsed = (state) => state.ui.sidebarCollapsed;

export const { addToast, removeToast, clearAllToasts, setSidebarCollapsed, toggleSidebar } =
  uiSlice.actions;
export default uiSlice.reducer;
