import { API_BASE_URL_VALUE } from './detectionApi';
import { apiFetch } from './apiFetch';

export class AdminApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = 'AdminApiError';
    this.status = status;
  }
}

async function adminRequestJson(url, options = {}) {
  const token = null;
  const headers = {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(options.headers || {}),
  };

  let response;
  try {
    response = await apiFetch(url, { ...options, headers });
  } catch {
    throw new AdminApiError('Could not connect to CVKI administration service.', 0);
  }

  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new AdminApiError(payload?.detail || 'Administration request failed.', response.status);
  }
  return payload;
}

export async function fetchDashboardSummary() {
  return adminRequestJson(`${API_BASE_URL_VALUE}/api/v1/admin/dashboard/summary`);
}

export async function fetchAdminCases(params = {}) {
  const query = new URLSearchParams();
  if (params.search) query.set('search', params.search);
  if (params.priority) query.set('priority', params.priority);
  if (params.issue) query.set('issue', params.issue);
  if (params.status) query.set('status', params.status);
  if (params.assignment) query.set('assignment', params.assignment);
  if (params.duplicate) query.set('duplicate', params.duplicate);
  if (params.created_from) query.set('created_from', params.created_from);
  if (params.created_to) query.set('created_to', params.created_to);
  if (params.sort_by) query.set('sort_by', params.sort_by);
  if (params.page) query.set('page', params.page);
  if (params.page_size) query.set('page_size', params.page_size);

  const qs = query.toString();
  return adminRequestJson(`${API_BASE_URL_VALUE}/api/v1/admin/cases${qs ? `?${qs}` : ''}`);
}

export async function fetchAdminCaseDetail(referenceId) {
  return adminRequestJson(`${API_BASE_URL_VALUE}/api/v1/admin/cases/${encodeURIComponent(referenceId)}`);
}

export async function fetchAdminCaseIntelligence(referenceId) {
  return adminRequestJson(`${API_BASE_URL_VALUE}/api/v1/admin/cases/${encodeURIComponent(referenceId)}/intelligence`);
}

export async function assignCase(referenceId, authorityUserId) {
  return adminRequestJson(`${API_BASE_URL_VALUE}/api/v1/admin/cases/${encodeURIComponent(referenceId)}/assign`, {
    method: 'POST',
    body: JSON.stringify({ assigned_to_user_id: authorityUserId }),
  });
}

export async function unassignCase(referenceId) {
  return adminRequestJson(`${API_BASE_URL_VALUE}/api/v1/admin/cases/${encodeURIComponent(referenceId)}/unassign`, {
    method: 'POST',
  });
}

export async function fetchAuthorities() {
  return adminRequestJson(`${API_BASE_URL_VALUE}/api/v1/admin/authorities`);
}

export async function updateCaseStatus(referenceId, status, reason = '', resolutionEvidence = '') {
  return adminRequestJson(`${API_BASE_URL_VALUE}/api/v1/complaint/cases/${encodeURIComponent(referenceId)}/status`, {
    method: 'PATCH',
    body: JSON.stringify({
      status,
      reason: reason || undefined,
      resolution_evidence: resolutionEvidence || undefined,
    }),
  });
}

export async function fetchMapCases(params = {}) {
  const query = new URLSearchParams();
  if (params.issue) query.set('issue', params.issue);
  if (params.priority) query.set('priority', params.priority);
  if (params.status) query.set('status', params.status);
  if (params.city) query.set('city', params.city);
  if (params.authority) query.set('authority', params.authority);
  if (params.assignment) query.set('assignment', params.assignment);
  if (params.created_from) query.set('created_from', params.created_from);
  if (params.created_to) query.set('created_to', params.created_to);
  if (params.limit) query.set('limit', params.limit);

  const qs = query.toString();
  return adminRequestJson(`${API_BASE_URL_VALUE}/api/v1/admin/map/cases${qs ? `?${qs}` : ''}`);
}

export async function fetchOperationalAnalytics(params = {}) {
  const query = new URLSearchParams();
  if (params.issue) query.set('issue', params.issue);
  if (params.priority) query.set('priority', params.priority);
  if (params.status) query.set('status', params.status);
  if (params.city) query.set('city', params.city);
  if (params.authority) query.set('authority', params.authority);
  if (params.created_from) query.set('created_from', params.created_from);
  if (params.created_to) query.set('created_to', params.created_to);
  if (params.group_by) query.set('group_by', params.group_by);

  const qs = query.toString();
  return adminRequestJson(`${API_BASE_URL_VALUE}/api/v1/admin/analytics${qs ? `?${qs}` : ''}`);
}

export async function downloadAnalyticsCsv(params = {}) {
  const token = null;
  const query = new URLSearchParams();
  if (params.issue) query.set('issue', params.issue);
  if (params.priority) query.set('priority', params.priority);
  if (params.status) query.set('status', params.status);
  if (params.city) query.set('city', params.city);
  if (params.authority) query.set('authority', params.authority);
  if (params.created_from) query.set('created_from', params.created_from);
  if (params.created_to) query.set('created_to', params.created_to);
  if (params.group_by) query.set('group_by', params.group_by);

  const qs = query.toString();
  const res = await apiFetch(`${API_BASE_URL_VALUE}/api/v1/admin/analytics/export${qs ? `?${qs}` : ''}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) throw new AdminApiError('Failed to export analytics CSV.', res.status);
  const blob = await res.blob();
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'cvki_operational_analytics.csv';
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(url);
}

export async function fetchAuditLogs(params = {}) {
  const query = new URLSearchParams();
  if (params.actor) query.set('actor', params.actor);
  if (params.role) query.set('role', params.role);
  if (params.action) query.set('action', params.action);
  if (params.result) query.set('result', params.result);
  if (params.reference_id) query.set('reference_id', params.reference_id);
  if (params.created_from) query.set('created_from', params.created_from);
  if (params.created_to) query.set('created_to', params.created_to);
  if (params.page) query.set('page', params.page);
  if (params.page_size) query.set('page_size', params.page_size);

  const qs = query.toString();
  return adminRequestJson(`${API_BASE_URL_VALUE}/api/v1/admin/audit${qs ? `?${qs}` : ''}`);
}

export async function fetchSecurityOverview() {
  return adminRequestJson(`${API_BASE_URL_VALUE}/api/v1/admin/audit/summary`);
}
