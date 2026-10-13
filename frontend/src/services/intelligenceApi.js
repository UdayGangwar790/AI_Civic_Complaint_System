import { API_BASE_URL_VALUE } from './detectionApi';
import { apiFetch } from './apiFetch';

export class IntelligenceApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = 'IntelligenceApiError';
    this.status = status;
  }
}

async function postJson(url, payload, _token = null) {
  const authToken = null;
  const headers = { 'Content-Type': 'application/json' };
  if (authToken) {
    headers.Authorization = `Bearer ${authToken}`;
  }

  let response;
  try {
    response = await apiFetch(url, {
      method: 'POST',
      headers,
      body: JSON.stringify(payload),
    });
  } catch {
    throw new IntelligenceApiError('Intelligence service could not be reached.', 0);
  }

  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new IntelligenceApiError(data?.detail || 'Intelligence request failed.', response.status);
  }
  return data;
}

export function analyzeNlpComplaint(payload) {
  return postJson(`${API_BASE_URL_VALUE}/api/v1/nlp/analyze`, payload);
}

export function checkDuplicateComplaint(payload, token = null) {
  return postJson(`${API_BASE_URL_VALUE}/api/v1/complaint/duplicate-check`, payload, token);
}

export function scorePriority(payload) {
  return postJson(`${API_BASE_URL_VALUE}/api/v1/priority/score`, payload);
}
