// src/components/common/FormField.test.tsx

import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { FormField } from './FormField';

// Test wrapper that sets up react-hook-form context
interface TestFormValues {
  email: string;
  name: string;
}

const TestFormWrapper: React.FC<{
  defaultValues?: Partial<TestFormValues>;
  children: (control: any) => React.ReactNode;
  onSubmit?: (data: TestFormValues) => void;
}> = ({ defaultValues, children, onSubmit }) => {
  const { control, handleSubmit } = useForm<TestFormValues>({
    defaultValues: { email: '', name: '', ...defaultValues },
  });

  return (
    <form onSubmit={handleSubmit(onSubmit || (() => {}))}>
      {children(control)}
      <button type="submit">Submit</button>
    </form>
  );
};

describe('FormField', () => {
  it('renders an input element', () => {
    render(
      <TestFormWrapper>
        {(control) => (
          <FormField control={control} name="email" placeholder="Enter email" />
        )}
      </TestFormWrapper>
    );
    expect(screen.getByPlaceholderText('Enter email')).toBeInTheDocument();
  });

  it('renders label when provided', () => {
    render(
      <TestFormWrapper>
        {(control) => (
          <FormField control={control} name="email" label="Email Address" />
        )}
      </TestFormWrapper>
    );
    expect(screen.getByText('Email Address')).toBeInTheDocument();
  });

  it('renders with default value from form', () => {
    render(
      <TestFormWrapper defaultValues={{ email: 'test@example.com' }}>
        {(control) => (
          <FormField control={control} name="email" label="Email" />
        )}
      </TestFormWrapper>
    );
    const input = screen.getByRole('textbox');
    expect(input).toHaveValue('test@example.com');
  });

  it('renders helper text when provided', () => {
    render(
      <TestFormWrapper>
        {(control) => (
          <FormField
            control={control}
            name="email"
            helperText="We will never share your email"
          />
        )}
      </TestFormWrapper>
    );
    expect(
      screen.getByText('We will never share your email')
    ).toBeInTheDocument();
  });

  it('renders left icon when provided', () => {
    render(
      <TestFormWrapper>
        {(control) => (
          <FormField
            control={control}
            name="email"
            leftIcon={<span data-testid="email-icon">@</span>}
          />
        )}
      </TestFormWrapper>
    );
    expect(screen.getByTestId('email-icon')).toBeInTheDocument();
  });

  it('renders right icon when provided', () => {
    render(
      <TestFormWrapper>
        {(control) => (
          <FormField
            control={control}
            name="email"
            rightIcon={<span data-testid="check-icon">V</span>}
          />
        )}
      </TestFormWrapper>
    );
    expect(screen.getByTestId('check-icon')).toBeInTheDocument();
  });

  it('updates form value on user input', async () => {
    const onSubmit = jest.fn();
    render(
      <TestFormWrapper onSubmit={onSubmit}>
        {(control) => (
          <FormField control={control} name="email" label="Email" />
        )}
      </TestFormWrapper>
    );

    const input = screen.getByRole('textbox');
    fireEvent.change(input, { target: { value: 'new@example.com' } });

    fireEvent.click(screen.getByText('Submit'));

    await waitFor(() => {
      expect(onSubmit).toHaveBeenCalledWith(
        expect.objectContaining({ email: 'new@example.com' }),
        expect.anything()
      );
    });
  });

  it('uses name as id when no id is provided', () => {
    render(
      <TestFormWrapper>
        {(control) => (
          <FormField control={control} name="email" label="Email" />
        )}
      </TestFormWrapper>
    );
    const input = screen.getByRole('textbox');
    expect(input).toHaveAttribute('id', 'email');
  });

  it('uses provided id over name', () => {
    render(
      <TestFormWrapper>
        {(control) => (
          <FormField
            control={control}
            name="email"
            id="custom-email-id"
            label="Email"
          />
        )}
      </TestFormWrapper>
    );
    const input = screen.getByRole('textbox');
    expect(input).toHaveAttribute('id', 'custom-email-id');
  });

  it('passes through HTML input attributes', () => {
    render(
      <TestFormWrapper>
        {(control) => (
          <FormField
            control={control}
            name="email"
            type="email"
            placeholder="you@school.com"
            disabled
          />
        )}
      </TestFormWrapper>
    );
    const input = screen.getByPlaceholderText('you@school.com');
    expect(input).toHaveAttribute('type', 'email');
    expect(input).toBeDisabled();
  });

  it('displays validation error when required field is empty', async () => {
    const schema = z.object({
      email: z.string().min(1, 'Email is required'),
      name: z.string(),
    });

    const ValidatedFormWrapper: React.FC = () => {
      const { control, handleSubmit } = useForm<TestFormValues>({
        defaultValues: { email: '', name: '' },
        resolver: zodResolver(schema),
      });

      return (
        <form onSubmit={handleSubmit(() => {})}>
          <FormField control={control} name="email" label="Email" />
          <button type="submit">Submit</button>
        </form>
      );
    };

    render(<ValidatedFormWrapper />);

    fireEvent.click(screen.getByText('Submit'));

    await waitFor(() => {
      expect(screen.getByText('Email is required')).toBeInTheDocument();
    });
  });
});
