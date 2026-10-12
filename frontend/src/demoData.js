const initialDemoData = {
  plants: [
    { id: 901, crop_type: 'Tomato', variety: 'Roma', field_area: 'North plot', latitude: 18.5204, longitude: 73.8567, health_status: 'Review recommended', last_scanned_at: '2026-10-12T07:34:00Z', last_watered_at: '2026-10-12T06:40:00Z', created_at: '2026-09-18T08:00:00Z', updated_at: '2026-10-12T07:34:00Z' },
    { id: 902, crop_type: 'Potato', variety: 'Kufri Jyoti', field_area: 'East bed', latitude: 18.5209, longitude: 73.8572, health_status: 'Healthy (example)', last_scanned_at: '2026-10-12T07:20:00Z', last_watered_at: null, created_at: '2026-09-24T08:00:00Z', updated_at: '2026-10-12T07:20:00Z' },
    { id: 903, crop_type: 'Pepper', variety: 'California Wonder', field_area: 'Greenhouse A', latitude: 18.5199, longitude: 73.8561, health_status: 'No recent scan', last_scanned_at: null, last_watered_at: '2026-10-12T06:40:00Z', created_at: '2026-10-01T08:00:00Z', updated_at: '2026-10-12T06:40:00Z' },
  ],
  detections: [
    { id: 1901, plant_id: 901, class_name: 'Tomato_Early_Blight', confidence: 0.84, confidence_status: 'REVIEW_RECOMMENDED', image_reference: null, latitude: 18.5204, longitude: 73.8567, detected_at: '2026-10-12T07:34:00Z', model_version: 'DEMO EXAMPLE', created_at: '2026-10-12T07:34:00Z' },
    { id: 1902, plant_id: 902, class_name: 'Potato_Healthy', confidence: 0.93, confidence_status: 'HIGH_CONFIDENCE', image_reference: null, latitude: 18.5209, longitude: 73.8572, detected_at: '2026-10-12T07:20:00Z', model_version: 'DEMO EXAMPLE', created_at: '2026-10-12T07:20:00Z' },
    { id: 1903, plant_id: 903, class_name: 'Pepper_Bacterial_Spot', confidence: 0.61, confidence_status: 'UNCERTAIN', image_reference: null, latitude: 18.5199, longitude: 73.8561, detected_at: '2026-10-12T07:05:00Z', model_version: 'DEMO EXAMPLE', created_at: '2026-10-12T07:05:00Z' },
  ],
  telemetry: [
    { id: 2901, robot_id: 'FLORA-ROVER-01', latitude: 18.5204, longitude: 73.8567, battery_level: 31, water_tank_level: null, movement_status: 'Returning to base', robot_state: 'MOVING', recorded_at: '2026-10-12T07:50:00Z' },
    { id: 2902, robot_id: 'FLORA-ROVER-01', latitude: 18.5209, longitude: 73.8572, battery_level: 35, water_tank_level: null, movement_status: 'Inspecting east bed', robot_state: 'SCANNING', recorded_at: '2026-10-12T07:20:00Z' },
    { id: 2903, robot_id: 'FLORA-ROVER-01', latitude: 18.5201, longitude: 73.8564, battery_level: 44, water_tank_level: null, movement_status: 'Moving between rows', robot_state: 'MOVING', recorded_at: '2026-10-12T07:05:00Z' },
    { id: 2904, robot_id: 'FLORA-ROVER-01', latitude: 18.5199, longitude: 73.8561, battery_level: 51, water_tank_level: null, movement_status: 'Idle at base', robot_state: 'IDLE', recorded_at: '2026-10-12T06:50:00Z' },
  ],
  watering: [
    { id: 3901, robot_id: 'FLORA-ROVER-01', plant_id: 901, started_at: '2026-10-12T06:40:00Z', ended_at: '2026-10-12T06:41:30Z', duration_seconds: 90, water_amount_liters: 0.6, trigger_source: 'DEMO EVENT · scheduled example', soil_moisture_before: null, soil_moisture_after: null, created_at: '2026-10-12T06:41:30Z' },
    { id: 3902, robot_id: 'FLORA-ROVER-01', plant_id: 903, started_at: '2026-10-12T06:28:00Z', ended_at: '2026-10-12T06:29:00Z', duration_seconds: 60, water_amount_liters: 0.4, trigger_source: 'DEMO EVENT · scheduled example', soil_moisture_before: null, soil_moisture_after: null, created_at: '2026-10-12T06:29:00Z' },
  ],
  alerts: [
    { id: 4901, alert_type: 'LOW_BATTERY', message: 'Example: rover battery is low (31%).', plant_id: null, robot_id: 'FLORA-ROVER-01', details: { battery_level: '31%', source: 'DEMO DATA' }, is_read: false, created_at: '2026-10-12T07:50:00Z' },
    { id: 4902, alert_type: 'LOW_CONFIDENCE_DETECTION', message: 'Example: Pepper result needs a review.', plant_id: 903, robot_id: null, details: { detection_id: 1903, class_name: 'Pepper_Bacterial_Spot', source: 'DEMO DATA' }, is_read: false, created_at: '2026-10-12T07:05:00Z' },
    { id: 4903, alert_type: 'DISEASE_DETECTED', message: 'Example: Tomato result flagged for review.', plant_id: 901, robot_id: null, details: { detection_id: 1901, class_name: 'Tomato_Early_Blight', source: 'DEMO DATA' }, is_read: true, created_at: '2026-10-12T07:34:00Z' },
  ],
};

let demoData = structuredClone(initialDemoData);

export async function readDemoList(key) {
  return structuredClone(demoData[key] || []);
}

export async function createDemoPlant(values) {
  const now = new Date().toISOString();
  const row = { id: Math.max(0, ...demoData.plants.map((plant) => plant.id)) + 1, ...values, created_at: now, updated_at: now, last_scanned_at: null, last_watered_at: null };
  demoData.plants = [...demoData.plants, row];
  return structuredClone(row);
}

export async function updateDemoPlant(id, values) {
  const now = new Date().toISOString();
  demoData.plants = demoData.plants.map((plant) => plant.id === id ? { ...plant, ...values, updated_at: now } : plant);
  return structuredClone(demoData.plants.find((plant) => plant.id === id));
}

export async function deleteDemoPlant(id) {
  demoData.plants = demoData.plants.filter((plant) => plant.id !== id);
  demoData.detections = demoData.detections.filter((row) => row.plant_id !== id);
  demoData.watering = demoData.watering.filter((row) => row.plant_id !== id);
  demoData.alerts = demoData.alerts.filter((row) => row.plant_id !== id);
}

export async function markDemoAlertRead(id) {
  demoData.alerts = demoData.alerts.map((alert) => alert.id === id ? { ...alert, is_read: true } : alert);
}

export function resetDemoData() {
  demoData = structuredClone(initialDemoData);
}
