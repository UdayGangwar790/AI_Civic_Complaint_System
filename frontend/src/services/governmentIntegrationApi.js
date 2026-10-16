import { API_BASE_URL_VALUE } from './detectionApi';
import { apiFetch } from './apiFetch';

export class GovernmentIntegrationApiError extends Error {
  constructor(message, status, code = null) {
    super(message);
    this.name = 'GovernmentIntegrationApiError';
    this.status = status;
    this.code = code;
  }
}

export async function getGovernmentIntegrations(activeOnly = false) {
  const url = `${API_BASE_URL_VALUE}/api/v1/government-integrations${activeOnly ? '?active_only=true' : ''}`;
  const response = await apiFetch(url);
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new GovernmentIntegrationApiError(
      data?.detail || 'Failed to list government integrations.',
      response.status
    );
  }
  return data;
}

export async function getGovernmentIntegration(integrationId) {
  const url = `${API_BASE_URL_VALUE}/api/v1/government-integrations/${encodeURIComponent(integrationId)}`;
  const response = await apiFetch(url);
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new GovernmentIntegrationApiError(
      data?.detail || 'Failed to retrieve government integration.',
      response.status
    );
  }
  return data;
}

export async function getCaseGovernmentSubmission(referenceId) {
  const url = `${API_BASE_URL_VALUE}/api/v1/government/cases/${encodeURIComponent(referenceId)}/submission`;
  const response = await apiFetch(url);
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new GovernmentIntegrationApiError(
      data?.detail || 'Failed to retrieve government submission summary.',
      response.status
    );
  }
  return data;
}

export async function prepareGovernmentSubmissionPackage(referenceId) {
  const url = `${API_BASE_URL_VALUE}/api/v1/government/cases/${encodeURIComponent(referenceId)}/prepare`;
  const response = await apiFetch(url, { method: 'POST' });
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new GovernmentIntegrationApiError(
      data?.detail || 'Failed to prepare government dispatch package.',
      response.status
    );
  }
  return data;
}

export async function submitGovernmentCase(referenceId, integrationId = null, idempotencyKey = null) {
  const url = `${API_BASE_URL_VALUE}/api/v1/government/cases/${encodeURIComponent(referenceId)}/submit`;
  const body = {};
  if (integrationId) body.integration_id = integrationId;
  if (idempotencyKey) body.idempotency_key = idempotencyKey;

  const response = await apiFetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new GovernmentIntegrationApiError(
      data?.detail || 'Failed to submit case to government integration.',
      response.status,
      data?.error_code
    );
  }
  return data;
}

export async function reconcileGovernmentSubmission(referenceId, reason = null) {
  const url = `${API_BASE_URL_VALUE}/api/v1/government/cases/${encodeURIComponent(referenceId)}/reconcile`;
  const response = await apiFetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ reason: reason || 'Admin manual reconciliation check' }),
  });
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new GovernmentIntegrationApiError(
      data?.detail || 'Failed to reconcile government submission.',
      response.status
    );
  }
  return data;
}

export async function syncGovernmentStatus(referenceId) {
  const url = `${API_BASE_URL_VALUE}/api/v1/government/cases/${encodeURIComponent(referenceId)}/status`;
  const response = await apiFetch(url);
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new GovernmentIntegrationApiError(
      data?.detail || 'Failed to synchronize external government status.',
      response.status
    );
  }
  return data;
}

export async function getCaseGovernmentReferences(referenceId) {
  const url = `${API_BASE_URL_VALUE}/api/v1/government/cases/${encodeURIComponent(referenceId)}/references`;
  const response = await apiFetch(url);
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new GovernmentIntegrationApiError(
      data?.detail || 'Failed to retrieve government reference mappings.',
      response.status
    );
  }
  return data;
}

export async function triggerGovernmentStatusSync(referenceId) {
  const url = `${API_BASE_URL_VALUE}/api/v1/government/cases/${encodeURIComponent(referenceId)}/status/sync`;
  const response = await apiFetch(url, { method: 'POST' });
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new GovernmentIntegrationApiError(
      data?.detail || 'Failed to trigger status synchronization.',
      response.status
    );
  }
  return data;
}

export async function getGovernmentStatusHistory(referenceId, limit = 50) {
  const url = `${API_BASE_URL_VALUE}/api/v1/government/cases/${encodeURIComponent(referenceId)}/status/history?limit=${limit}`;
  const response = await apiFetch(url);
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new GovernmentIntegrationApiError(
      data?.detail || 'Failed to retrieve status history.',
      response.status
    );
  }
  return data;
}

