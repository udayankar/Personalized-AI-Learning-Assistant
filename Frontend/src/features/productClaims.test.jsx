import React from 'react';
import { configureStore } from '@reduxjs/toolkit';
import { Provider } from 'react-redux';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import authReducer from '../store/slices/authSlice';
import documentReducer from '../store/slices/documentSlice';
import uiReducer from '../store/slices/uiSlice';
import LandingPage from './landing/LandingPage';
import DashboardPage from './dashboard/DashboardPage';
import DocumentLibraryPage from './documents/DocumentLibraryPage';
import SettingsPage from './settings/SettingsPage';

function renderWithAppState(component) {
  const store = configureStore({
    reducer: {
      auth: authReducer,
      documents: documentReducer,
      ui: uiReducer,
    },
  });

  return render(
    <Provider store={store}>
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        {component}
      </MemoryRouter>
    </Provider>
  );
}

describe('accurate product claims', () => {
  test('landing page explains supported PDFs and answer sources without guarantees', () => {
    render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <LandingPage />
      </MemoryRouter>
    );

    expect(screen.getAllByText(/text-based/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/scanned PDFs are not (currently )?OCR-processed/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/general AI knowledge/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/HttpOnly JWT cookie and CSRF checks/i)).toBeInTheDocument();
    expect(screen.getByText(/persistence across deployments depends on host storage/i)).toBeInTheDocument();
    expect(screen.getByText(/Local FAISS vector search index for each account/i)).toBeInTheDocument();
    expect(screen.getByText(/Tools to browse, delete, and reprocess uploaded documents/i)).toBeInTheDocument();
    expect(screen.queryByText(/Free and open-source/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Every answer cited with document name and exact page numbers/i)).not.toBeInTheDocument();
  });

  test('dashboard distinguishes document evidence from general AI knowledge and describes local storage', () => {
    renderWithAppState(<DashboardPage />);

    expect(screen.getAllByText(/searches your documents first/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/general AI knowledge/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/server's local filesystem/i)).toBeInTheDocument();
    expect(screen.getByText(/persistence across deployments depends on the host/i)).toBeInTheDocument();
    expect(screen.queryByText(/answers come from your documents, not generic knowledge/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/rebuilt automatically/i)).not.toBeInTheDocument();
  });

  test('document upload explains text extraction limits and local search indexing', () => {
    renderWithAppState(<DocumentLibraryPage />);

    expect(screen.getByText(/Scanned PDFs are not currently processed with OCR/i)).toBeInTheDocument();
    expect(screen.getByText(/local search index/i)).toBeInTheDocument();
    expect(screen.queryByText(/vector database/i)).not.toBeInTheDocument();
  });

  test('settings does not imply unavailable profile features are in active development', () => {
    renderWithAppState(<SettingsPage />);

    expect(screen.getByText(/Profile editing and password changes are not available yet/i)).toBeInTheDocument();
    expect(screen.getByText(/Local Vector Search Index/i)).toBeInTheDocument();
    expect(screen.queryByText(/in active development/i)).not.toBeInTheDocument();
  });
});
