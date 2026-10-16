import { API_BASE_URL_VALUE } from './detectionApi';
import { apiFetch } from './apiFetch';

export class GeospatialApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = 'GeospatialApiError';
    this.status = status;
  }
}

export async function getGeospatialContext({
  latitude,
  longitude,
  accuracy_m,
  issue_category,
  radius_meters = 250,
  time_window_days = 30,
}) {
  const payload = {
    latitude,
    longitude,
    accuracy_m: accuracy_m || null,
    issue_category: issue_category || null,
    radius_meters,
    time_window_days,
  };

  const response = await apiFetch(`${API_BASE_URL_VALUE}/api/v1/geospatial/context`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new GeospatialApiError(
      data?.detail || 'Failed to fetch geospatial intelligence context.',
      response.status
    );
  }
  return data;
}

export async function getNearbyCases({
  latitude,
  longitude,
  radius_meters = 250,
  time_window_days = 30,
  issue,
  unresolved_only = false,
}) {
  const params = new URLSearchParams({
    latitude,
    longitude,
    radius_meters,
    time_window_days,
    unresolved_only,
  });
  if (issue) params.set('issue', issue);

  const response = await apiFetch(`${API_BASE_URL_VALUE}/api/v1/geospatial/cases/nearby?${params}`);
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new GeospatialApiError(
      data?.detail || 'Failed to search nearby civic cases.',
      response.status
    );
  }
  return data;
}

export async function getCaseGeospatialContext(referenceId, options = {}) {
  const params = new URLSearchParams({
    radius_meters: options.radius_meters || 250,
    time_window_days: options.time_window_days || 30,
  });

  const response = await apiFetch(
    `${API_BASE_URL_VALUE}/api/v1/geospatial/cases/${encodeURIComponent(referenceId)}/context?${params}`
  );
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new GeospatialApiError(
      data?.detail || 'Failed to fetch case geospatial context.',
      response.status
    );
  }
  return data;
}

export async function resolveRoad({ latitude, longitude, accuracy_m }) {
  const params = new URLSearchParams({ latitude, longitude });
  if (accuracy_m !== undefined && accuracy_m !== null) {
    params.set('accuracy_m', accuracy_m);
  }

  const response = await apiFetch(`${API_BASE_URL_VALUE}/api/v1/geospatial/road/resolve?${params}`);
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new GeospatialApiError(
      data?.detail || 'Failed to resolve road information.',
      response.status
    );
  }
  return data;
}

export async function getExternalCivicContext({
  latitude,
  longitude,
  issue_category,
  window_hours = 24,
}) {
  const params = new URLSearchParams({
    latitude,
    longitude,
    window_hours,
  });
  if (issue_category) params.set('issue_category', issue_category);

  const response = await apiFetch(
    `${API_BASE_URL_VALUE}/api/v1/geospatial/external-context?${params}`
  );
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new GeospatialApiError(
      data?.detail || 'Failed to fetch external civic context.',
      response.status
    );
  }
  return data;
}

