import React from 'react';
import { Provider } from 'react-redux';
import { configureStore } from '@reduxjs/toolkit';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import chatReducer, { sendMessage } from '../../../store/slices/chatSlice';
import ChatWorkspacePage from '../ChatWorkspacePage';

jest.mock('react-markdown', () => ({
  __esModule: true,
  default: ({ children }) => <div>{children}</div>,
}));
jest.mock('remark-gfm', () => ({ __esModule: true, default: () => null }));

function renderChat(answerMode, message, sources = []) {
  const store = configureStore({ reducer: { chat: chatReducer } });
  store.dispatch(sendMessage.pending('request-1', 'Study question'));
  store.dispatch(sendMessage.fulfilled({
    answer: 'The assistant response.',
    answer_mode: answerMode,
    message,
    reliability: answerMode === 'DOCUMENT_SUPPORTED' ? 'HIGH' : 'LOW',
    conflict_status: 'NONE',
    fallback_reason: null,
    claims: sources.length ? [{
      text: 'The claim is supported by the lesson.',
      classification: 'SUPPORTED',
      sources,
    }] : [],
    sources,
  }, 'request-1', 'Study question'));
  return render(
    <Provider store={store}>
      <ChatWorkspacePage />
    </Provider>
  );
}

describe('Chat answer mode and citations', () => {
  beforeEach(() => {
    Element.prototype.scrollIntoView = jest.fn();
  });

  test('shows document-supported mode and opens a retrieved passage citation', async () => {
    const user = userEvent.setup();
    renderChat('DOCUMENT_SUPPORTED', null, [{
      reference: 'R1', source: 'lesson.pdf', page: 4, text: 'Retrieved supporting excerpt.',
    }]);

    expect(screen.getByText('From your documents')).toBeInTheDocument();
    expect(screen.getByText('Reliability category: high')).toBeInTheDocument();
    expect(screen.getByText('The claim is supported by the lesson.')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /lesson.pdf · p.4/i }));
    expect(screen.getByText('Retrieved supporting excerpt.')).toBeInTheDocument();
  });

  test('shows the no-information response without document citations', () => {
    renderChat(
      'INSUFFICIENT_CONFIDENCE',
      'No relevant information was found in your uploaded documents to answer this question.',
    );

    expect(screen.getByText('Not found in your documents')).toBeInTheDocument();
    expect(screen.getByText(/No relevant information was found in your uploaded documents/)).toBeInTheDocument();
    expect(screen.queryByText(/general model knowledge/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Source citations')).not.toBeInTheDocument();
  });

  test('shows the document-limited mode', () => {
    renderChat('INSUFFICIENT_CONFIDENCE', 'More source material is needed.');

    expect(screen.getByText('Not found in your documents')).toBeInTheDocument();
    expect(screen.getByRole('note')).toHaveTextContent('More source material is needed');
  });
});
