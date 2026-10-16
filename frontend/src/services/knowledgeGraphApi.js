import { API_BASE_URL_VALUE } from './detectionApi';
import { apiFetch } from './apiFetch';

export class KnowledgeGraphApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = 'KnowledgeGraphApiError';
    this.status = status;
  }
}

export async function getCaseKnowledgeGraph(referenceId, options = {}) {
  const { maxDepth, maxNodes, maxEdges } = options;
  const params = new URLSearchParams();
  if (maxDepth) params.append('max_depth', maxDepth);
  if (maxNodes) params.append('max_nodes', maxNodes);
  if (maxEdges) params.append('max_edges', maxEdges);

  const queryStr = params.toString() ? `?${params.toString()}` : '';
  const response = await apiFetch(
    `${API_BASE_URL_VALUE}/api/v1/knowledge-graph/cases/${encodeURIComponent(referenceId)}${queryStr}`
  );
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new KnowledgeGraphApiError(
      data?.detail || 'Failed to fetch civic knowledge graph for case.',
      response.status
    );
  }
  return data;
}

export async function rebuildCaseKnowledgeGraph(referenceId) {
  const response = await apiFetch(
    `${API_BASE_URL_VALUE}/api/v1/knowledge-graph/cases/${encodeURIComponent(referenceId)}/rebuild`,
    {
      method: 'POST',
    }
  );
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new KnowledgeGraphApiError(
      data?.detail || 'Failed to rebuild civic knowledge graph for case.',
      response.status
    );
  }
  return data;
}

export async function getRoadKnowledgeGraph(roadKey) {
  const response = await apiFetch(
    `${API_BASE_URL_VALUE}/api/v1/knowledge-graph/roads/${encodeURIComponent(roadKey)}`
  );
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new KnowledgeGraphApiError(
      data?.detail || 'Failed to fetch road knowledge graph.',
      response.status
    );
  }
  return data;
}

export async function getAuthorityKnowledgeGraph(authorityKey) {
  const response = await apiFetch(
    `${API_BASE_URL_VALUE}/api/v1/knowledge-graph/authorities/${encodeURIComponent(authorityKey)}`
  );
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new KnowledgeGraphApiError(
      data?.detail || 'Failed to fetch authority knowledge graph.',
      response.status
    );
  }
  return data;
}

export async function explainRelationship(edgeId) {
  const response = await apiFetch(
    `${API_BASE_URL_VALUE}/api/v1/knowledge-graph/relationships/${encodeURIComponent(edgeId)}`
  );
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new KnowledgeGraphApiError(
      data?.detail || 'Failed to retrieve relationship explanation.',
      response.status
    );
  }
  return data;
}

export async function findRelatedCases(referenceId, limit = 10) {
  const response = await apiFetch(
    `${API_BASE_URL_VALUE}/api/v1/knowledge-graph/cases/${encodeURIComponent(referenceId)}/related?limit=${limit}`
  );
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new KnowledgeGraphApiError(
      data?.detail || 'Failed to retrieve related cases.',
      response.status
    );
  }
  return data;
}
