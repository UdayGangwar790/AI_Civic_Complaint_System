import { apiFetch } from './apiFetch';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL
  || `http://${typeof window === 'undefined' ? 'localhost' : window.location.hostname}:8000`;

const messagesByStatus = {
  400: 'The image could not be read. Choose a valid JPG, PNG, or WEBP image.',
  413: 'That image is larger than the 10 MB upload limit.',
  415: 'This image format is not supported. Choose JPG, PNG, or WEBP.',
  503: 'The detection model is currently unavailable. Try again shortly.',
};

export class DetectionApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = 'DetectionApiError';
    this.status = status;
  }
}

export async function predictImage(file) {
  const formData = new FormData();
  formData.append('file', file);

  let response;
  try {
    response = await apiFetch(`${API_BASE_URL}/api/v1/detection/predict`, {
      method: 'POST',
      body: formData,
    });
  } catch {
    throw new DetectionApiError(
      'The backend could not be reached. Confirm the API is running and try again.',
      0,
    );
  }

  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const message = messagesByStatus[response.status]
      || payload?.detail
      || 'The image could not be analyzed. Try again.';
    throw new DetectionApiError(message, response.status);
  }

  if (
    !payload
    || payload.success !== true
    || !Array.isArray(payload.detections)
    || typeof payload.annotated_image !== 'string'
    || !payload.annotated_image.startsWith('data:image/png;base64,')
  ) {
    throw new DetectionApiError('The backend returned an unexpected analysis response.', response.status);
  }

  return payload;
}

export const API_UPLOAD_LIMIT_BYTES = 10 * 1024 * 1024;
export const API_BASE_URL_VALUE = API_BASE_URL;
