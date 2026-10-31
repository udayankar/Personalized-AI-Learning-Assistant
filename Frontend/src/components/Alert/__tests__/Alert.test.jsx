import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import Alert from '../Alert';

describe('Alert component', () => {
  it('renders alert message', () => {
    render(<Alert type="error" message="Invalid credentials" />);
    expect(screen.getByRole('alert')).toHaveTextContent('Invalid credentials');
  });

  it('renders dismiss button when onDismiss is provided', () => {
    const handleDismiss = jest.fn();
    render(<Alert type="info" message="Notice" onDismiss={handleDismiss} />);
    const dismissButton = screen.getByRole('button', { name: /dismiss alert/i });
    expect(dismissButton).toBeInTheDocument();
    fireEvent.click(dismissButton);
    expect(handleDismiss).toHaveBeenCalledTimes(1);
  });

  it('returns null when no content is provided', () => {
    const { container } = render(<Alert />);
    expect(container.firstChild).toBeNull();
  });
});
