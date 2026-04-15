// src/components/common/Input.test.tsx

import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { Input } from './Input';

describe('Input', () => {
  it('renders a basic input element', () => {
    render(<Input placeholder="Enter text" />);
    expect(screen.getByPlaceholderText('Enter text')).toBeInTheDocument();
  });

  it('renders the label when provided', () => {
    render(<Input label="Email" name="email" />);
    expect(screen.getByText('Email')).toBeInTheDocument();
  });

  it('associates label with input via htmlFor', () => {
    render(<Input label="Username" name="username" />);
    const label = screen.getByText('Username');
    const input = screen.getByRole('textbox');
    expect(label).toHaveAttribute('for', 'username');
    expect(input).toHaveAttribute('id', 'username');
  });

  it('does not render a label when label is not provided', () => {
    const { container } = render(<Input name="noLabel" />);
    expect(container.querySelector('label')).toBeNull();
  });

  it('displays error message when error prop is set', () => {
    render(<Input error="This field is required" />);
    expect(screen.getByText('This field is required')).toBeInTheDocument();
  });

  it('applies error styling when error is present', () => {
    render(<Input error="Invalid" data-testid="err-input" />);
    const input = screen.getByRole('textbox');
    expect(input.className).toContain('border-red-500');
  });

  it('displays helper text when no error', () => {
    render(<Input helperText="Enter your email address" />);
    expect(screen.getByText('Enter your email address')).toBeInTheDocument();
  });

  it('hides helper text when error is present', () => {
    render(<Input helperText="Hint text" error="Error text" />);
    expect(screen.getByText('Error text')).toBeInTheDocument();
    expect(screen.queryByText('Hint text')).not.toBeInTheDocument();
  });

  it('renders left icon when provided', () => {
    render(<Input leftIcon={<span data-testid="left-icon">L</span>} />);
    expect(screen.getByTestId('left-icon')).toBeInTheDocument();
  });

  it('renders right icon when provided', () => {
    render(<Input rightIcon={<span data-testid="right-icon">R</span>} />);
    expect(screen.getByTestId('right-icon')).toBeInTheDocument();
  });

  it('adds left padding class when left icon is present', () => {
    render(<Input leftIcon={<span>L</span>} />);
    const input = screen.getByRole('textbox');
    expect(input.className).toContain('pl-10');
  });

  it('adds right padding class when right icon is present', () => {
    render(<Input rightIcon={<span>R</span>} />);
    const input = screen.getByRole('textbox');
    expect(input.className).toContain('pr-10');
  });

  it('passes through HTML input attributes', () => {
    render(
      <Input
        type="email"
        placeholder="you@school.com"
        disabled
        required
      />
    );
    const input = screen.getByPlaceholderText('you@school.com');
    expect(input).toHaveAttribute('type', 'email');
    expect(input).toBeDisabled();
    expect(input).toBeRequired();
  });

  it('fires onChange event', () => {
    const handleChange = vi.fn();
    render(<Input onChange={handleChange} />);
    const input = screen.getByRole('textbox');
    fireEvent.change(input, { target: { value: 'hello' } });
    expect(handleChange).toHaveBeenCalledTimes(1);
  });

  it('uses id prop over name when both are provided', () => {
    render(<Input id="custom-id" name="field-name" label="Field" />);
    const input = screen.getByRole('textbox');
    expect(input).toHaveAttribute('id', 'custom-id');
    const label = screen.getByText('Field');
    expect(label).toHaveAttribute('for', 'custom-id');
  });
});
