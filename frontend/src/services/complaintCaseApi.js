import { API_BASE_URL_VALUE } from './detectionApi';
import { apiFetch } from './apiFetch';

export class ComplaintCaseApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = 'ComplaintCaseApiError';
    this.status = status;
  }
}

async function requestJson(url, options = {}, _token = null) {
  const authToken = null;
  const headers = { ...(options.headers || {}) };
  if (authToken) {
    headers.Authorization = `Bearer ${authToken}`;
  }

  let response;
  try {
    response = await apiFetch(url, { ...options, headers });
  } catch {
    throw new ComplaintCaseApiError('The CVKI case service could not be reached.', 0);
  }
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new ComplaintCaseApiError(payload?.detail || 'The CVKI case request failed.', response.status);
  }
  return payload;
}

export function createCvkiCase(payload, token = null) {
  return requestJson(
    `${API_BASE_URL_VALUE}/api/v1/complaint/cases`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    },
    token,
  );
}

export function getCvkiCase(referenceId, token = null) {
  return requestJson(
    `${API_BASE_URL_VALUE}/api/v1/complaint/cases/${encodeURIComponent(referenceId)}`,
    {},
    token,
  );
}

export function getCvkiCaseStatus(referenceId, token = null) {
  return requestJson(
    `${API_BASE_URL_VALUE}/api/v1/complaint/cases/${encodeURIComponent(referenceId)}/status`,
    {},
    token,
  );
}

export function getMyCvkiCases(page = 1, limit = 10, token = null) {
  return requestJson(
    `${API_BASE_URL_VALUE}/api/v1/complaint/cases/my?page=${page}&limit=${limit}`,
    {},
    token,
  );
}

export function getSubmissionReadiness(referenceId, token = null) {
  return requestJson(
    `${API_BASE_URL_VALUE}/api/v1/complaint/cases/${encodeURIComponent(referenceId)}/submission-readiness`,
    {},
    token,
  );
}

export function prepareGovernmentSubmission(referenceId, token = null) {
  return requestJson(
    `${API_BASE_URL_VALUE}/api/v1/complaint/cases/${encodeURIComponent(referenceId)}/prepare-submission`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    },
    token,
  );
}