export async function getCaseEscalation(referenceId) {
  const url = `${API_BASE_URL_VALUE}/api/v1/government/cases/${encodeURIComponent(referenceId)}/escalation`;
  const response = await apiFetch(url);
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new GovernmentIntegrationApiError(
      data?.detail || 'Failed to retrieve case escalation status.',
      response.status
    );
  }
  return data;
}

export async function evaluateCaseEscalation(referenceId) {
  const url = `${API_BASE_URL_VALUE}/api/v1/government/cases/${encodeURIComponent(referenceId)}/escalation/evaluate`;
  const response = await apiFetch(url, { method: 'POST' });
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new GovernmentIntegrationApiError(
      data?.detail || 'Failed to evaluate case escalation.',
      response.status
    );
  }
  return data;
}

export async function getCaseEscalationHistory(referenceId, limit = 50) {
  const url = `${API_BASE_URL_VALUE}/api/v1/government/cases/${encodeURIComponent(referenceId)}/escalation/history?limit=${limit}`;
  const response = await apiFetch(url);
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new GovernmentIntegrationApiError(
      data?.detail || 'Failed to retrieve escalation history.',
      response.status
    );
  }
  return data;
}

export async function getEscalationPolicies(enabledOnly = false) {
  const url = `${API_BASE_URL_VALUE}/api/v1/admin/government/escalation-policies${enabledOnly ? '?enabled_only=true' : ''}`;
  const response = await apiFetch(url);
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new GovernmentIntegrationApiError(
      data?.detail || 'Failed to retrieve escalation policies.',
      response.status
    );
  }
  return data;
}

export async function submitResolutionVerification(referenceId, payload) {
  const url = `${API_BASE_URL_VALUE}/api/v1/government/cases/${encodeURIComponent(referenceId)}/resolution-verification`;
  const response = await apiFetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new GovernmentIntegrationApiError(
      data?.detail || 'Failed to submit citizen resolution verification.',
      response.status
    );
  }
  return data;
}

export async function getLatestResolutionVerification(referenceId, integrationId = null) {
  const q = integrationId ? `?integration_id=${encodeURIComponent(integrationId)}` : '';
  const url = `${API_BASE_URL_VALUE}/api/v1/government/cases/${encodeURIComponent(referenceId)}/resolution-verification${q}`;
  const response = await apiFetch(url);
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    if (response.status === 404) return null;
    throw new GovernmentIntegrationApiError(
      data?.detail || 'Failed to retrieve resolution verification.',
      response.status
    );
  }
  return data;
}

export async function getResolutionVerificationHistory(referenceId, integrationId = null, limit = 50) {
  const q = `?limit=${limit}${integrationId ? `&integration_id=${encodeURIComponent(integrationId)}` : ''}`;
  const url = `${API_BASE_URL_VALUE}/api/v1/government/cases/${encodeURIComponent(referenceId)}/resolution-verification/history${q}`;
  const response = await apiFetch(url);
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new GovernmentIntegrationApiError(
      data?.detail || 'Failed to retrieve resolution verification history.',
      response.status
    );
  }
  return data;
}

export async function reviewResolutionVerification(referenceId, verificationId, payload) {
  const url = `${API_BASE_URL_VALUE}/api/v1/admin/government/cases/${encodeURIComponent(referenceId)}/resolution-verification/${encodeURIComponent(verificationId)}/review`;
  const response = await apiFetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new GovernmentIntegrationApiError(
      data?.detail || 'Failed to review resolution verification.',
      response.status
    );
  }
  return data;
}

export async function getGovernmentAnalyticsSummary(integrationId = null) {
  const q = integrationId ? `?integration_id=${encodeURIComponent(integrationId)}` : '';
  const url = `${API_BASE_URL_VALUE}/api/v1/admin/government/analytics/summary${q}`;
  const response = await apiFetch(url);
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new GovernmentIntegrationApiError(
      data?.detail || 'Failed to retrieve government response analytics.',
      response.status
    );
  }
  return data;
}

export async function getCaseTimelineAnalytics(referenceId, integrationId = null) {
  const q = integrationId ? `?integration_id=${encodeURIComponent(integrationId)}` : '';
  const url = `${API_BASE_URL_VALUE}/api/v1/government/cases/${encodeURIComponent(referenceId)}/analytics/timeline${q}`;
  const response = await apiFetch(url);
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new GovernmentIntegrationApiError(
      data?.detail || 'Failed to retrieve case timeline analytics.',
      response.status
    );
  }
  return data;
}
