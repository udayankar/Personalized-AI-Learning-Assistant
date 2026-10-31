/**
 * Button — Reusable button component
 *
 * Props:
 *   variant   — 'primary' | 'secondary' | 'ghost' | 'danger'  (default: 'primary')
 *   size      — 'sm' | 'md' | 'lg'                            (default: 'md')
 *   fullWidth — boolean                                        (default: false)
 *   isLoading — boolean, shows spinner and disables           (default: false)
 *   disabled  — boolean                                        (default: false)
 *   type      — button type attribute                          (default: 'button')
 *   onClick   — click handler
 *   children  — button label / content
 *   All other props forwarded to <button>
 */

import React from 'react';
import styles from './Button.module.css';

export default function Button({
  variant = 'primary',
  size = 'md',
  fullWidth = false,
  isLoading = false,
  disabled = false,
  type = 'button',
  onClick,
  children,
  className = '',
  ...rest
}) {
  const classes = [
    styles.btn,
    styles[variant] ?? styles.primary,
    styles[size] ?? styles.md,
    fullWidth ? styles.fullWidth : '',
    className,
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <button
      type={type}
      className={classes}
      disabled={disabled || isLoading}
      onClick={onClick}
      aria-busy={isLoading}
      {...rest}
    >
      {isLoading && <span className={styles.spinner} aria-hidden="true" />}
      {children}
    </button>
  );
}
