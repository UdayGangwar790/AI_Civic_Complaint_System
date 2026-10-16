import { API_BASE_URL_VALUE } from './detectionApi';
import { LocationApiError } from './locationApi';
import { apiFetch } from './apiFetch';

export async function resolveAuthority({ coordinates, address, live = true }) {
  const params = new URLSearchParams({
    latitude: coordinates.latitude,
    longitude: coordinates.longitude,
  });
  if (live) params.set('live', 'true');
  for (const field of ['road', 'area', 'city', 'district', 'state', 'country']) {
    if (address?.[field]) params.set(field, address[field]);
  }

  let response;
  try {
    response = await apiFetch(`${API_BASE_URL_VALUE}/api/v1/authority/resolve?${params}`);
  } catch {
    throw new LocationApiError('Authority information could not be reached.', 0);
  }

  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new LocationApiError(
      payload?.detail || 'Authority information is temporarily unavailable.',
      response.status,
    );
  }
  return payload;
}

export async function fetchOfficialAuthoritySources() {
  const res = await apiFetch(`${API_BASE_URL_VALUE}/api/v1/authority/sources`);
  if (!res.ok) throw new LocationApiError('Failed to load official sources.', res.status);
  return res.json();
}

export async function fetchAuthorityMapCases(params = {}) {
  const token = null;
  const query = new URLSearchParams();
  if (params.issue) query.set('issue', params.issue);
  if (params.priority) query.set('priority', params.priority);
  if (params.status) query.set('status', params.status);
  if (params.city) query.set('city', params.city);
  if (params.created_from) query.set('created_from', params.created_from);
  if (params.created_to) query.set('created_to', params.created_to);
  if (params.limit) query.set('limit', params.limit);

  const qs = query.toString();
  const res = await apiFetch(`${API_BASE_URL_VALUE}/api/v1/authority/map/cases${qs ? `?${qs}` : ''}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  });
  const data = await res.json().catch(() => null);
  if (!res.ok) throw new LocationApiError(data?.detail || 'Failed to load authority cases.', res.status);
  return data;
}

export async function updateAuthorityCaseStatus(referenceId, status, reason, resolutionEvidence) {
  const token = null;
  const res = await apiFetch(`${API_BASE_URL_VALUE}/api/v1/complaint/cases/${encodeURIComponent(referenceId)}/status`, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({
      status,
      reason: reason || undefined,
      resolution_evidence: resolutionEvidence || undefined,
    }),
  });
  const data = await res.json().catch(() => null);
  if (!res.ok) throw new LocationApiError(data?.detail || 'Failed to update case status.', res.status);
  return data;
}

export async function fetchAuthorityCaseIntelligence(referenceId) {
  let response;
  try {
    response = await apiFetch(`${API_BASE_URL_VALUE}/api/v1/authority/cases/${encodeURIComponent(referenceId)}/intelligence`);
  } catch {
    throw new LocationApiError('Case intelligence could not be reached.', 0);
  }
  const payload = await response.json().catch(() => null);
  if (!response.ok) throw new LocationApiError(payload?.detail || 'Case intelligence is unavailable.', response.status);
  return payload;
}
