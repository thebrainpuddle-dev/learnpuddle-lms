// src/components/common/Toast.test.tsx

import React from 'react';
import { render, screen, fireEvent, act, waitFor } from '@testing-library/react';
import { afterEach, beforeEach } from 'vitest';
import { ToastProvider, useToast } from './Toast';

// Test consumer that exposes toast methods
const ToastTrigger: React.FC = () => {
  const toast = useToast();
  return (
    <div>
      <button onClick={() => toast.success('Success!', 'It worked')}>
        Show Success
      </button>
      <button onClick={() => toast.error('Error!', 'Something failed')}>
        Show Error
      </button>
      <button onClick={() => toast.warning('Warning!', 'Be careful')}>
        Show Warning
      </button>
      <button onClick={() => toast.info('Info', 'FYI')}>
        Show Info
      </button>
    </div>
  );
};

// Ensure fake timers are always restored, even if a test throws before
// calling vi.useRealTimers() itself.
afterEach(() => {
  vi.useRealTimers();
});

describe('ToastProvider', () => {
  it('renders children', () => {
    render(
      <ToastProvider>
        <div>App Content</div>
      </ToastProvider>
    );
    expect(screen.getByText('App Content')).toBeInTheDocument();
  });

  it('shows success toast when triggered', () => {
    render(
      <ToastProvider>
        <ToastTrigger />
      </ToastProvider>
    );

    fireEvent.click(screen.getByText('Show Success'));
    expect(screen.getByText('Success!')).toBeInTheDocument();
    expect(screen.getByText('It worked')).toBeInTheDocument();
  });

  it('shows error toast when triggered', () => {
    render(
      <ToastProvider>
        <ToastTrigger />
      </ToastProvider>
    );

    fireEvent.click(screen.getByText('Show Error'));
    expect(screen.getByText('Error!')).toBeInTheDocument();
    expect(screen.getByText('Something failed')).toBeInTheDocument();
  });

  it('shows warning toast when triggered', () => {
    render(
      <ToastProvider>
        <ToastTrigger />
      </ToastProvider>
    );

    fireEvent.click(screen.getByText('Show Warning'));
    expect(screen.getByText('Warning!')).toBeInTheDocument();
  });

  it('shows info toast when triggered', () => {
    render(
      <ToastProvider>
        <ToastTrigger />
      </ToastProvider>
    );

    fireEvent.click(screen.getByText('Show Info'));
    expect(screen.getByText('Info')).toBeInTheDocument();
    expect(screen.getByText('FYI')).toBeInTheDocument();
  });

  it('renders toast with role="alert" for accessibility', () => {
    render(
      <ToastProvider>
        <ToastTrigger />
      </ToastProvider>
    );

    fireEvent.click(screen.getByText('Show Success'));
    expect(screen.getByRole('alert')).toBeInTheDocument();
  });

  it('can show multiple toasts at the same time', () => {
    render(
      <ToastProvider>
        <ToastTrigger />
      </ToastProvider>
    );

    fireEvent.click(screen.getByText('Show Success'));
    fireEvent.click(screen.getByText('Show Error'));

    expect(screen.getByText('Success!')).toBeInTheDocument();
    expect(screen.getByText('Error!')).toBeInTheDocument();
  });

  it('removes toast when close button is clicked', async () => {
    render(
      <ToastProvider>
        <ToastTrigger />
      </ToastProvider>
    );

    fireEvent.click(screen.getByText('Show Success'));
    expect(screen.getByText('Success!')).toBeInTheDocument();

    // Find and click the close button (XMarkIcon button)
    const alert = screen.getByRole('alert');
    const closeButton = alert.querySelector('button');
    expect(closeButton).toBeInTheDocument();

    fireEvent.click(closeButton!);

    await waitFor(() => {
      expect(screen.queryByText('Success!')).not.toBeInTheDocument();
    });
  });

  it('auto-dismisses toast after timeout', async () => {
    // Scope faking to setTimeout/clearTimeout only.
    // Faking MessageChannel (React 18 scheduler) or Date without scoping causes
    // cross-file timer pollution that makes other test files flaky in the same
    // worker thread.
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });

    render(
      <ToastProvider>
        <ToastTrigger />
      </ToastProvider>
    );

    fireEvent.click(screen.getByText('Show Success'));
    expect(screen.getByText('Success!')).toBeInTheDocument();

    // Fast-forward past the 5-second auto-dismiss timer
    act(() => {
      vi.advanceTimersByTime(5500);
    });

    expect(screen.queryByText('Success!')).not.toBeInTheDocument();

    vi.useRealTimers();
  });
});

describe('useToast outside provider', () => {
  it('throws when used outside ToastProvider', () => {
    const BrokenComponent = () => {
      useToast();
      return null;
    };

    // Suppress console.error for expected error
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {});

    expect(() => render(<BrokenComponent />)).toThrow(
      'useToast must be used within a ToastProvider'
    );

    spy.mockRestore();
  });
});
