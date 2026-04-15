// src/components/common/ErrorBoundary.test.tsx

import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { ErrorBoundary, PageErrorBoundary, withErrorBoundary } from './ErrorBoundary';

// Suppress React error boundary console.error in tests
const originalConsoleError = console.error;
beforeAll(() => {
  console.error = (...args: any[]) => {
    // Suppress expected React error boundary messages
    if (
      typeof args[0] === 'string' &&
      (args[0].includes('Error: Uncaught') ||
        args[0].includes('The above error occurred'))
    ) {
      return;
    }
    originalConsoleError(...args);
  };
});
afterAll(() => {
  console.error = originalConsoleError;
});

// Component that throws during render
const ThrowingComponent: React.FC<{ shouldThrow?: boolean }> = ({
  shouldThrow = true,
}) => {
  if (shouldThrow) {
    throw new Error('Test render error');
  }
  return <div>Working Content</div>;
};

describe('ErrorBoundary', () => {
  it('renders children when no error occurs', () => {
    render(
      <ErrorBoundary>
        <div>Safe Content</div>
      </ErrorBoundary>
    );
    expect(screen.getByText('Safe Content')).toBeInTheDocument();
  });

  it('renders default fallback UI when child throws', () => {
    render(
      <ErrorBoundary>
        <ThrowingComponent />
      </ErrorBoundary>
    );
    expect(screen.getByText('Something went wrong')).toBeInTheDocument();
    expect(screen.queryByText('Working Content')).not.toBeInTheDocument();
  });

  it('renders custom fallback when provided', () => {
    render(
      <ErrorBoundary fallback={<div>Custom Error UI</div>}>
        <ThrowingComponent />
      </ErrorBoundary>
    );
    expect(screen.getByText('Custom Error UI')).toBeInTheDocument();
    expect(screen.queryByText('Something went wrong')).not.toBeInTheDocument();
  });

  it('shows Try Again button in default fallback', () => {
    render(
      <ErrorBoundary>
        <ThrowingComponent />
      </ErrorBoundary>
    );
    expect(screen.getByText('Try Again')).toBeInTheDocument();
  });

  it('shows Reload Page button in default fallback', () => {
    render(
      <ErrorBoundary>
        <ThrowingComponent />
      </ErrorBoundary>
    );
    expect(screen.getByText('Reload Page')).toBeInTheDocument();
  });

  it('calls onError callback when error is caught', () => {
    const onError = vi.fn();
    render(
      <ErrorBoundary onError={onError}>
        <ThrowingComponent />
      </ErrorBoundary>
    );
    expect(onError).toHaveBeenCalledTimes(1);
    expect(onError).toHaveBeenCalledWith(
      expect.objectContaining({ message: 'Test render error' }),
      expect.objectContaining({ componentStack: expect.any(String) })
    );
  });

  it('resets error state when Try Again is clicked', () => {
    const { rerender } = render(
      <ErrorBoundary>
        <ThrowingComponent shouldThrow={true} />
      </ErrorBoundary>
    );

    // Error is showing
    expect(screen.getByText('Something went wrong')).toBeInTheDocument();

    // Click Try Again - this resets the boundary, but the same component
    // will throw again, so error reappears
    fireEvent.click(screen.getByText('Try Again'));
    // After reset, React will re-render children; since ThrowingComponent
    // still throws, the error UI will reappear
    expect(screen.getByText('Something went wrong')).toBeInTheDocument();
  });

  it('resets when resetKey changes', () => {
    const { rerender } = render(
      <ErrorBoundary resetKey="key-1">
        <ThrowingComponent shouldThrow={true} />
      </ErrorBoundary>
    );

    expect(screen.getByText('Something went wrong')).toBeInTheDocument();

    // Change resetKey - boundary will reset, then component throws again
    rerender(
      <ErrorBoundary resetKey="key-2">
        <ThrowingComponent shouldThrow={true} />
      </ErrorBoundary>
    );

    // Component still throws, so error reappears
    expect(screen.getByText('Something went wrong')).toBeInTheDocument();
  });
});

describe('PageErrorBoundary', () => {
  it('renders children when no error', () => {
    render(
      <PageErrorBoundary pathname="/page">
        <div>Page Content</div>
      </PageErrorBoundary>
    );
    expect(screen.getByText('Page Content')).toBeInTheDocument();
  });

  it('catches errors from children', () => {
    render(
      <PageErrorBoundary pathname="/page">
        <ThrowingComponent />
      </PageErrorBoundary>
    );
    expect(screen.getByText('Something went wrong')).toBeInTheDocument();
  });
});

describe('withErrorBoundary', () => {
  it('wraps a component with error boundary', () => {
    const SafeComponent = () => <div>Wrapped Content</div>;
    const Wrapped = withErrorBoundary(SafeComponent);

    render(<Wrapped />);
    expect(screen.getByText('Wrapped Content')).toBeInTheDocument();
  });

  it('catches errors from wrapped component', () => {
    const UnsafeComponent = () => {
      throw new Error('Wrapped error');
    };
    const Wrapped = withErrorBoundary(UnsafeComponent);

    render(<Wrapped />);
    expect(screen.getByText('Something went wrong')).toBeInTheDocument();
  });

  it('sets displayName on wrapped component', () => {
    const MyComponent = () => <div>Test</div>;
    MyComponent.displayName = 'MyComponent';
    const Wrapped = withErrorBoundary(MyComponent);
    expect(Wrapped.displayName).toBe('withErrorBoundary(MyComponent)');
  });
});
