import { API_BASE_URL_VALUE } from './detectionApi';
import { apiFetch } from './apiFetch';

export class LocationApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = 'LocationApiError';
    this.status = status;
  }
}

export function getCurrentLocation(options = {}) {
  if (!navigator.geolocation) {
    return Promise.reject(new LocationApiError('This browser does not support device location.', 0));
  }

  return new Promise((resolve, reject) => {
    navigator.geolocation.getCurrentPosition(resolve, reject, {
      enableHighAccuracy: true,
      timeout: 10000,
      maximumAge: 0,
      ...options,
    });
  });
}

export function normalizePosition(position) {
  const { latitude, longitude, accuracy } = position.coords;
  if (
    !Number.isFinite(latitude) || latitude < -90 || latitude > 90
    || !Number.isFinite(longitude) || longitude < -180 || longitude > 180
    || !Number.isFinite(accuracy) || accuracy < 0
  ) {
    throw new LocationApiError('The browser returned invalid location data.', 0);
  }
  return {
    latitude,
    longitude,
    accuracy_meters: accuracy,
  };
}

export async function reverseGeocode({ latitude, longitude }) {
  const params = new URLSearchParams({ latitude, longitude });
  let response;
  try {
    response = await apiFetch(`${API_BASE_URL_VALUE}/api/v1/location/reverse-geocode?${params}`);
  } catch {
    throw new LocationApiError('Location details could not be reached. Coordinates are still available.', 0);
  }

  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new LocationApiError(
      payload?.detail || 'The location could not be resolved right now.',
      response.status,
    );
  }
  return payload;
}

export function locationErrorMessage(error) {
  if (error instanceof LocationApiError) return error.message;
  if (error?.code === 1) return 'Location permission was not granted.';
  if (error?.code === 2) return 'Your location is currently unavailable.';
  if (error?.code === 3) return 'Location request timed out. Try again.';
  return 'Your location could not be determined. Try again.';
}
