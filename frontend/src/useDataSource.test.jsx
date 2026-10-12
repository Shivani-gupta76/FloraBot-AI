import React from 'react';
import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { useDataSource } from './useDataSource.js';
import { resetDemoData } from './demoData.js';

afterEach(() => { resetDemoData(); vi.restoreAllMocks(); });

describe('useDataSource', () => {
  it('reads only the isolated provider in demo mode', async () => {
    const realLoader = vi.fn();
    const { result } = renderHook(() => useDataSource('token', true, 'plants', realLoader));
    await waitFor(() => expect(result.current.data?.length).toBe(3));
    expect(realLoader).not.toHaveBeenCalled();
    expect(result.current.data[0].id).toBe(901);
  });

  it('switches back to the real API loader when demo mode is disabled', async () => {
    const realLoader = vi.fn().mockResolvedValue([{ id: 77 }]);
    const { result, rerender } = renderHook(({ demoMode }) => useDataSource('token', demoMode, 'plants', realLoader), { initialProps: { demoMode: true } });
    await waitFor(() => expect(result.current.data?.length).toBe(3));
    rerender({ demoMode: false });
    await waitFor(() => expect(result.current.data).toEqual([{ id: 77 }]));
    expect(realLoader).toHaveBeenCalledTimes(1);
  });
});
