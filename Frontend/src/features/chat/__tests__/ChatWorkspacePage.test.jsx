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
    reliability: answerMode === 'DOCUMENT_SUPPORTED' ? 'HIGH' : (answerMode === 'GENERAL_KNOWLEDGE' ? 'MODERATE' : 'LOW'),
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

  test('shows general knowledge disclosure without document citations', () => {
    renderChat(
      'GENERAL_KNOWLEDGE',
      'The uploaded documents do not sufficiently cover this question. The explanation is based on general model knowledge.',
    );

    expect(screen.getByText('General model knowledge')).toBeInTheDocument();
    expect(screen.getByRole('note')).toHaveTextContent('not sufficiently cover');
    expect(screen.getByText('Reliability category: moderate')).toBeInTheDocument();
    expect(screen.queryByLabelText('Source citations')).not.toBeInTheDocument();
  });

  test('shows insufficient-confidence mode', () => {
    renderChat('INSUFFICIENT_CONFIDENCE', 'More source material is needed.');

    expect(screen.getByText('Unable to answer confidently')).toBeInTheDocument();
    expect(screen.getByRole('note')).toHaveTextContent('More source material is needed');
  });
});
