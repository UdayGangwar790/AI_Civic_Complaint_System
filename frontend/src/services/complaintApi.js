import { API_BASE_URL_VALUE } from './detectionApi';
import { apiFetch } from './apiFetch';

export class ComplaintApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = 'ComplaintApiError';
    this.status = status;
  }
}

export async function generateComplaintDraft({ detection, location, authority, language, imageAttached }) {
  let response;
  try {
    response = await apiFetch(`${API_BASE_URL_VALUE}/api/v1/complaint/draft`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        detection,
        location,
        authority,
        language,
        image_attached: imageAttached,
      }),
    });
  } catch {
    throw new ComplaintApiError('The complaint draft service could not be reached.', 0);
  }

  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new ComplaintApiError(payload?.detail || 'The complaint draft could not be generated.', response.status);
  }
  if (!payload || typeof payload.draft_text !== 'string' || typeof payload.title !== 'string') {
    throw new ComplaintApiError('The complaint service returned an unexpected response.', response.status);
  }
  return payload;
}
