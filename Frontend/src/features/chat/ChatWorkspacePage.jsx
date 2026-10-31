import React, { useState, useEffect, useRef } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  Send,
  Sparkles,
  BookOpen,
  FileText,
  RotateCcw,
  X,
  AlertCircle,
  HelpCircle,
} from 'lucide-react';
import {
  sendMessage,
  selectMessages,
  selectIsGenerating,
  selectSelectedCitation,
  setSelectedCitation,
  retryLastMessage,
} from '../../store/slices/chatSlice';
import styles from './ChatWorkspacePage.module.css';

const EXAMPLE_QUERIES = [
  'What is image thresholding in OpenCV?',
  'Explain Python multithreading and the GIL',
  'How does an HTTP request work?',
  'What are the key concepts in Chapter 1?',
];

export default function ChatWorkspacePage() {
  const dispatch = useDispatch();
  const messages = useSelector(selectMessages);
  const isGenerating = useSelector(selectIsGenerating);
  const selectedCitation = useSelector(selectSelectedCitation);

  const [query, setQuery] = useState('');
  const textareaRef = useRef(null);
  const messageListRef = useRef(null);
  const messagesEndRef = useRef(null);

  // Auto-scroll to bottom whenever messages change or generation status changes
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isGenerating]);

  // Adjust textarea height dynamically
  const handleTextareaChange = (e) => {
    setQuery(e.target.value);
    const textarea = textareaRef.current;
    if (textarea) {
      textarea.style.height = 'auto';
      textarea.style.height = `${Math.min(textarea.scrollHeight, 160)}px`;
    }
  };

  const handleSend = () => {
    const trimmed = query.trim();
    if (!trimmed || isGenerating) return;

    dispatch(sendMessage(trimmed));
    setQuery('');
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleExampleClick = (example) => {
    if (isGenerating) return;
    dispatch(sendMessage(example));
  };

  const handleRetry = () => {
    const lastUserMessage = [...messages].reverse().find((m) => m.role === 'user');
    if (lastUserMessage) {
      dispatch(retryLastMessage());
      dispatch(sendMessage(lastUserMessage.content));
    }
  };

  return (
    <div className={styles.workspace}>
      <div className={styles.chatPanel}>
        {/* ── Message List ──────────────────────────────────── */}
        <div className={styles.messageList} ref={messageListRef} role="log" aria-live="polite">
          {messages.length === 0 ? (
            <div className={styles.emptyState}>
              <div className={styles.emptyIcon} aria-hidden="true">
                <Sparkles size={28} />
              </div>
              <h2 className={styles.emptyTitle}>AI Learning Workspace</h2>
              <p className={styles.emptyDesc}>
                Ask any question about your course materials. The assistant retrieves relevant passages
                from your uploaded PDFs and grounds its answers with page citations.
              </p>

              <div className={styles.exampleQueries}>
                {EXAMPLE_QUERIES.map((example) => (
                  <button
                    key={example}
                    type="button"
                    className={styles.exampleQuery}
                    onClick={() => handleExampleClick(example)}
                  >
                    {example}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            messages.map((message) => {
              const isUser = message.role === 'user';
              const isError = message.status === 'error';
              const isLoading = message.status === 'loading';

              return (
                <div
                  key={message.id}
                  className={`${styles.message} ${isUser ? styles.user : styles.assistant} ${
                    isError ? styles.error : ''
                  }`}
                >
                  <div
                    className={`${styles.messageAvatar} ${
                      isUser ? styles.avatarUser : styles.avatarAssistant
                    }`}
                    aria-hidden="true"
                  >
                    {isUser ? 'You' : <BookOpen size={16} />}
                  </div>

                  <div className={styles.messageBubble}>
                    <div className={styles.messageContent}>
                      {isLoading ? (
                        <div className={styles.typingIndicator} aria-label="Thinking">
                          <span className={styles.typingDot} />
                          <span className={styles.typingDot} />
                          <span className={styles.typingDot} />
                        </div>
                      ) : isError ? (
                        <div>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                            <AlertCircle size={16} />
                            <span>{message.content}</span>
                          </div>
                          <button
                            type="button"
                            className={styles.retryButton}
                            onClick={handleRetry}
                          >
                            <RotateCcw size={12} />
                            <span>Retry question</span>
                          </button>
                        </div>
                      ) : (
                        <div className={styles.markdownBody}>
                          <ReactMarkdown remarkPlugins={[remarkGfm]}>
                            {message.content}
                          </ReactMarkdown>
                        </div>
                      )}

                      {/* Source Citations */}
                      {!isUser && message.sources && message.sources.length > 0 && (
                        <div className={styles.sourcesRow} aria-label="Source citations">
                          {message.sources.map((src, idx) => (
                            <button
                              key={`${src.source}-${src.page}-${idx}`}
                              type="button"
                              className={styles.citationTag}
                              onClick={() => dispatch(setSelectedCitation(src))}
                              title={`Inspect excerpt from ${src.source} (Page ${src.page})`}
                            >
                              <FileText size={12} aria-hidden="true" />
                              <span>
                                {src.source} · p.{src.page}
                              </span>
                            </button>
                          ))}
                        </div>
                      )}
                    </div>

                    <div className={styles.messageTime}>
                      {new Date(message.timestamp).toLocaleTimeString([], {
                        hour: '2-digit',
                        minute: '2-digit',
                      })}
                    </div>
                  </div>
                </div>
              );
            })
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* ── Input Composer ────────────────────────────────── */}
        <div className={styles.composerArea}>
          <div className={styles.composerWrapper}>
            <textarea
              ref={textareaRef}
              rows={1}
              value={query}
              onChange={handleTextareaChange}
              onKeyDown={handleKeyDown}
              placeholder="Ask a question about your study materials..."
              className={styles.composerTextarea}
              disabled={isGenerating}
              aria-label="Ask a question"
            />
            <button
              type="button"
              className={styles.sendButton}
              onClick={handleSend}
              disabled={!query.trim() || isGenerating}
              aria-label="Send question"
            >
              <Send size={16} />
            </button>
          </div>
          <p className={styles.composerHint}>
            Press <kbd style={{ fontFamily: 'inherit', fontWeight: 600 }}>Enter</kbd> to send,{' '}
            <kbd style={{ fontFamily: 'inherit', fontWeight: 600 }}>Shift + Enter</kbd> for a new line
          </p>
        </div>
      </div>

      {/* ── Source Viewer Side Drawer ───────────────────────── */}
      {selectedCitation && (
        <>
          <div
            className={styles.drawerOverlay}
            onClick={() => dispatch(setSelectedCitation(null))}
            aria-hidden="true"
          />
          <aside className={styles.drawer} role="dialog" aria-label="Source excerpt inspector">
            <div className={styles.drawerHeader}>
              <h3 className={styles.drawerTitle}>Source Citation</h3>
              <button
                type="button"
                className={styles.drawerCloseBtn}
                onClick={() => dispatch(setSelectedCitation(null))}
                aria-label="Close source drawer"
              >
                <X size={20} />
              </button>
            </div>

            <div className={styles.drawerBody}>
              <p className={styles.drawerFilename}>{selectedCitation.source}</p>
              <div className={styles.drawerPage}>
                <BookOpen size={12} />
                <span>Page {selectedCitation.page}</span>
              </div>

              <p className={styles.drawerExcerptLabel}>Retrieved Excerpt</p>
              <div className={styles.drawerExcerpt}>
                {selectedCitation.text}
              </div>
            </div>
          </aside>
        </>
      )}
    </div>
  );
}
