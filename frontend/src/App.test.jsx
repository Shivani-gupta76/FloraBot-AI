import React from 'react';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import App from './App.jsx';

afterEach(() => {
  cleanup();
  sessionStorage.clear();
  vi.unstubAllGlobals();
});

describe('dashboard help link', () => {
  it('opens the configured Swagger UI in a keyboard-accessible new-tab link', async () => {
    sessionStorage.setItem('flora_token', 'test-token');
    vi.stubGlobal('fetch', vi.fn(async (url) => {
      const path = new URL(url).pathname;
      const payload = path === '/api/auth/me'
        ? { id: 1, full_name: 'Test Operator', role: 'Operator' }
        : path === '/health' ? { status: 'ok' } : [];
      return { ok: true, status: 200, json: async () => payload };
    }));

    render(<MemoryRouter><App /></MemoryRouter>);
    const link = await screen.findByRole('link', { name: 'Open Flora-Bot API documentation in a new tab' });
    await waitFor(() => expect(link.getAttribute('href')).toBe('http://localhost:8000/docs'));
    expect(link.tagName).toBe('A');
    expect(link.getAttribute('target')).toBe('_blank');
    expect(link.getAttribute('rel')).toBe('noopener noreferrer');
    expect(link.tabIndex).toBe(0);
  });
});
