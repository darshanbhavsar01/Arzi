import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { App } from '@/app/App';

describe('App placeholder', () => {
  it('names the product in a level-one heading', () => {
    render(<App />);

    expect(screen.getByRole('heading', { level: 1, name: 'Arzi' })).toBeInTheDocument();
  });

  it('always shows the human-review disclaimer', () => {
    render(<App />);

    expect(screen.getByRole('contentinfo')).toHaveTextContent(
      'A qualified person reviews and signs every appeal.',
    );
  });

  it('treats the logo as decorative next to the visible product name', () => {
    render(<App />);

    expect(screen.getByRole('presentation')).toHaveAttribute('alt', '');
  });
});
