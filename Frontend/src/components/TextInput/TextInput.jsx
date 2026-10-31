/**
 * TextInput — Accessible labeled input with optional trailing slot,
 *             error message, and hint text.
 *
 * Props:
 *   id          — HTML id (also wires label htmlFor)
 *   label       — label text
 *   required    — shows asterisk and sets aria-required
 *   type        — input type                       (default: 'text')
 *   value       — controlled value
 *   onChange    — change handler
 *   placeholder — placeholder text
 *   error       — string: inline error message (also triggers error styling)
 *   hint        — string: helper/hint text below input
 *   trailing    — React node: icon/button rendered inside input on the right
 *   disabled    — boolean
 *   autoComplete — autocomplete attribute
 *   All other props forwarded to <input>
 */

import React from 'react';
import styles from './TextInput.module.css';

export default function TextInput({
  id,
  label,
  required = false,
  type = 'text',
  value,
  onChange,
  placeholder,
  error,
  hint,
  trailing,
  disabled = false,
  autoComplete,
  className = '',
  ...rest
}) {
  const inputClasses = [
    styles.input,
    error ? styles.error : '',
    trailing ? styles.hasTrailing : '',
    className,
  ]
    .filter(Boolean)
    .join(' ');

  const errorId = id ? `${id}-error` : undefined;
  const hintId  = id ? `${id}-hint`  : undefined;

  const describedBy = [
    error ? errorId : null,
    hint  ? hintId  : null,
  ]
    .filter(Boolean)
    .join(' ') || undefined;

  return (
    <div className={styles.group}>
      {label && (
        <label htmlFor={id} className={styles.label}>
          {label}
          {required && <span className={styles.required} aria-hidden="true"> *</span>}
        </label>
      )}

      <div className={styles.inputWrapper}>
        <input
          id={id}
          type={type}
          value={value}
          onChange={onChange}
          placeholder={placeholder}
          disabled={disabled}
          required={required}
          autoComplete={autoComplete}
          aria-invalid={!!error}
          aria-describedby={describedBy}
          className={inputClasses}
          {...rest}
        />
        {trailing && (
          <span className={styles.trailing}>{trailing}</span>
        )}
      </div>

      {error && (
        <span id={errorId} className={styles.errorMsg} role="alert">
          {error}
        </span>
      )}

      {!error && hint && (
        <span id={hintId} className={styles.hint}>
          {hint}
        </span>
      )}
    </div>
  );
}
