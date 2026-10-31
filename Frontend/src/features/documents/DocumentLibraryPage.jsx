import React, { useState, useRef } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import {
  UploadCloud,
  FileText,
  CheckCircle2,
  AlertCircle,
  Clock,
  Info,
  ShieldCheck,
  FileCheck,
} from 'lucide-react';
import {
  uploadDocument,
  selectUploadedFiles,
  selectUploadPhase,
  selectUploadProgress,
  selectDocumentError,
  selectLastUploadedFilename,
  clearUploadError,
} from '../../store/slices/documentSlice';
import { addToast } from '../../store/slices/uiSlice';
import Button from '../../components/Button/Button';
import Alert from '../../components/Alert/Alert';
import EmptyState from '../../components/EmptyState/EmptyState';
import styles from './DocumentLibraryPage.module.css';

export default function DocumentLibraryPage() {
  const dispatch = useDispatch();
  const fileInputRef = useRef(null);

  const uploadedFiles = useSelector(selectUploadedFiles);
  const uploadPhase = useSelector(selectUploadPhase);
  const uploadProgress = useSelector(selectUploadProgress);
  const documentError = useSelector(selectDocumentError);
  const lastUploadedFilename = useSelector(selectLastUploadedFilename);

  const [isDragOver, setIsDragOver] = useState(false);
  const [selectedFile, setSelectedFile] = useState(null);
  const [clientError, setClientError] = useState('');

  const isUploading = uploadPhase === 'uploading';
  const isIndexing = uploadPhase === 'indexing';
  const isBusy = isUploading || isIndexing;

  const handleFileSelection = (file) => {
    setClientError('');
    dispatch(clearUploadError());

    if (!file) return;

    // Client-side PDF validation
    const isPdfExt = file.name.toLowerCase().endsWith('.pdf');
    const isPdfMime = file.type === 'application/pdf' || file.type === '';

    if (!isPdfExt || !isPdfMime) {
      setClientError('Only PDF files are supported. Please select a valid .pdf document.');
      return;
    }

    // Check duplicate in current session
    const isAlreadyUploaded = uploadedFiles.some((f) => f.filename === file.name);
    if (isAlreadyUploaded) {
      setClientError(`"${file.name}" has already been uploaded in this session.`);
      return;
    }

    setSelectedFile(file);
    dispatch(uploadDocument({ file }))
      .unwrap()
      .then((data) => {
        dispatch(
          addToast({
            type: 'success',
            message: `"${data.filename}" successfully uploaded and indexed!`,
          })
        );
        setSelectedFile(null);
      })
      .catch((err) => {
        // Error is captured in Redux
      });
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragOver(false);

    if (isBusy) return;

    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFileSelection(e.dataTransfer.files[0]);
    }
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    if (!isBusy) {
      setIsDragOver(true);
    }
  };

  const handleDragLeave = (e) => {
    e.preventDefault();
    setIsDragOver(false);
  };

  const handleFileInputChange = (e) => {
    if (e.target.files && e.target.files.length > 0) {
      handleFileSelection(e.target.files[0]);
      e.target.value = ''; // Reset input so same file could be re-selected if needed
    }
  };

  const formatFileSize = (bytes) => {
    if (!bytes) return 'Unknown size';
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  return (
    <div className={styles.page}>
      {/* ── Page Header ─────────────────────────────────────── */}
      <div className={styles.header}>
        <h1 className={styles.title}>Document Library &amp; PDF Ingestion</h1>
        <p className={styles.subtitle}>
          Upload lecture slides, chapters, or textbook PDFs. The backend parses text, extracts chunks,
          and generates vector embeddings so the AI can cite them in responses.
        </p>
      </div>

      {/* ── Client Error ────────────────────────────────────── */}
      {clientError && (
        <Alert
          type="error"
          message={clientError}
          onDismiss={() => setClientError('')}
          style={{ marginBottom: '24px' }}
        />
      )}

      {/* ── Server Error ────────────────────────────────────── */}
      {documentError && (
        <Alert
          type="error"
          message={documentError}
          onDismiss={() => dispatch(clearUploadError())}
          style={{ marginBottom: '24px' }}
        />
      )}

      {/* ── Upload Dropzone ─────────────────────────────────── */}
      <div
        className={`${styles.dropzone} ${isDragOver ? styles.dragOver : ''}`}
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onClick={() => !isBusy && fileInputRef.current?.click()}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            fileInputRef.current?.click();
          }
        }}
        aria-label="Upload PDF study material dropzone"
      >
        <input
          type="file"
          ref={fileInputRef}
          onChange={handleFileInputChange}
          accept=".pdf,application/pdf"
          className={styles.fileInputHidden}
          disabled={isBusy}
        />

        <div className={styles.dropzoneIconWrap} aria-hidden="true">
          <UploadCloud size={32} />
        </div>

        <h2 className={styles.dropzoneTitle}>
          {isBusy ? 'Processing Document...' : 'Drop your study PDF here, or click to browse'}
        </h2>

        <p className={styles.dropzoneHint}>
          Supports PDF documents only. Text will be chunked and indexed into the RAG vector store.
        </p>

        <Button
          type="button"
          variant="primary"
          size="md"
          isLoading={isBusy}
          disabled={isBusy}
          onClick={(e) => {
            e.stopPropagation();
            fileInputRef.current?.click();
          }}
        >
          {isBusy ? 'Uploading & Indexing...' : 'Select PDF File'}
        </Button>
      </div>

      {/* ── Active Upload Monitor ───────────────────────────── */}
      {isBusy && (
        <div className={styles.progressCard} aria-live="polite">
          <div className={styles.progressHeader}>
            <div className={styles.progressFilename}>
              <FileText size={16} />
              <span>{selectedFile?.name || 'Document'}</span>
            </div>
            <div className={styles.progressPercent}>
              {isUploading ? `${uploadProgress}%` : 'Indexing...'}
            </div>
          </div>

          <div className={styles.progressBarTrack}>
            <div
              className={styles.progressBarFill}
              style={{
                width: isUploading ? `${uploadProgress}%` : '100%',
                backgroundColor: isIndexing ? 'var(--color-navy-800)' : 'var(--color-amber-600)',
              }}
            />
          </div>

          <div className={styles.progressStatus}>
            {isUploading ? (
              <>
                <Clock size={14} />
                <span>Uploading PDF data to server...</span>
              </>
            ) : (
              <>
                <div className={styles.indexingSpinner} />
                <span>
                  Ingesting and indexing study material into vector database. Please wait...
                </span>
              </>
            )}
          </div>
        </div>
      )}

      {/* ── Current Session Uploads ─────────────────────────── */}
      <h2 className={styles.sectionTitle}>Uploaded in This Study Session</h2>

      {uploadedFiles.length === 0 ? (
        <EmptyState
          icon={FileText}
          title="No documents uploaded yet in this session"
          description="Upload your syllabus, lecture slides, or textbook notes above to start asking grounded questions."
        />
      ) : (
        <div className={styles.documentList} role="list" aria-label="Current session documents">
          {uploadedFiles.map((doc, idx) => (
            <div key={`${doc.filename}-${idx}`} className={styles.documentItem} role="listitem">
              <div className={styles.docInfo}>
                <FileCheck size={24} className={styles.docIcon} aria-hidden="true" />
                <div>
                  <p className={styles.docName}>{doc.filename}</p>
                  <p className={styles.docMeta}>
                    {formatFileSize(doc.size)} · Uploaded{' '}
                    {new Date(doc.uploadedAt).toLocaleTimeString([], {
                      hour: '2-digit',
                      minute: '2-digit',
                    })}
                  </p>
                </div>
              </div>

              <div className={styles.docBadge}>
                <CheckCircle2 size={12} aria-hidden="true" />
                <span>Indexed in RAG</span>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* ── Honest Backend Limitations Notice ───────────────── */}
      <div className={styles.limitationBanner} role="note">
        <Info size={20} className={styles.limitationIcon} aria-hidden="true" />
        <p className={styles.limitationText}>
          <strong>Knowledge Base Storage Architecture:</strong> Uploaded documents are converted into
          text chunks and embedded into the server's shared FAISS index. The current backend stores all
          materials persistently on disk, but does not yet expose remote file browsing or deletion endpoints.
          Documents listed above represent files uploaded during your active browser session.
        </p>
      </div>
    </div>
  );
}
