import React from 'react';
import styles from './Card.module.css';

export default function Card({
  children,
  className = '',
  padding = 'md',
  shadow = 'sm',
  as: Component = 'div',
  ...props
}) {
  const paddingClass = styles[`padding-${padding}`] || styles['padding-md'];
  const shadowClass = styles[`shadow-${shadow}`] || styles['shadow-sm'];

  return (
    <Component className={`${styles.card} ${paddingClass} ${shadowClass} ${className}`} {...props}>
      {children}
    </Component>
  );
}
