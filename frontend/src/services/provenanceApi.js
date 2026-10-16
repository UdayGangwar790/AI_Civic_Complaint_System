import { API_BASE_URL_VALUE } from './detectionApi';
import { apiFetch } from './apiFetch';

export class ProvenanceApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = 'ProvenanceApiError';
    this.status = status;
  }
}

export async function getCaseProvenance(referenceId) {
  const response = await apiFetch(
    `${API_BASE_URL_VALUE}/api/v1/provenance/cases/${encodeURIComponent(referenceId)}`
  );
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new ProvenanceApiError(
      data?.detail || 'Failed to fetch case evidence provenance chain.',
      response.status
    );
  }
  return data;
}
