import React from 'react';
import { Link } from 'react-router-dom';
import {
  BookOpen,
  Search,
  FileText,
  CheckCircle2,
  Clock,
  ArrowRight,
  ShieldCheck,
  Sparkles,
  UploadCloud,
  FileCheck,
} from 'lucide-react';
import styles from './LandingPage.module.css';

export default function LandingPage() {
  return (
    <div className={styles.landingPage}>
      {/* ── 1. HERO SECTION ─────────────────────────────────── */}
      <section className={styles.hero} aria-label="Hero section">
        <div className={styles.heroInner}>
          <div className={styles.heroCopy}>
            <div className={styles.heroEyebrow}>
              <Sparkles size={16} aria-hidden="true" />
              <span>Grounded Academic Assistant</span>
            </div>

            <h1 className={styles.heroHeading}>
              Study Smarter with <span className={styles.heroHeadingAccent}>AI-Powered</span> Learning
            </h1>

            <p className={styles.heroSubheading}>
              Upload text-based lecture notes, textbooks, and syllabus PDFs. Answers use retrieved
              passages from your documents, with citations when available. If the documents do not
              contain relevant information, the assistant says so. Scanned PDFs are not OCR-processed.
            </p>

            <div className={styles.heroCtas}>
              <Link to="/signup" className={styles.ctaPrimary}>
                <span>Create an Account</span>
                <ArrowRight size={18} aria-hidden="true" />
              </Link>
              <Link to="/login" className={styles.ctaSecondary}>
                Sign In
              </Link>
            </div>

            <div className={styles.trustBadge}>
              <ShieldCheck size={18} className={styles.trustBadgeIcon} aria-hidden="true" />
              <span>Source references are shown when document evidence is available</span>
            </div>
          </div>

          {/* Hero Visual Mockup */}
          <div className={styles.heroVisual} aria-hidden="true">
            <div className={styles.heroCard}>
              <div className={styles.heroCardHeader}>
                <div className={styles.heroCardIcon}>
                  <BookOpen size={24} />
                </div>
                <div>
                  <p className={styles.heroCardTitle}>Example Document-Supported Answer</p>
                  <p className={styles.heroCardSubtitle}>Retrieval-Augmented Generation (RAG)</p>
                </div>
              </div>

              <div className={styles.heroCardQuestion}>
                <p className={styles.heroCardQuestionLabel}>Student Question</p>
                <p className={styles.heroCardQuestionText}>
                  "What is simple thresholding in OpenCV and how is the cutoff applied?"
                </p>
              </div>

              <div className={styles.heroCardAnswer}>
                <p className={styles.heroCardAnswerLabel}>Illustrative Response</p>
                <p className={styles.heroCardAnswerText}>
                  Simple thresholding applies a fixed pixel threshold across the entire image. If a pixel's
                  intensity is below the threshold, it is set to 0; otherwise, it is assigned the maximum value.
                </p>
                <div className={styles.heroCardSource}>
                  <FileText size={14} />
                  <p className={styles.heroCardSourceLabel}>Example source: opencv-notes.pdf · Page 14</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── 2. FEATURES SECTION ─────────────────────────────── */}
      <section className={styles.features} aria-label="Core features">
        <div className={styles.sectionInner}>
          <div className={styles.featuresHeader}>
            <span className={styles.sectionLabel}>Key Capabilities</span>
            <h2 className={styles.sectionHeading}>Engineered for Focused Academic Study</h2>
            <p className={styles.sectionSubheading}>
              The assistant answers from retrieved document passages and identifies when the documents do not contain an answer.
            </p>
          </div>

          <div className={styles.featuresGrid}>
            <div className={styles.featureCard}>
              <div className={styles.featureIconWrapper}>
                <UploadCloud size={28} />
              </div>
              <h3 className={styles.featureTitle}>Upload Study Material</h3>
              <p className={styles.featureDescription}>
                Upload text-based PDFs. Their text is extracted and added to an account-specific local search index; scanned PDFs are not OCR-processed.
              </p>
            </div>

            <div className={styles.featureCard}>
              <div className={styles.featureIconWrapper}>
                <Search size={28} />
              </div>
              <h3 className={styles.featureTitle}>Semantic Retrieval</h3>
              <p className={styles.featureDescription}>
                Ask questions in plain language. The RAG pipeline performs high-dimensional vector search to retrieve the most relevant passages from your texts.
              </p>
            </div>

            <div className={styles.featureCard}>
              <div className={styles.featureIconWrapper}>
                <FileCheck size={28} />
              </div>
              <h3 className={styles.featureTitle}>Source References</h3>
              <p className={styles.featureDescription}>
                Document-supported responses can include source documents and page details. Review available excerpts to check the answer against the material.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* ── 3. HOW IT WORKS ─────────────────────────────────── */}
      <section className={styles.howItWorks} aria-label="How it works">
        <div className={styles.sectionInner}>
          <div className={styles.stepsHeader}>
            <span className={styles.sectionLabel}>Simple Workflow</span>
            <h2 className={styles.sectionHeading}>Three Steps to Study with Your Materials</h2>
            <p className={styles.sectionSubheading}>
              Upload supported PDFs, ask questions, and review answers with available source information.
            </p>
          </div>

          <div className={styles.stepsRow}>
            <div className={styles.step}>
              <div className={styles.stepNumber}>1</div>
              <h3 className={styles.stepTitle}>Upload PDF Notes</h3>
              <p className={styles.stepDescription}>
                Upload text-based syllabus or chapter PDFs to add their content to your account's local search index.
              </p>
            </div>

            <div className={styles.step}>
              <div className={styles.stepNumber}>2</div>
              <h3 className={styles.stepTitle}>Ask Conceptual Questions</h3>
              <p className={styles.stepDescription}>
                Type questions in the AI Learning Workspace. Request explanations, code examples, or comparisons.
              </p>
            </div>

            <div className={styles.step}>
              <div className={styles.stepNumber}>3</div>
              <h3 className={styles.stepTitle}>Review Cited Answers</h3>
              <p className={styles.stepDescription}>
                Review AI-generated answers and, when available, the document excerpts they reference.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* ── 4. HONEST CAPABILITIES ──────────────────────────── */}
      <section className={styles.capabilities} aria-label="Current capabilities and roadmap">
        <div className={styles.sectionInner}>
          <div className={styles.capabilitiesHeader}>
            <span className={styles.sectionLabel}>Transparency</span>
            <h2 className={styles.sectionHeading}>Current Status &amp; Development Roadmap</h2>
            <p className={styles.sectionSubheading}>
              Here is what is available now and what is planned for future development.
            </p>
          </div>

          <div className={styles.capabilitiesGrid}>
            <div className={`${styles.capabilityPanel} ${styles.capabilityPanelAvailable}`}>
              <h3 className={`${styles.capabilityPanelHeading} ${styles.capabilityPanelHeadingAvailable}`}>
                <CheckCircle2 size={20} className={styles.capabilityIconAvailable} />
                <span>Currently Live &amp; Supported</span>
              </h3>
              <ul className={styles.capabilityList}>
                <li className={`${styles.capabilityItem} ${styles.capabilityItemAvailable}`}>
                  <CheckCircle2 size={16} className={`${styles.capabilityIcon} ${styles.capabilityIconAvailable}`} />
                  <span>Text-based PDF upload and processing for document search; scanned PDFs are not OCR-processed</span>
                </li>
                <li className={`${styles.capabilityItem} ${styles.capabilityItemAvailable}`}>
                  <CheckCircle2 size={16} className={`${styles.capabilityIcon} ${styles.capabilityIconAvailable}`} />
                  <span>Document-grounded answers with source excerpts, or a clear message when no supporting information is found</span>
                </li>
                <li className={`${styles.capabilityItem} ${styles.capabilityItemAvailable}`}>
                  <CheckCircle2 size={16} className={`${styles.capabilityIcon} ${styles.capabilityIconAvailable}`} />
                  <span>Source document excerpts and page details when available</span>
                </li>
                <li className={`${styles.capabilityItem} ${styles.capabilityItemAvailable}`}>
                  <CheckCircle2 size={16} className={`${styles.capabilityIcon} ${styles.capabilityIconAvailable}`} />
                  <span>Account signup and login with an HttpOnly JWT cookie and CSRF checks for unsafe browser requests</span>
                </li>
                <li className={`${styles.capabilityItem} ${styles.capabilityItemAvailable}`}>
                  <CheckCircle2 size={16} className={`${styles.capabilityIcon} ${styles.capabilityIconAvailable}`} />
                  <span>Account-specific document folders and search indexes on the server; persistence across deployments depends on host storage</span>
                </li>
                <li className={`${styles.capabilityItem} ${styles.capabilityItemAvailable}`}>
                  <CheckCircle2 size={16} className={`${styles.capabilityIcon} ${styles.capabilityIconAvailable}`} />
                  <span>Local FAISS vector search index for each account</span>
                </li>
              </ul>
            </div>

            <div className={`${styles.capabilityPanel} ${styles.capabilityPanelDev}`}>
              <h3 className={`${styles.capabilityPanelHeading} ${styles.capabilityPanelHeadingDev}`}>
                <Clock size={20} className={styles.capabilityIconDev} />
                <span>Planned</span>
              </h3>
              <ul className={styles.capabilityList}>
                <li className={`${styles.capabilityItem} ${styles.capabilityItemDev}`}>
                  <Clock size={16} className={`${styles.capabilityIcon} ${styles.capabilityIconDev}`} />
                  <span>Continuous learner model tracking proficiency levels and skills</span>
                </li>
                <li className={`${styles.capabilityItem} ${styles.capabilityItemDev}`}>
                  <Clock size={16} className={`${styles.capabilityIcon} ${styles.capabilityIconDev}`} />
                  <span>Machine learning recommendation engine ranking next study topics</span>
                </li>
                <li className={`${styles.capabilityItem} ${styles.capabilityItemDev}`}>
                  <Clock size={16} className={`${styles.capabilityIcon} ${styles.capabilityIconDev}`} />
                  <span>Adaptive assessment quizzes updating topic mastery scores</span>
                </li>
                <li className={`${styles.capabilityItem} ${styles.capabilityItemDev}`}>
                  <Clock size={16} className={`${styles.capabilityIcon} ${styles.capabilityIconDev}`} />
                  <span>Tools to browse, delete, and reprocess uploaded documents</span>
                </li>
                <li className={`${styles.capabilityItem} ${styles.capabilityItemDev}`}>
                  <Clock size={16} className={`${styles.capabilityIcon} ${styles.capabilityIconDev}`} />
                  <span>Multi-session persistent chat history saved to the database</span>
                </li>
              </ul>
            </div>
          </div>
        </div>
      </section>

      {/* ── 5. FINAL CTA ────────────────────────────────────── */}
      <section className={styles.ctaSection} aria-label="Get started call to action">
        <div className={styles.ctaSectionInner}>
          <h2 className={styles.ctaSectionHeading}>Ready to Transform Your Study Experience?</h2>
          <p className={styles.ctaSectionSubtext}>
            Ask questions about your course material and receive answers grounded in retrieved document passages.
          </p>
          <Link to="/signup" className={styles.ctaSectionButton}>
            <span>Create Your Account</span>
            <ArrowRight size={18} aria-hidden="true" />
          </Link>
          <p className={styles.ctaSectionNote}>Independent learning assistant project under development</p>
        </div>
      </section>
    </div>
  );
}
