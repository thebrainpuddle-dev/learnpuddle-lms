// src/components/reportBuilder/RecipientChipsInput.test.tsx

import React, { useState } from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { RecipientChipsInput } from './RecipientChipsInput';

function Harness({
  initial = [],
  error = null,
}: {
  initial?: string[];
  error?: string | null;
}) {
  const [value, setValue] = useState<string[]>(initial);
  return <RecipientChipsInput value={value} onChange={setValue} error={error} />;
}

describe('RecipientChipsInput', () => {
  it('commits a valid email on Enter and clears the draft', async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const input = screen.getByTestId('recipient-draft-input');
    await user.type(input, 'alice@example.com{Enter}');
    expect(screen.getByTestId('recipient-chip-0')).toHaveTextContent(
      'alice@example.com',
    );
    expect((input as HTMLInputElement).value).toBe('');
  });

  it('rejects invalid email shapes with a local error', async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.type(
      screen.getByTestId('recipient-draft-input'),
      'not-an-email{Enter}',
    );
    expect(screen.getByTestId('recipient-error')).toHaveTextContent(
      /not a valid email/i,
    );
    expect(screen.queryByTestId('recipient-chip-0')).toBeNull();
  });

  it('surfaces server-side errors passed via the `error` prop', () => {
    render(
      <Harness
        initial={['external@other.com']}
        error="recipients_json: EXTERNAL_RECIPIENT_NOT_ALLOWED"
      />,
    );
    expect(screen.getByTestId('recipient-error')).toHaveTextContent(
      /EXTERNAL_RECIPIENT_NOT_ALLOWED/,
    );
  });

  it('removes a chip when the X button is clicked', async () => {
    const user = userEvent.setup();
    render(<Harness initial={['a@b.com', 'c@d.com']} />);
    expect(screen.getByTestId('recipient-chip-0')).toBeInTheDocument();
    await user.click(screen.getByTestId('recipient-remove-0'));
    expect(screen.getByTestId('recipient-chip-0')).toHaveTextContent('c@d.com');
    expect(screen.queryByTestId('recipient-chip-1')).toBeNull();
  });
});
