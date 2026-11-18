jest.mock('../apiClient', () => ({
  __esModule: true,
  default: { post: jest.fn() },
}));

import apiClient from '../apiClient';
import { sendQuery } from '../chatService';

describe('chatService', () => {
  beforeEach(() => jest.clearAllMocks());

  test('allows a long bounded RAG request without changing other API timeouts', async () => {
    apiClient.post.mockResolvedValue({ data: { answer: 'Document grounded answer' } });

    await expect(sendQuery('Question from my PDF')).resolves.toEqual({
      answer: 'Document grounded answer',
    });
    expect(apiClient.post).toHaveBeenCalledWith(
      '/chat/query',
      { query: 'Question from my PDF' },
      { timeout: 900000 },
    );
  });
});
