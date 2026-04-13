// src/components/common/ConfirmDialog.test.tsx

import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { ConfirmDialog } from './ConfirmDialog';

describe('ConfirmDialog', () => {
  const defaultProps = {
    isOpen: true,
    onClose: jest.fn(),
    onConfirm: jest.fn(),
    title: 'Delete Course',
    message: 'Are you sure you want to delete this course?',
  };

  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('renders title and message when open', () => {
    render(<ConfirmDialog {...defaultProps} />);
    expect(screen.getByText('Delete Course')).toBeInTheDocument();
    expect(
      screen.getByText('Are you sure you want to delete this course?')
    ).toBeInTheDocument();
  });

  it('does not render when isOpen is false', () => {
    render(<ConfirmDialog {...defaultProps} isOpen={false} />);
    expect(screen.queryByText('Delete Course')).not.toBeInTheDocument();
  });

  it('shows default confirm label "Confirm"', () => {
    render(<ConfirmDialog {...defaultProps} />);
    expect(screen.getByText('Confirm')).toBeInTheDocument();
  });

  it('shows default cancel label "Cancel"', () => {
    render(<ConfirmDialog {...defaultProps} />);
    expect(screen.getByText('Cancel')).toBeInTheDocument();
  });

  it('uses custom confirm label', () => {
    render(<ConfirmDialog {...defaultProps} confirmLabel="Yes, Delete" />);
    expect(screen.getByText('Yes, Delete')).toBeInTheDocument();
  });

  it('uses custom cancel label', () => {
    render(<ConfirmDialog {...defaultProps} cancelLabel="No, Keep It" />);
    expect(screen.getByText('No, Keep It')).toBeInTheDocument();
  });

  it('calls onClose when cancel button is clicked', () => {
    render(<ConfirmDialog {...defaultProps} />);
    fireEvent.click(screen.getByText('Cancel'));
    expect(defaultProps.onClose).toHaveBeenCalledTimes(1);
  });

  it('calls onConfirm and onClose when confirm button is clicked', () => {
    render(<ConfirmDialog {...defaultProps} />);
    fireEvent.click(screen.getByText('Confirm'));
    expect(defaultProps.onConfirm).toHaveBeenCalledTimes(1);
    expect(defaultProps.onClose).toHaveBeenCalledTimes(1);
  });

  it('shows "Processing..." when loading is true', () => {
    render(<ConfirmDialog {...defaultProps} loading />);
    expect(screen.getByText('Processing...')).toBeInTheDocument();
    expect(screen.queryByText('Confirm')).not.toBeInTheDocument();
  });

  it('disables buttons when loading is true', () => {
    render(<ConfirmDialog {...defaultProps} loading />);
    const cancelButton = screen.getByText('Cancel');
    const confirmButton = screen.getByText('Processing...');
    expect(cancelButton).toBeDisabled();
    expect(confirmButton).toBeDisabled();
  });
});
