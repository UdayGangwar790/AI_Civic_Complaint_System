import { API_BASE_URL_VALUE } from './detectionApi';
import { apiFetch } from './apiFetch';

const USER_STORAGE_KEY = 'cvki_auth_user';
const LEGACY_TOKEN_STORAGE_KEY = 'cvki_auth_token';

export class AuthApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = 'AuthApiError';
    this.status = status;
  }
}

async function requestJson(url, options = {}) {
  let response;
  try {
    response = await apiFetch(url, options);
  } catch {
    throw new AuthApiError('The authentication service could not be reached.', 0);
  }
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new AuthApiError(payload?.detail || 'Authentication request failed.', response.status);
  }
  return payload;
}

export async function registerCitizen(credentialsOrEmail, maybePassword) {
  const email = typeof credentialsOrEmail === 'object' ? credentialsOrEmail.email : credentialsOrEmail;
  const password = typeof credentialsOrEmail === 'object' ? credentialsOrEmail.password : maybePassword;

  return requestJson(`${API_BASE_URL_VALUE}/api/v1/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  });
}

export async function loginCitizen(credentialsOrEmail, maybePassword) {
  const email = typeof credentialsOrEmail === 'object' ? credentialsOrEmail.email : credentialsOrEmail;
  const password = typeof credentialsOrEmail === 'object' ? credentialsOrEmail.password : maybePassword;

  return requestJson(`${API_BASE_URL_VALUE}/api/v1/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  });
}

export async function logout() {
  await requestJson(`${API_BASE_URL_VALUE}/api/v1/auth/logout`, { method: 'POST' });
  clearAuthSession();
}

export async function getCurrentUser() {
  const payload = await requestJson(`${API_BASE_URL_VALUE}/api/v1/auth/me`);
  setStoredUser(payload);
  return payload;
}

export async function checkAdminAccess() {
  return requestJson(`${API_BASE_URL_VALUE}/api/v1/admin/access-check`);
}

export async function checkAuthorityAccess() {
  return requestJson(`${API_BASE_URL_VALUE}/api/v1/authority/access-check`);
}

function removeLegacyToken() {
  try {
    localStorage.removeItem(LEGACY_TOKEN_STORAGE_KEY);
  } catch {
    // Storage can be unavailable in restricted browser contexts.
  }
}

export function getStoredUser() {
  removeLegacyToken();
  try {
    const raw = localStorage.getItem(USER_STORAGE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }

}

export function getCurrentUserRole(user = null) {
  const activeUser = user || getStoredUser();
  return activeUser?.role || 'citizen';
}

export function setStoredUser(user) {
  try {
    if (user) {
      localStorage.setItem(USER_STORAGE_KEY, JSON.stringify(user));
    } else {
      localStorage.removeItem(USER_STORAGE_KEY);
    }
  } catch {
    // Storage can be unavailable in restricted browser contexts.
  }
  removeLegacyToken();
}

export function setAuthSession(user) {
  setStoredUser(user);
}

export function clearStoredAuth() {
  try {
    localStorage.removeItem(USER_STORAGE_KEY);
  } catch {
    // Storage can be unavailable in restricted browser contexts.
  }
  removeLegacyToken();
}

export const clearAuthSession = clearStoredAuth;
