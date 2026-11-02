import React from 'react';
import { cleanup, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import App from './App.jsx';

afterEach(() => {
  cleanup();
  sessionStorage.clear();
  localStorage.clear();
  vi.unstubAllGlobals();
});

const plants = [{ id: 1, crop_type: 'Tomato', variety: 'Roma', field_area: 'North plot', latitude: null, longitude: null, health_status: 'Review recommended', last_scanned_at: null, last_watered_at: null, created_at: '2026-10-30T12:00:00Z', updated_at: '2026-10-30T12:00:00Z' }];
const detections = [{ id: 2, plant_id: 1, class_name: 'Tomato_Early_Blight', confidence: 0.82, confidence_status: 'REVIEW_RECOMMENDED', detected_at: '2026-10-30T12:00:00Z', model_version: 'flora-model-v1', latitude: null, longitude: null }];
const alerts = [
  { id: 3, alert_type: 'DISEASE_DETECTED', message: 'Disease class reported by inference service', plant_id: 1, details: { detection_id: 2, class_name: 'Tomato_Early_Blight' }, is_read: false, created_at: '2026-10-30T12:01:00Z' },
  { id: 4, alert_type: 'LOW_BATTERY', message: 'Robot reported low battery', plant_id: null, robot_id: 'robot-1', details: {}, is_read: false, created_at: '2026-10-30T12:02:00Z' },
];

function renderDashboard(path = '/', records = { plants, detections, alerts }) {
  sessionStorage.setItem('flora_token', 'test-token');
  vi.stubGlobal('fetch', vi.fn(async (url) => {
    const route = new URL(url).pathname;
    const payload = route === '/api/auth/me'
      ? { id: 1, full_name: 'Test Operator', email: 'operator@example.com', role: 'Operator' }
      : route === '/health' ? { status: 'ok' }
        : route === '/api/plants' ? records.plants
          : route === '/api/detections' ? records.detections
            : route === '/api/alerts' ? records.alerts
              : route === '/api/inference/status' ? { available: false, reason: 'Model file not found.' } : [];
    return { ok: true, status: 200, json: async () => payload };
  }));
  return render(<MemoryRouter initialEntries={[path]}><App /></MemoryRouter>);
}

describe('dashboard help link', () => {
  it('opens the configured Swagger UI in a keyboard-accessible new-tab link', async () => {
    renderDashboard();
    const link = await screen.findByRole('link', { name: 'Open Flora-Bot API documentation in a new tab' });
    await waitFor(() => expect(link.getAttribute('href')).toBe('http://localhost:8000/docs'));
    expect(link.tagName).toBe('A');
    expect(link.getAttribute('target')).toBe('_blank');
    expect(link.getAttribute('rel')).toBe('noopener noreferrer');
    expect(link.tabIndex).toBe(0);
  });
});

describe('Phase 1 dashboard cleanup', () => {
  it('shows only the six requested sidebar links', async () => {
    renderDashboard();
    const nav = await screen.findByRole('navigation', { name: 'Main navigation' });
    expect(within(nav).getAllByRole('link').map((link) => link.textContent.trim())).toEqual([
      'Overview', 'Crop management', 'Disease detection', 'Disease Alerts', 'Reports & history', 'Settings',
    ]);
    expect(within(nav).queryByText(/Rover|Irrigation|GPS/i)).toBeNull();
  });

  it('shows real overview counts and an unavailable camera status', async () => {
    renderDashboard();
    expect(await screen.findByText('Recent Disease Detections')).toBeTruthy();
    expect(screen.getByText('Recent Disease Alerts')).toBeTruthy();
    expect(screen.getByText('Registered crops')).toBeTruthy();
    expect(screen.getByText('Camera connection')).toBeTruthy();
    expect(screen.getByText('Awaiting hardware integration')).toBeTruthy();
    expect(screen.queryByText('Rover status')).toBeNull();
    expect(screen.queryByText('Recent watering')).toBeNull();
  });

  it('shows the ESP32-CAM waiting state without manual image controls', async () => {
    renderDashboard('/detections', { plants, detections: [], alerts: [] });
    expect(await screen.findByText('Waiting for images from ESP32-CAM.')).toBeTruthy();
    expect(screen.queryByLabelText('Leaf image')).toBeNull();
    expect(screen.queryByText('Run actual model')).toBeNull();
    expect(screen.queryByText('Choose File')).toBeNull();
  });

  it('lists disease alerts and excludes hardware alerts', async () => {
    renderDashboard('/alerts');
    expect(await screen.findByText('Disease alert feed')).toBeTruthy();
    expect(screen.getByText('Tomato Early Blight')).toBeTruthy();
    expect(await screen.findByText('82.0%')).toBeTruthy();
    expect(screen.getByText('Tomato')).toBeTruthy();
    expect(screen.queryByText('Robot reported low battery')).toBeNull();
  });

  it('keeps disease detection and alert history without rover or watering events', async () => {
    renderDashboard('/history');
    expect(await screen.findByText('Disease history')).toBeTruthy();
    expect(screen.getAllByText('Disease detection').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Disease alert').length).toBeGreaterThan(0);
    expect(screen.queryByText('Rover updates')).toBeNull();
    expect(screen.queryByText('Watering events')).toBeNull();
    expect(screen.getByRole('button', { name: /Export CSV/i })).toBeTruthy();
  });

  it('keeps crop records and account/API settings accessible', async () => {
    renderDashboard('/crops');
    expect(await screen.findByText('Registered crops')).toBeTruthy();
    expect(screen.getByText('Tomato')).toBeTruthy();
    cleanup();
    renderDashboard('/settings');
    expect(await screen.findByText('Test Operator')).toBeTruthy();
    expect(screen.getByText('API base URL')).toBeTruthy();
    expect(screen.getByText('Authentication')).toBeTruthy();
  });
});
