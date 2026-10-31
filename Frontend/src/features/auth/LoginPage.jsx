import React, { useState, useEffect } from 'react';
import { Link, useNavigate, useLocation } from 'react-router-dom';
import { useDispatch, useSelector } from 'react-redux';
import { Eye, EyeOff, BookOpen, ShieldCheck, FileText, ArrowRight } from 'lucide-react';
import {
  loginUser,
  clearError,
  selectIsAuthenticated,
  selectAuthStatus,
  selectAuthError,
} from '../../store/slices/authSlice';
import TextInput from '../../components/TextInput/TextInput';
import Button from '../../components/Button/Button';
import Alert from '../../components/Alert/Alert';
import styles from './LoginPage.module.css';

export default function LoginPage() {
  const dispatch = useDispatch();
  const navigate = useNavigate();
  const location = useLocation();

  const isAuthenticated = useSelector(selectIsAuthenticated);
  const status = useSelector(selectAuthStatus);
  const authError = useSelector(selectAuthError);

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [clientErrors, setClientErrors] = useState({});

  const isLoading = status === 'loading';

  // Redirect if already authenticated
  useEffect(() => {
    if (isAuthenticated) {
      const destination = location.state?.from?.pathname || '/app';
      navigate(destination, { replace: true });
    }
  }, [isAuthenticated, navigate, location]);

  // Clear auth errors when leaving the page
  useEffect(() => {
    return () => {
      dispatch(clearError());
    };
  }, [dispatch]);

  const validate = () => {
    const errors = {};
    if (!email.trim()) {
      errors.email = 'Email address is required';
    } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) {
      errors.email = 'Please enter a valid email address';
    }

    if (!password) {
      errors.password = 'Password is required';
    }

    setClientErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!validate()) return;

    dispatch(loginUser({ Email: email.trim(), Password: password }));
  };

  const handleEmailChange = (e) => {
    setEmail(e.target.value);
    if (clientErrors.email) {
      setClientErrors((prev) => ({ ...prev, email: '' }));
    }
    if (authError) {
      dispatch(clearError());
    }
  };

  const handlePasswordChange = (e) => {
    setPassword(e.target.value);
    if (clientErrors.password) {
      setClientErrors((prev) => ({ ...prev, password: '' }));
    }
    if (authError) {
      dispatch(clearError());
    }
  };

  return (
    <div className={styles.container}>
      <div className={styles.authWrapper}>
        {/* ── Left Branding Panel ── */}
        <div className={styles.brandPanel}>
          <div className={styles.brandTop}>
            <div className={styles.brandBadge}>
              <BookOpen size={16} />
              <span>Personalized AI Learning</span>
            </div>
            <h2 className={styles.brandTitle}>Welcome Back to Your Academic Workspace</h2>
            <p className={styles.brandDesc}>
              Log in to access your course documents, review verified citations, and study with your
              knowledge-grounded learning assistant.
            </p>

            <ul className={styles.brandFeatures}>
              <li className={styles.brandFeatureItem}>
                <ShieldCheck size={16} className={styles.brandIcon} />
                <span>Answers grounded strictly in your study material</span>
              </li>
              <li className={styles.brandFeatureItem}>
                <FileText size={16} className={styles.brandIcon} />
                <span>Direct page-level source references</span>
              </li>
            </ul>
          </div>

          <div className={styles.brandFooter}>
            Session secured with HttpOnly authentication
          </div>
        </div>

        {/* ── Right Form Panel ── */}
        <div className={styles.formPanel}>
          <div className={styles.formHeader}>
            <h1 className={styles.formTitle}>Sign In</h1>
            <p className={styles.formSubtitle}>Enter your credentials to access your assistant</p>
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
              id="login-email"
              label="Email Address"
              type="email"
              value={email}
              onChange={handleEmailChange}
              placeholder="you@university.edu"
              required
              autoComplete="email"
              error={clientErrors.email}
              disabled={isLoading}
            />

            <TextInput
              id="login-password"
              label="Password"
              type={showPassword ? 'text' : 'password'}
              value={password}
              onChange={handlePasswordChange}
              placeholder="••••••••"
              required
              autoComplete="current-password"
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

            <div className={styles.submitArea}>
              <Button
                type="submit"
                variant="primary"
                size="md"
                fullWidth
                isLoading={isLoading}
              >
                Sign In
              </Button>
            </div>
          </form>

          <p className={styles.switchPrompt}>
            Don't have an account?
            <Link to="/signup" className={styles.switchLink}>
              Create one here
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
