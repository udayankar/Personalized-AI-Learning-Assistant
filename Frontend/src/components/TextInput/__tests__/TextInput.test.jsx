import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import TextInput from '../TextInput';

describe('TextInput component', () => {
  it('renders input with label', () => {
    render(<TextInput id="email" label="Email Address" value="" onChange={() => {}} />);
    expect(screen.getByLabelText(/email address/i)).toBeInTheDocument();
  });

  it('renders error message and sets aria-invalid', () => {
    render(
      <TextInput
        id="email"
        label="Email Address"
        value=""
        onChange={() => {}}
        error="Invalid email"
      />
    );
    const input = screen.getByLabelText(/email address/i);
    expect(input).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByRole('alert')).toHaveTextContent('Invalid email');
  });

  it('handles user input change', () => {
    const handleChange = jest.fn();
    render(<TextInput id="email" label="Email" value="" onChange={handleChange} />);
    const input = screen.getByLabelText(/email/i);
    fireEvent.change(input, { target: { value: 'user@test.edu' } });
    expect(handleChange).toHaveBeenCalledTimes(1);
  });
});
