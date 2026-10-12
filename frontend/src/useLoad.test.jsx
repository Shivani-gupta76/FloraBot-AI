import React, { StrictMode } from 'react';
import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { useLoad } from './useLoad.js';

afterEach(() => vi.useRealTimers());

describe('useLoad', () => {
  it('settles with records and with an empty array as successful data', async () => {
    const loader = vi.fn().mockResolvedValueOnce([{ id: 1 }]).mockResolvedValueOnce([]);
    const { result, rerender } = renderHook(({ version }) => useLoad(() => loader(), [version], 0), { initialProps: { version: 1 } });
    await waitFor(() => expect(result.current.data).toEqual([{ id: 1 }]));
    rerender({ version: 2 });
    await waitFor(() => expect(result.current.data).toEqual([]));
    expect(result.current.error).toBe('');
    expect(result.current.loading).toBe(false);
  });

  it('ends loading and exposes a useful error when a loader rejects', async () => {
    const { result } = renderHook(() => useLoad(() => Promise.reject(new Error('server unavailable')), [], 0));
    await waitFor(() => expect(result.current.error).toBe('server unavailable'));
    expect(result.current.loading).toBe(false);
  });

  it('restarts after StrictMode aborts the first effect request', async () => {
    let calls = 0;
    const loader = vi.fn((signal) => {
      calls += 1;
      if (calls === 1) return new Promise((_, reject) => signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError'))));
      return Promise.resolve(['ready']);
    });
    const wrapper = ({ children }) => <StrictMode>{children}</StrictMode>;
    const { result } = renderHook(() => useLoad(loader, [], 0), { wrapper, reactStrictMode: true });
    await act(async () => { await Promise.resolve(); await Promise.resolve(); });
    expect(calls).toBe(2);
    await waitFor(() => expect(result.current.data).toEqual(['ready']));
    expect(result.current.loading).toBe(false);
  });

  it('shows a slow state while a request is pending and settles when it completes', async () => {
    vi.useFakeTimers();
    let finish;
    const loader = vi.fn(() => new Promise((resolve) => { finish = resolve; }));
    const { result } = renderHook(() => useLoad(loader, [], 0));
    await act(async () => { await vi.advanceTimersByTimeAsync(8_000); });
    expect(result.current.slow).toBe(true);
    await act(async () => { finish(['done']); await Promise.resolve(); });
    expect(result.current.data).toEqual(['done']);
    expect(result.current.loading).toBe(false);
  });

  it('cancels on unmount and deduplicates rerenders while a request is active', async () => {
    let observedSignal;
    const loader = vi.fn((signal) => { observedSignal = signal; return new Promise(() => {}); });
    const { rerender, unmount } = renderHook(() => useLoad(loader, [], 0));
    rerender();
    expect(loader).toHaveBeenCalledTimes(1);
    unmount();
    expect(observedSignal.aborted).toBe(true);
  });

  it('runs independent hook requests in parallel', async () => {
    const first = vi.fn().mockResolvedValue(['one']);
    const second = vi.fn().mockResolvedValue(['two']);
    const { result } = renderHook(() => [useLoad(first, [], 0), useLoad(second, [], 0)]);
    await waitFor(() => expect(result.current.map((item) => item.data)).toEqual([['one'], ['two']]));
    expect(first).toHaveBeenCalledTimes(1);
    expect(second).toHaveBeenCalledTimes(1);
  });
});
