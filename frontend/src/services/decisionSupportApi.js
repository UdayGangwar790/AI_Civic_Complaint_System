import { apiFetch } from './apiFetch';

const API_BASE = '/api/v1';

export async function getDecisionSupport(referenceId) {
  const resp = await apiFetch(`${API_BASE}/decision-support/cases/${encodeURIComponent(referenceId)}`);
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: 'Failed to fetch decision support' }));
    throw new Error(err.detail || `HTTP ${resp.status}`);
  }
  return resp.json();
}

export async function getDecisionProvenance(referenceId) {
  const resp = await apiFetch(`${API_BASE}/decision-support/cases/${encodeURIComponent(referenceId)}/provenance`);
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: 'Failed to fetch decision provenance' }));
    throw new Error(err.detail || `HTTP ${resp.status}`);
  }
  return resp.json();
}

export async function getDecisionGraph(referenceId) {
  const resp = await apiFetch(`${API_BASE}/decision-support/cases/${encodeURIComponent(referenceId)}/graph`);
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: 'Failed to fetch decision knowledge graph' }));
    throw new Error(err.detail || `HTTP ${resp.status}`);
  }
  return resp.json();
}

export async function reviewDecisionRecommendation(referenceId, reviewData) {
  const resp = await apiFetch(`${API_BASE}/decision-support/cases/${encodeURIComponent(referenceId)}/review`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(reviewData),
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: 'Failed to submit recommendation review' }));
    throw new Error(err.detail || `HTTP ${resp.status}`);
  }
  return resp.json();
}

export async function getCitizenView(referenceId) {
  const resp = await apiFetch(`${API_BASE}/decision-support/cases/${encodeURIComponent(referenceId)}/citizen-view`);
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: 'Failed to fetch citizen case view' }));
    throw new Error(err.detail || `HTTP ${resp.status}`);
  }
  return resp.json();
}

export async function getCaseClarification(referenceId) {
  const resp = await apiFetch(`${API_BASE}/decision-support/cases/${encodeURIComponent(referenceId)}/clarification`);
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: 'Failed to fetch clarification questions' }));
    throw new Error(err.detail || `HTTP ${resp.status}`);
  }
  return resp.json();
}

export async function submitCitizenClarification(referenceId, clarifyData) {
  const resp = await apiFetch(`${API_BASE}/decision-support/cases/${encodeURIComponent(referenceId)}/clarify`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(clarifyData),
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: 'Failed to submit clarification response' }));
    throw new Error(err.detail || `HTTP ${resp.status}`);
  }
  return resp.json();
}

export async function getInspectionProtocol(referenceId) {
  const resp = await apiFetch(`${API_BASE}/inspection/cases/${encodeURIComponent(referenceId)}/protocol`);
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: 'Failed to fetch inspection protocol' }));
    throw new Error(err.detail || `HTTP ${resp.status}`);
  }
  return resp.json();
}

export async function submitFieldInspection(referenceId, inspectionData) {
  const resp = await apiFetch(`${API_BASE}/inspection/cases/${encodeURIComponent(referenceId)}/submit`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(inspectionData),
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: 'Failed to submit field inspection' }));
    throw new Error(err.detail || `HTTP ${resp.status}`);
  }
  return resp.json();
}

export async function getFieldInspectionRecord(inspectionId) {
  const resp = await apiFetch(`${API_BASE}/inspection/${encodeURIComponent(inspectionId)}`);
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: 'Failed to fetch field inspection record' }));
    throw new Error(err.detail || `HTTP ${resp.status}`);
  }
  return resp.json();
}
