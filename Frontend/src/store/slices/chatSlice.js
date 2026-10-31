/**
 * Chat Redux Slice
 *
 * Manages the active study session conversation.
 *
 * Note: The backend does not persist chat history.
 * Messages exist only for the current browser session.
 * Clearing Redux state (logout, page reload) clears the conversation.
 *
 * Backend response shape (verified against Backend/App/schemas.py):
 *   { answer: string, sources: [{ source: string, page: number, text: string }] }
 */

import { createSlice, createAsyncThunk } from '@reduxjs/toolkit';
import { sendQuery as sendQueryAPI } from '../../services/chatService';
import { nanoid } from '@reduxjs/toolkit';
import { logoutUser } from './authSlice';

// ─── Async Thunks ─────────────────────────────────────────────

/**
 * Send a question to the RAG pipeline.
 * Optimistically adds user message immediately.
 * Updates with AI response on completion.
 */
export const sendMessage = createAsyncThunk(
  'chat/sendMessage',
  async (query, { rejectWithValue }) => {
    try {
      const data = await sendQueryAPI(query);
      return data; // { answer, sources }
    } catch (error) {
      return rejectWithValue(error.message);
    }
  }
);

// ─── Slice ────────────────────────────────────────────────────

const chatSlice = createSlice({
  name: 'chat',
  initialState: {
    messages: [],
    // [{ id, role: 'user'|'assistant', content, sources, timestamp, status }]
    isGenerating: false,
    selectedCitation: null, // { source, page, text } — drives the citation drawer
    error: null,
    pendingMessageId: null, // ID of the assistant placeholder being generated
  },
  reducers: {
    setSelectedCitation(state, action) {
      state.selectedCitation = action.payload; // null to close drawer
    },
    clearChat(state) {
      state.messages = [];
      state.error = null;
      state.isGenerating = false;
      state.selectedCitation = null;
      state.pendingMessageId = null;
    },
    clearChatError(state) {
      state.error = null;
      // Remove failed assistant messages
      state.messages = state.messages.filter((m) => m.status !== 'error');
    },
    retryLastMessage(state) {
      // Remove the last failed assistant message so the user can retry
      const lastFailed = [...state.messages].reverse().find(
        (m) => m.role === 'assistant' && m.status === 'error'
      );
      if (lastFailed) {
        state.messages = state.messages.filter((m) => m.id !== lastFailed.id);
      }
      state.error = null;
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(sendMessage.pending, (state, action) => {
        const userQuery = action.meta.arg;
        const userMessageId = nanoid();
        const assistantPlaceholderId = nanoid();

        // Add user message immediately
        state.messages.push({
          id: userMessageId,
          role: 'user',
          content: userQuery,
          sources: [],
          timestamp: new Date().toISOString(),
          status: 'complete',
        });

        // Add assistant placeholder
        state.messages.push({
          id: assistantPlaceholderId,
          role: 'assistant',
          content: '',
          sources: [],
          timestamp: new Date().toISOString(),
          status: 'loading',
        });

        state.isGenerating = true;
        state.error = null;
        state.pendingMessageId = assistantPlaceholderId;
      })
      .addCase(sendMessage.fulfilled, (state, action) => {
        const { answer, sources } = action.payload;
        const pendingMsg = state.messages.find((m) => m.id === state.pendingMessageId);

        if (pendingMsg) {
          pendingMsg.content = answer;
          pendingMsg.sources = sources || [];
          pendingMsg.status = 'complete';
        }

        state.isGenerating = false;
        state.pendingMessageId = null;
        state.error = null;
      })
      .addCase(sendMessage.rejected, (state, action) => {
        const pendingMsg = state.messages.find((m) => m.id === state.pendingMessageId);

        if (pendingMsg) {
          pendingMsg.status = 'error';
          pendingMsg.content = action.payload || 'Failed to get a response. Please try again.';
        }

        state.isGenerating = false;
        state.error = action.payload || 'Failed to get a response. Please try again.';
        state.pendingMessageId = null;
      })
      .addCase(logoutUser.fulfilled, (state) => {
        state.messages = [];
        state.error = null;
        state.isGenerating = false;
        state.selectedCitation = null;
        state.pendingMessageId = null;
      })
      .addCase(logoutUser.rejected, (state) => {
        state.messages = [];
        state.error = null;
        state.isGenerating = false;
        state.selectedCitation = null;
        state.pendingMessageId = null;
      });
  },
});

// ─── Selectors ────────────────────────────────────────────────

export const selectMessages = (state) => state.chat.messages;
export const selectIsGenerating = (state) => state.chat.isGenerating;
export const selectSelectedCitation = (state) => state.chat.selectedCitation;
export const selectChatError = (state) => state.chat.error;

export const { setSelectedCitation, clearChat, clearChatError, retryLastMessage } = chatSlice.actions;
export default chatSlice.reducer;
