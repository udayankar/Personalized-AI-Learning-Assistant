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
              Connect your lecture notes, textbooks, and syllabus PDFs. Ask questions and get clear,
              rigorous answers grounded strictly in your verified study materials.
            </p>

            <div className={styles.heroCtas}>
              <Link to="/signup" className={styles.ctaPrimary}>
                <span>Start Learning Free</span>
                <ArrowRight size={18} aria-hidden="true" />
              </Link>
              <Link to="/login" className={styles.ctaSecondary}>
                Sign In
              </Link>
            </div>

            <div className={styles.trustBadge}>
              <ShieldCheck size={18} className={styles.trustBadgeIcon} aria-hidden="true" />
              <span>Every answer cited with document name and exact page numbers</span>
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
                  <p className={styles.heroCardTitle}>AI Academic Tutor</p>
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
                <p className={styles.heroCardAnswerLabel}>Grounded Response</p>
                <p className={styles.heroCardAnswerText}>
                  Simple thresholding applies a fixed pixel threshold across the entire image. If a pixel's
                  intensity is below the threshold, it is set to 0; otherwise, it is assigned the maximum value.
                </p>
                <div className={styles.heroCardSource}>
                  <FileText size={14} />
                  <p className={styles.heroCardSourceLabel}>Source: opencv-notes.pdf · Page 14</p>
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
              Unlike generic chat bots that hallucinate answers, this assistant operates on your specific course curriculum.
            </p>
          </div>

          <div className={styles.featuresGrid}>
            <div className={styles.featureCard}>
              <div className={styles.featureIconWrapper}>
                <UploadCloud size={28} />
              </div>
              <h3 className={styles.featureTitle}>Upload Study Material</h3>
              <p className={styles.featureDescription}>
                Ingest PDF textbooks, lecture slides, and notes. The backend extracts text, builds semantic embeddings, and stores them in FAISS vector indices.
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
              <h3 className={styles.featureTitle}>Verified Source Citations</h3>
              <p className={styles.featureDescription}>
                Every response displays the source document and page number. Inspect excerpts instantly in the side drawer to cross-check explanations.
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
            <h2 className={styles.sectionHeading}>Three Steps to Master Your Coursework</h2>
            <p className={styles.sectionSubheading}>
              Turn dense PDFs into an interactive personal study partner in seconds.
            </p>
          </div>

          <div className={styles.stepsRow}>
            <div className={styles.step}>
              <div className={styles.stepNumber}>1</div>
              <h3 className={styles.stepTitle}>Upload PDF Notes</h3>
              <p className={styles.stepDescription}>
                Drag and drop your syllabus or chapter PDFs into the Document Library to index them into vector storage.
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
                Study formatted explanations with markdown, equations, and direct links to the relevant textbook pages.
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
              We believe in honest architecture. Here is what is live today versus what is actively being built.
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
                  <span>Full PDF upload and automated text chunking with FAISS indexing</span>
                </li>
                <li className={`${styles.capabilityItem} ${styles.capabilityItemAvailable}`}>
                  <CheckCircle2 size={16} className={`${styles.capabilityIcon} ${styles.capabilityIconAvailable}`} />
                  <span>RAG semantic retrieval and Gemini-powered pedagogical explanations</span>
                </li>
                <li className={`${styles.capabilityItem} ${styles.capabilityItemAvailable}`}>
                  <CheckCircle2 size={16} className={`${styles.capabilityIcon} ${styles.capabilityIconAvailable}`} />
                  <span>Exact source document tracking with page numbers and text snippets</span>
                </li>
                <li className={`${styles.capabilityItem} ${styles.capabilityItemAvailable}`}>
                  <CheckCircle2 size={16} className={`${styles.capabilityIcon} ${styles.capabilityIconAvailable}`} />
                  <span>Secure JWT HttpOnly cookie authentication and account registration</span>
                </li>
                <li className={`${styles.capabilityItem} ${styles.capabilityItemAvailable}`}>
                  <CheckCircle2 size={16} className={`${styles.capabilityIcon} ${styles.capabilityIconAvailable}`} />
                  <span>Persistent knowledge base storage on the server across sessions</span>
                </li>
              </ul>
            </div>

            <div className={`${styles.capabilityPanel} ${styles.capabilityPanelDev}`}>
              <h3 className={`${styles.capabilityPanelHeading} ${styles.capabilityPanelHeadingDev}`}>
                <Clock size={20} className={styles.capabilityIconDev} />
                <span>In Active Development</span>
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
                  <span>Per-user document isolation and server-side document file management</span>
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
            Join the academic study platform that answers your questions using your own course material.
          </p>
          <Link to="/signup" className={styles.ctaSectionButton}>
            <span>Create Your Account</span>
            <ArrowRight size={18} aria-hidden="true" />
          </Link>
          <p className={styles.ctaSectionNote}>Free and open-source learning platform</p>
        </div>
      </section>
    </div>
  );
}
