import React, { useEffect, useState, useRef } from 'react';
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
  Trash2,
  Eye,
  X,
} from 'lucide-react';
import {
  deleteDocument,
  fetchDocumentDetails,
  fetchDocuments,
  uploadDocument,
  selectCatalogError,
  selectCatalogStatus,
  selectDeletingDocumentIds,
  selectDeleteErrors,
  selectDetailsError,
  selectDetailsStatus,
  selectSelectedDocument,
  selectUploadedFiles,
  selectUploadPhase,
  selectUploadProgress,
  selectDocumentError,
  selectLastUploadedFilename,
  clearUploadError,
  clearDocumentDetails,
  clearCatalogState,
} from '../../store/slices/documentSlice';
import { selectUser } from '../../store/slices/authSlice';
import { addToast } from '../../store/slices/uiSlice';
import Button from '../../components/Button/Button';
import Alert from '../../components/Alert/Alert';
import EmptyState from '../../components/EmptyState/EmptyState';
import styles from './DocumentLibraryPage.module.css';

export default function DocumentLibraryPage() {
  const dispatch = useDispatch();
  const fileInputRef = useRef(null);
  const user = useSelector(selectUser);

  const uploadedFiles = useSelector(selectUploadedFiles);
  const catalogStatus = useSelector(selectCatalogStatus);
  const catalogError = useSelector(selectCatalogError);
  const selectedDocument = useSelector(selectSelectedDocument);
  const detailsStatus = useSelector(selectDetailsStatus);
  const detailsError = useSelector(selectDetailsError);
  const deletingDocumentIds = useSelector(selectDeletingDocumentIds);
  const deleteErrors = useSelector(selectDeleteErrors);
  const uploadPhase = useSelector(selectUploadPhase);
  const uploadProgress = useSelector(selectUploadProgress);
  const documentError = useSelector(selectDocumentError);
  const lastUploadedFilename = useSelector(selectLastUploadedFilename);

  const [isDragOver, setIsDragOver] = useState(false);
  const [selectedFile, setSelectedFile] = useState(null);
  const [clientError, setClientError] = useState('');
  const [documentToDelete, setDocumentToDelete] = useState(null);

  const isUploading = uploadPhase === 'uploading';
  const isIndexing = uploadPhase === 'indexing';
  const isBusy = isUploading || isIndexing;

  useEffect(() => {
    if (user?.ID) dispatch(fetchDocuments(user.ID));
    else dispatch(clearCatalogState());
  }, [dispatch, user?.ID]);

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
        if (user?.ID) dispatch(fetchDocuments(user.ID));
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
    if (bytes == null) return 'Unavailable size';
    if (bytes === 0) return '0 B';
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const formatDate = (value) => {
    if (!value) return 'Date unavailable';
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? 'Date unavailable' : date.toLocaleString();
  };

  const handleDocumentDetails = (document) => {
    if (selectedDocument?.id === document.id) {
      dispatch(clearDocumentDetails());
      return;
    }
    if (user?.ID) dispatch(fetchDocumentDetails({ documentId: document.id, userId: user.ID }));
  };

  const handleDelete = () => {
    if (!documentToDelete || !user?.ID) return;
    dispatch(deleteDocument({ documentId: documentToDelete.id, userId: user.ID }))
      .unwrap()
      .then(() => {
        dispatch(addToast({ type: 'success', message: `"${documentToDelete.filename}" was deleted.` }));
        setDocumentToDelete(null);
      })
      .catch(() => {
        if (user?.ID) dispatch(fetchDocuments(user.ID));
      });
  };

  const handleRetryDelete = (document) => {
    if (!user?.ID) return;
    dispatch(deleteDocument({ documentId: document.id, userId: user.ID }))
      .unwrap()
      .catch(() => dispatch(fetchDocuments(user.ID)));
  };

  return (
    <div className={styles.page}>
      {/* ── Page Header ─────────────────────────────────────── */}
      <div className={styles.header}>
        <h1 className={styles.title}>Document Library &amp; PDF Ingestion</h1>
        <p className={styles.subtitle}>
          Upload text-based lecture slides, chapters, or textbook PDFs. Their text is extracted and prepared
          for search. Scanned PDFs are not currently processed with OCR; source references may be available
          when the assistant answers from document evidence.
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
          Supports text-based PDF documents. Scanned PDFs are not OCR-processed. Extracted text is added to your local search index.
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
                  Processing your PDF and preparing it for search. Please wait...
                </span>
              </>
            )}
          </div>
        </div>
      )}

      <h2 className={styles.sectionTitle}>Your Documents</h2>

      {catalogStatus === 'loading' && (
        <div className={styles.catalogMessage} role="status">Loading your documents…</div>
      )}

      {catalogStatus === 'failed' && (
        <div className={styles.catalogError} role="alert">
          <span>{catalogError}</span>
          <Button type="button" variant="secondary" size="sm" onClick={() => user?.ID && dispatch(fetchDocuments(user.ID))}>
            Retry
          </Button>
        </div>
      )}

      {catalogStatus === 'succeeded' && uploadedFiles.length === 0 && (
        <EmptyState
          icon={FileText}
          title="No documents uploaded yet"
          description="Upload your syllabus, lecture slides, or textbook notes above to start asking grounded questions."
        />
      )}

      {catalogStatus === 'succeeded' && uploadedFiles.length > 0 && (
        <div className={styles.documentList} role="list" aria-label="Your documents">
          {uploadedFiles.map((doc) => {
            const isDeleting = deletingDocumentIds.includes(doc.id);
            const statusLabel = {
              PROCESSING: 'Processing',
              READY: 'Ready for search',
              FAILED: 'Needs attention',
              DELETING: 'Deletion pending',
            }[doc.status] || doc.status;
            return (
              <div key={doc.id} className={styles.documentItem} role="listitem">
                <div className={styles.docInfo}>
                  <FileCheck size={24} className={styles.docIcon} aria-hidden="true" />
                  <div>
                    <p className={styles.docName}>{doc.filename}</p>
                    <p className={styles.docMeta}>
                      {formatFileSize(doc.file_size_bytes)} · {doc.page_count == null ? 'Pages unavailable' : `${doc.page_count} pages`} · Uploaded {formatDate(doc.uploaded_at)}
                    </p>
                  </div>
                </div>

                <div className={styles.documentActions}>
                  <span className={`${styles.docBadge} ${doc.status !== 'READY' ? styles.statusMuted : ''}`}>
                    {doc.status === 'READY' ? <CheckCircle2 size={12} aria-hidden="true" /> : <Clock size={12} aria-hidden="true" />}
                    <span>{doc.available ? statusLabel : 'File unavailable'}</span>
                  </span>
                  <Button
                    type="button"
                    variant="secondary"
                    size="sm"
                    disabled={isDeleting}
                    onClick={() => handleDocumentDetails(doc)}
                    aria-label={`Details for ${doc.filename}`}
                  >
                    <Eye size={14} /> Details
                  </Button>
                  <Button
                    type="button"
                    variant="secondary"
                    size="sm"
                    disabled={isDeleting}
                    isLoading={isDeleting}
                    onClick={() => setDocumentToDelete(doc)}
                    aria-label={`${doc.status === 'DELETING' ? 'Retry deletion of' : 'Delete'} ${doc.filename}`}
                  >
                    <Trash2 size={14} /> {doc.status === 'DELETING' ? 'Retry delete' : 'Delete'}
                  </Button>
                </div>
                {deleteErrors[doc.id] && (
                  <div className={styles.rowError} role="alert">
                    <span>{deleteErrors[doc.id]}</span>
                    <button type="button" onClick={() => handleRetryDelete(doc)}>Retry</button>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {(detailsStatus !== 'idle' || selectedDocument) && (
        <section className={styles.detailsPanel} aria-labelledby="document-details-title" aria-live="polite">
          <div className={styles.detailsHeader}>
            <h3 id="document-details-title">Document details</h3>
            <button type="button" className={styles.iconButton} onClick={() => dispatch(clearDocumentDetails())} aria-label="Close document details">
              <X size={18} />
            </button>
          </div>
          {detailsStatus === 'loading' && <p role="status">Loading document details…</p>}
          {detailsStatus === 'failed' && <p role="alert">{detailsError || 'Document details are unavailable.'}</p>}
          {detailsStatus === 'succeeded' && selectedDocument && (
            <dl className={styles.detailsGrid}>
              <dt>Filename</dt><dd>{selectedDocument.filename}</dd>
              <dt>Uploaded</dt><dd>{formatDate(selectedDocument.uploaded_at)}</dd>
              <dt>Last updated</dt><dd>{formatDate(selectedDocument.updated_at)}</dd>
              <dt>Size</dt><dd>{formatFileSize(selectedDocument.file_size_bytes)}</dd>
              <dt>Pages</dt><dd>{selectedDocument.page_count == null ? 'Unavailable' : selectedDocument.page_count}</dd>
              <dt>Status</dt><dd>{selectedDocument.available ? selectedDocument.status : 'File unavailable'}</dd>
            </dl>
          )}
        </section>
      )}

      {documentToDelete && (
        <div className={styles.confirmBackdrop}>
          <section className={styles.confirmDialog} role="alertdialog" aria-modal="true" aria-labelledby="delete-document-title" aria-describedby="delete-document-description">
            <h3 id="delete-document-title">Delete {documentToDelete.filename}?</h3>
            <p id="delete-document-description">This removes the PDF from your library and rebuilds your search index. This action cannot be undone.</p>
            <div className={styles.confirmActions}>
              <Button type="button" variant="secondary" onClick={() => setDocumentToDelete(null)}>Cancel</Button>
              <Button type="button" variant="primary" onClick={handleDelete}>Delete document</Button>
            </div>
          </section>
        </div>
      )}

      {/* ── Honest Backend Limitations Notice ───────────────── */}
      <div className={styles.limitationBanner} role="note">
        <Info size={20} className={styles.limitationIcon} aria-hidden="true" />
        <p className={styles.limitationText}>
          <strong>Knowledge Base Storage:</strong> Your PDFs and their local FAISS search index are stored on
          the backend host in storage scoped to your authenticated account. The library shows server-side
          document metadata; file availability depends on that local storage.
        </p>
      </div>
    </div>
  );
}
