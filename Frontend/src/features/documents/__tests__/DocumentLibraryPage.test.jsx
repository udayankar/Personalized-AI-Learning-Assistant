import React from 'react';
import { Provider } from 'react-redux';
import { configureStore } from '@reduxjs/toolkit';
import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import documentReducer from '../../../store/slices/documentSlice';
import authReducer from '../../../store/slices/authSlice';
import uiReducer from '../../../store/slices/uiSlice';
import { logoutUser, loginUser } from '../../../store/slices/authSlice';
import DocumentLibraryPage from '../DocumentLibraryPage';
import * as documentService from '../../../services/documentService';

jest.mock('../../../services/documentService', () => ({
  getDocuments: jest.fn(),
  getDocument: jest.fn(),
  deleteDocument: jest.fn(),
  uploadDocument: jest.fn(),
}));

const user = { ID: 7, Name: 'Student', Email: 'student@example.test' };
const doc = {
  id: 'doc-1',
  filename: 'notes.pdf',
  uploaded_at: '2026-11-16T10:00:00Z',
  updated_at: '2026-11-16T10:00:00Z',
  file_size_bytes: 2048,
  page_count: 5,
  status: 'READY',
  available: true,
};

function renderPage(initialDocuments = []) {
  const initialAuth = authReducer(undefined, { type: 'test/init' });
  const store = configureStore({
    reducer: { documents: documentReducer, auth: authReducer, ui: uiReducer },
    preloadedState: {
      auth: {
        ...initialAuth,
        user,
        isAuthenticated: true,
        isInitialized: true,
        status: 'succeeded',
      },
    },
  });
  if (initialDocuments !== null) documentService.getDocuments.mockResolvedValue(initialDocuments);
  const view = render(
    <Provider store={store}>
      <DocumentLibraryPage />
    </Provider>
  );
  return { ...view, store };
}

describe('DocumentLibraryPage', () => {
  beforeEach(() => jest.clearAllMocks());

  test('shows a loading state while the server catalog is loading', async () => {
    documentService.getDocuments.mockReturnValue(new Promise(() => {}));
    renderPage(null);
    expect(screen.getByRole('status')).toHaveTextContent('Loading your documents');
  });

  test('shows an empty state when the server returns no documents', async () => {
    renderPage([]);
    expect(await screen.findByText('No documents uploaded yet')).toBeInTheDocument();
  });

  test('shows server metadata and loads details for an owned document', async () => {
    documentService.getDocument.mockResolvedValue(doc);
    renderPage([doc]);

    expect(await screen.findByText('notes.pdf')).toBeInTheDocument();
    expect(screen.getByText(/2\.0 KB · 5 pages/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Details for notes.pdf' }));
    expect(await screen.findByText('Document details')).toBeInTheDocument();
    expect(screen.getByText('READY')).toBeInTheDocument();
    expect(documentService.getDocument).toHaveBeenCalledWith('doc-1');
  });

  test('shows list errors and can retry', async () => {
    documentService.getDocuments
      .mockRejectedValueOnce(new Error('Documents unavailable'))
      .mockResolvedValueOnce([doc]);
    renderPage(null);

    expect(await screen.findByRole('alert')).toHaveTextContent('Documents unavailable');
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(await screen.findByText('notes.pdf')).toBeInTheDocument();
  });

  test('canceling deletion makes no request and confirming removes only on success', async () => {
    const userActions = userEvent.setup();
    documentService.deleteDocument.mockResolvedValue(undefined);
    renderPage([doc]);

    await screen.findByText('notes.pdf');
    await userActions.click(screen.getByRole('button', { name: 'Delete notes.pdf' }));
    expect(screen.getByRole('alertdialog')).toBeInTheDocument();
    await userActions.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(documentService.deleteDocument).not.toHaveBeenCalled();

    await userActions.click(screen.getByRole('button', { name: 'Delete notes.pdf' }));
    await userActions.click(screen.getByRole('button', { name: 'Delete document' }));
    await waitFor(() => expect(documentService.deleteDocument).toHaveBeenCalledWith('doc-1'));
    await waitFor(() => expect(screen.queryByText('notes.pdf')).not.toBeInTheDocument());
  });

  test('failed deletion keeps the document visible and reports the error', async () => {
    documentService.deleteDocument.mockRejectedValue(new Error('Deletion is incomplete and can be retried'));
    renderPage([doc]);
    await screen.findByText('notes.pdf');
    await userEvent.click(screen.getByRole('button', { name: 'Delete notes.pdf' }));
    await userEvent.click(screen.getByRole('button', { name: 'Delete document' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('Deletion is incomplete');
    expect(screen.getByText('notes.pdf')).toBeInTheDocument();
  });

  test('upload success refreshes from server metadata and auth changes clear another user catalog', async () => {
    const uploaded = { ...doc, filename: 'new-notes.pdf', file_size_bytes: 9999 };
    documentService.uploadDocument.mockResolvedValue({ filename: uploaded.filename, message: 'ok' });
    documentService.getDocuments.mockResolvedValue([]);
    documentService.getDocuments
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([uploaded])
      .mockResolvedValueOnce([]);
    const { store } = renderPage(null);
    await screen.findByText('No documents uploaded yet');

    const file = new File(['pdf'], 'new-notes.pdf', { type: 'application/pdf' });
    await userEvent.upload(screen.getByLabelText('Upload PDF study material dropzone').querySelector('input'), file);
    expect(await screen.findByText('new-notes.pdf')).toBeInTheDocument();
    expect(screen.getByText(/9\.8 KB/)).toBeInTheDocument();

    act(() => store.dispatch(loginUser.fulfilled({ ...user, ID: 8 }, 'login-2')));
    await waitFor(() => expect(screen.queryByText('new-notes.pdf')).not.toBeInTheDocument());
    act(() => store.dispatch(logoutUser.fulfilled({ message: 'logged out' }, 'logout-1')));
    expect(store.getState().documents.uploadedFiles).toEqual([]);
  });
});
