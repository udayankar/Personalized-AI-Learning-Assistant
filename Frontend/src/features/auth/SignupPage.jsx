import React, { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useDispatch, useSelector } from 'react-redux';
import { Eye, EyeOff, BookOpen, ShieldCheck, FileText, Sparkles } from 'lucide-react';
import {
  signupUser,
  clearError,
  selectIsAuthenticated,
  selectAuthStatus,
  selectAuthError,
} from '../../store/slices/authSlice';
import TextInput from '../../components/TextInput/TextInput';
import Button from '../../components/Button/Button';
import Alert from '../../components/Alert/Alert';
import styles from './SignupPage.module.css';

export default function SignupPage() {
  const dispatch = useDispatch();
  const navigate = useNavigate();

  const isAuthenticated = useSelector(selectIsAuthenticated);
  const status = useSelector(selectAuthStatus);
  const authError = useSelector(selectAuthError);

  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [clientErrors, setClientErrors] = useState({});

  const isLoading = status === 'loading';

  // Redirect if authenticated
  useEffect(() => {
    if (isAuthenticated) {
      navigate('/app', { replace: true });
    }
  }, [isAuthenticated, navigate]);

  // Clear auth errors on unmount
  useEffect(() => {
    return () => {
      dispatch(clearError());
    };
  }, [dispatch]);

  const validate = () => {
    const errors = {};
    if (!name.trim()) {
      errors.name = 'Full name is required';
    } else if (name.trim().length > 100) {
      errors.name = 'Name must be 100 characters or fewer';
    }

    if (!email.trim()) {
      errors.email = 'Email address is required';
    } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) {
      errors.email = 'Please enter a valid email address';
    }

    if (!password) {
      errors.password = 'Password is required';
    } else if (password.length < 8) {
      errors.password = 'Password must be at least 8 characters long';
    } else if (password.length > 128) {
      errors.password = 'Password must be 128 characters or fewer';
    }

    setClientErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!validate()) return;

    dispatch(
      signupUser({
        Name: name.trim(),
        Email: email.trim(),
        Password: password,
      })
    );
  };

  const handleNameChange = (e) => {
    setName(e.target.value);
    if (clientErrors.name) setClientErrors((prev) => ({ ...prev, name: '' }));
    if (authError) dispatch(clearError());
  };

  const handleEmailChange = (e) => {
    setEmail(e.target.value);
    if (clientErrors.email) setClientErrors((prev) => ({ ...prev, email: '' }));
    if (authError) dispatch(clearError());
  };

  const handlePasswordChange = (e) => {
    setPassword(e.target.value);
    if (clientErrors.password) setClientErrors((prev) => ({ ...prev, password: '' }));
    if (authError) dispatch(clearError());
  };

  return (
    <div className={styles.container}>
      <div className={styles.authWrapper}>
        {/* ── Left Branding Panel ── */}
        <div className={styles.brandPanel}>
          <div className={styles.brandTop}>
            <div className={styles.brandBadge}>
              <Sparkles size={16} />
              <span>Join the Learning Revolution</span>
            </div>
            <h2 className={styles.brandTitle}>Build Your Knowledge With Grounded AI</h2>
            <p className={styles.brandDesc}>
              Create your account to start uploading PDF study materials, asking deep conceptual
              questions, and reviewing verified citations.
            </p>

            <ul className={styles.brandFeatures}>
              <li className={styles.brandFeatureItem}>
                <ShieldCheck size={16} className={styles.brandIcon} />
                <span>Zero hallucinations — citations from your exact files</span>
              </li>
              <li className={styles.brandFeatureItem}>
                <FileText size={16} className={styles.brandIcon} />
                <span>Page-referenced excerpts for every explanation</span>
              </li>
              <li className={styles.brandFeatureItem}>
                <BookOpen size={16} className={styles.brandIcon} />
                <span>Persistent knowledge base ready whenever you study</span>
              </li>
            </ul>
          </div>

          <div className={styles.brandFooter}>
            By registering, you agree to our academic study terms
          </div>
        </div>

        {/* ── Right Form Panel ── */}
        <div className={styles.formPanel}>
          <div className={styles.formHeader}>
            <h1 className={styles.formTitle}>Create Account</h1>
            <p className={styles.formSubtitle}>Get started with your personalized learning assistant</p>
          </div>

          {authError && (
            <Alert
              type="error"
              message={authError}
              onDismiss={() => dispatch(clearError())}
              style={{ marginBottom: '16px' }}
            />
          )}

          <form onSubmit={handleSubmit} className={styles.form} noValidate>
            <TextInput
              id="signup-name"
              label="Full Name"
              type="text"
              value={name}
              onChange={handleNameChange}
              placeholder="Jane Doe"
              required
              autoComplete="name"
              error={clientErrors.name}
              disabled={isLoading}
            />

            <TextInput
              id="signup-email"
              label="Email Address"
              type="email"
              value={email}
              onChange={handleEmailChange}
              placeholder="jane@university.edu"
              required
              autoComplete="email"
              error={clientErrors.email}
              disabled={isLoading}
            />

            <TextInput
              id="signup-password"
              label="Password"
              type={showPassword ? 'text' : 'password'}
              value={password}
              onChange={handlePasswordChange}
              placeholder="At least 8 characters"
              required
              autoComplete="new-password"
              error={clientErrors.password}
              disabled={isLoading}
              trailing={
                <button
                  type="button"
                  className={styles.eyeButton}
                  onClick={() => setShowPassword(!showPassword)}
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                  tabIndex={-1}
                >
                  {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                </button>
              }
            />

            <p className={styles.passwordHint}>
              Must be at least 8 characters long.
            </p>

            <div className={styles.submitArea}>
              <Button
                type="submit"
                variant="primary"
                size="md"
                fullWidth
                isLoading={isLoading}
              >
                Create Account
              </Button>
            </div>
          </form>

          <p className={styles.switchPrompt}>
            Already have an account?
            <Link to="/login" className={styles.switchLink}>
              Sign in instead
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
