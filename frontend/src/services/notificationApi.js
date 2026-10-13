import { API_BASE_URL_VALUE } from './detectionApi';
import { apiFetch } from './apiFetch';

export class NotificationApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = 'NotificationApiError';
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
    throw new NotificationApiError('The CVKI notification service could not be reached.', 0);
  }
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new NotificationApiError(payload?.detail || 'The notification request failed.', response.status);
  }
  return payload;
}

export function getNotifications(page = 1, pageSize = 20, unreadOnly = false, token = null) {
  return requestJson(
    `${API_BASE_URL_VALUE}/api/v1/notifications?page=${page}&page_size=${pageSize}&unread_only=${unreadOnly}`,
    {},
    token,
  );
}

export function getUnreadNotificationCount(token = null) {
  return requestJson(
    `${API_BASE_URL_VALUE}/api/v1/notifications/unread-count`,
    {},
    token,
  );
}

export function markNotificationRead(notificationId, token = null) {
  return requestJson(
    `${API_BASE_URL_VALUE}/api/v1/notifications/${encodeURIComponent(notificationId)}/read`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    },
    token,
  );
}

export function markAllNotificationsRead(token = null) {
  return requestJson(
    `${API_BASE_URL_VALUE}/api/v1/notifications/read-all`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    },
    token,
  );
}
