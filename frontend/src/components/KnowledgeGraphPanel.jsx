import { useEffect, useState } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  HelpCircle,
  Info,
  LoaderCircle,
  Network,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
  X,
} from 'lucide-react';
import {
  explainRelationship,
  getCaseKnowledgeGraph,
  rebuildCaseKnowledgeGraph,
} from '../services/knowledgeGraphApi';

export function KnowledgeGraphPanel({ referenceId, isStaff = false }) {
  const [subgraph, setSubgraph] = useState(null);
  const [loading, setLoading] = useState(true);
  const [rebuilding, setRebuilding] = useState(false);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState('explorer'); // 'explorer' | 'visual'
  const [selectedEdgeId, setSelectedEdgeId] = useState(null);
  const [explanation, setExplanation] = useState(null);
  const [explaining, setExplaining] = useState(false);
  const [selectedNode, setSelectedNode] = useState(null);

  const loadGraph = (refId) => {
    setLoading(true);
    setError(null);
    getCaseKnowledgeGraph(refId)
      .then((data) => {
        setSubgraph(data);
        setLoading(false);
      })
      .catch((err) => {
        setError(err?.message || 'Civic knowledge graph is unavailable.');
        setLoading(false);
      });
  };

  useEffect(() => {
    loadGraph(referenceId);
  }, [referenceId]);

  const handleRebuild = async () => {
    if (rebuilding) return;
    setRebuilding(true);
    try {
      const rebuilt = await rebuildCaseKnowledgeGraph(referenceId);
      setSubgraph(rebuilt);
      setSelectedEdgeId(null);
      setExplanation(null);
    } catch (err) {
      alert(err?.message || 'Failed to rebuild knowledge graph.');
    } finally {
      setRebuilding(false);
    }
  };

  const handleExplainEdge = async (edgeId) => {
    setSelectedEdgeId(edgeId);
    setExplaining(true);
    try {
      const exp = await explainRelationship(edgeId);
      setExplanation(exp);
    } catch (err) {
      setExplanation({
        error: err?.message || 'Could not retrieve relationship explanation.',
      });
    } finally {
      setExplaining(false);
    }
  };

  if (loading) {
    return (
      <div className="detail-section geospatial-panel-loading">
        <LoaderCircle size={18} className="spin-slow" />
        <span>Synthesizing Civic Knowledge Graph &amp; connecting entity claims...</span>
      </div>
    );
  }

  if (error || !subgraph) {
    return (
      <div className="detail-section">
        <h4>Civic Knowledge Graph</h4>
        <p className="text-muted" style={{ fontSize: '12px' }}>
          {error || 'Knowledge graph records are currently unavailable for this record.'}
        </p>
      </div>
    );
  }

  const nodes = subgraph.nodes || [];
  const edges = subgraph.edges || [];

  // Group nodes by type for explorer view
  const nodesByType = {};
  nodes.forEach((n) => {
    if (!nodesByType[n.node_type]) nodesByType[n.node_type] = [];
    nodesByType[n.node_type].push(n);
  });

  // Map canonical_key to node for quick lookups
  const nodeMap = new Map();
  nodes.forEach((n) => nodeMap.set(n.canonical_key, n));

  return (
    <div className="detail-section knowledge-graph-card">
      {/* Header */}
      <div className="kg-header-row">
        <div className="kg-title-group">
          <h4>
            <Network size={18} className="text-primary" /> Civic Knowledge Graph
          </h4>
          <span className="kg-stats-tag">
            {nodes.length} entities &bull; {edges.length} verified relationships
          </span>
        </div>
        <div className="kg-actions">
          <div className="kg-tab-pill-group">
            <button
              type="button"
              className={`kg-tab-pill ${activeTab === 'explorer' ? 'active' : ''}`}
              onClick={() => setActiveTab('explorer')}
            >
              Relationship Explorer
            </button>
            {isStaff && (
              <button
                type="button"
                className={`kg-tab-pill ${activeTab === 'visual' ? 'active' : ''}`}
                onClick={() => setActiveTab('visual')}
              >
                Visual Topology
              </button>
            )}
          </div>
          {isStaff && (
            <button
              type="button"
              className="kg-btn-secondary"
              onClick={handleRebuild}
              disabled={rebuilding}
              title="Deterministically rebuild knowledge graph from authoritative records"
            >
              <RefreshCw size={13} className={rebuilding ? 'spin-slow' : ''} />
              <span>{rebuilding ? 'Rebuilding...' : 'Rebuild'}</span>
            </button>
          )}
        </div>
      </div>

      {/* Explorer Mode */}
      {activeTab === 'explorer' && (
        <div className="kg-explorer-view">
          <p className="kg-section-desc">
            Trace the verified entity relationships connecting this civic incident to road infrastructure,
            responsible authorities, external context, and resolution evidence.
          </p>

          <div className="kg-relationship-chain">
            {edges.map((edge) => {
              const fromN = nodeMap.get(edge.from_node);
              const toN = nodeMap.get(edge.to_node);
              const isSelected = selectedEdgeId === edge.edge_id;

              return (
                <div
                  key={edge.edge_id}
                  className={`kg-edge-card state-${edge.verification_state} ${isSelected ? 'selected' : ''}`}
                  onClick={() => handleExplainEdge(edge.edge_id)}
                >
                  <div className="kg-edge-card-from">
                    <span className="kg-node-badge-type">{fromN?.node_type || 'Entity'}</span>
                    <strong className="kg-node-name">{fromN?.display_name || edge.from_node}</strong>
                  </div>

                  <div className="kg-edge-connector">
                    <div className="kg-edge-line" />
                    <span className="kg-relation-pill" title={edge.relation_type}>
                      {edge.relation_type.replaceAll('_', ' ')}
                    </span>
                    <div className="kg-edge-arrow">&rarr;</div>
                  </div>

                  <div className="kg-edge-card-to">
                    <span className="kg-node-badge-type">{toN?.node_type || 'Entity'}</span>
                    <strong className="kg-node-name">{toN?.display_name || edge.to_node}</strong>
                  </div>

                  <div className="kg-edge-meta-col">
                    <span className={`kg-verification-badge state-${edge.verification_state}`}>
                      {edge.verification_state === 'verified' && <ShieldCheck size={11} />}
                      {edge.verification_state === 'partially_verified' && <Info size={11} />}
                      {edge.verification_state === 'not_verified' && <ShieldAlert size={11} />}
                      {edge.verification_state === 'system_derived' && <Network size={11} />}
                      {edge.verification_state.replaceAll('_', ' ')}
                    </span>
                    <button
                      type="button"
                      className="kg-why-link"
                      onClick={(e) => {
                        e.stopPropagation();
                        handleExplainEdge(edge.edge_id);
                      }}
                    >
                      <HelpCircle size={11} /> Explain Link
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Visual Mode (Staff/Admin) */}
      {activeTab === 'visual' && isStaff && (
        <div className="kg-visual-view">
          <div className="kg-visual-canvas-wrapper">
            <svg className="kg-svg-canvas" viewBox="0 0 860 380" preserveAspectRatio="xMidYMid meet">
              <defs>
                <marker
                  id="kg-arrowhead"
                  markerWidth="8"
                  markerHeight="6"
                  refX="7"
                  refY="3"
                  orient="auto"
                >
                  <polygon points="0 0, 8 3, 0 6" fill="#64748b" />
                </marker>
              </defs>

              {/* Render edges */}
              {edges.map((edge) => {
                // Distribute nodes roughly along 4 columns
                const fromIdx = nodes.findIndex((n) => n.canonical_key === edge.from_node);
                const toIdx = nodes.findIndex((n) => n.canonical_key === edge.to_node);
                const x1 = 80 + ((fromIdx >= 0 ? fromIdx % 4 : 0) * 220);
                const y1 = 40 + (Math.floor(Math.max(0, fromIdx) / 4) * 80);
                const x2 = 80 + ((toIdx >= 0 ? toIdx % 4 : 2) * 220);
                const y2 = 40 + (Math.floor(Math.max(0, toIdx) / 4) * 80);

                const isSelected = selectedEdgeId === edge.edge_id;
                return (
                  <g key={edge.edge_id} onClick={() => handleExplainEdge(edge.edge_id)} className="kg-svg-edge-group">
                    <line
                      x1={x1}
                      y1={y1}
                      x2={x2}
                      y2={y2}
                      stroke={isSelected ? '#3b82f6' : '#94a3b8'}
                      strokeWidth={isSelected ? '2.5' : '1.5'}
                      strokeDasharray={edge.verification_state === 'system_derived' ? '4 3' : 'none'}
                      markerEnd="url(#kg-arrowhead)"
                    />
                    <text
                      x={(x1 + x2) / 2}
                      y={(y1 + y2) / 2 - 6}
                      textAnchor="middle"
                      fill="#475569"
                      fontSize="9"
                      fontWeight="600"
                    >
                      {edge.relation_type}
                    </text>
                  </g>
                );
              })}

              {/* Render nodes */}
              {nodes.map((node, idx) => {
                const col = idx % 4;
                const row = Math.floor(idx / 4);
                const cx = 80 + col * 220;
                const cy = 40 + row * 80;
                const isSelected = selectedNode?.canonical_key === node.canonical_key;

                let fillColor = '#e2e8f0';
                let strokeColor = '#64748b';
                if (node.node_type === 'case' || node.node_type === 'civic_issue') {
                  fillColor = '#fee2e2';
                  strokeColor = '#ef4444';
                } else if (node.node_type === 'road' || node.node_type === 'location') {
                  fillColor = '#e0f2fe';
                  strokeColor = '#0284c7';
                } else if (node.node_type === 'maintenance_authority' || node.node_type === 'jurisdiction') {
                  fillColor = '#dcfce7';
                  strokeColor = '#16a34a';
                } else if (node.node_type === 'builder_or_contractor') {
                  fillColor = '#f3e8ff';
                  strokeColor = '#9333ea';
                } else if (node.node_type.includes('context')) {
                  fillColor = '#fef3c7';
                  strokeColor = '#d97706';
                }

                return (
                  <g
                    key={node.canonical_key}
                    className="kg-svg-node"
                    onClick={() => setSelectedNode(node)}
                  >
                    <rect
                      x={cx - 75}
                      y={cy - 18}
                      width="150"
                      height="36"
                      rx="8"
                      fill={fillColor}
                      stroke={isSelected ? '#2563eb' : strokeColor}
                      strokeWidth={isSelected ? '2.5' : '1.5'}
                    />
                    <text
                      x={cx}
                      y={cy - 2}
                      textAnchor="middle"
                      fill="#0f172a"
                      fontSize="10"
                      fontWeight="600"
                    >
                      {node.display_name?.slice(0, 20)}
                    </text>
                    <text
                      x={cx}
                      y={cy + 10}
                      textAnchor="middle"
                      fill="#64748b"
                      fontSize="8"
                    >
                      {node.node_type}
                    </text>
                  </g>
                );
              })}
            </svg>
          </div>

          {selectedNode && (
            <div className="kg-selected-node-card">
              <div className="kg-card-header">
                <strong>{selectedNode.display_name}</strong>
                <button
                  type="button"
                  className="kg-icon-btn"
                  onClick={() => setSelectedNode(null)}
                >
                  <X size={14} />
                </button>
              </div>
              <div className="kg-node-details-grid">
                <div><span>Canonical Key:</span> <code>{selectedNode.canonical_key}</code></div>
                <div><span>Type:</span> <em>{selectedNode.node_type}</em></div>
                <div><span>Associated Cases:</span> {selectedNode.case_references?.join(', ') || 'N/A'}</div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Relationship Explanation Modal / Drawer */}
      {selectedEdgeId && (
        <div className="kg-explanation-drawer">
          <div className="kg-drawer-header">
            <div className="kg-drawer-title">
              <HelpCircle size={16} className="text-primary" />
              <strong>Relationship Explainability Inspector</strong>
            </div>
            <button
              type="button"
              className="kg-icon-btn"
              onClick={() => {
                setSelectedEdgeId(null);
                setExplanation(null);
              }}
            >
              <X size={14} />
            </button>
          </div>

          {explaining ? (
            <div className="kg-drawer-loading">
              <LoaderCircle size={16} className="spin-slow" />
              <span>Hydrating evidence records and provenance chain...</span>
            </div>
          ) : explanation?.error ? (
            <p className="text-danger" style={{ fontSize: '12px' }}>{explanation.error}</p>
          ) : explanation ? (
            <div className="kg-drawer-body">
              <div className="kg-drawer-edge-header">
                <span className="kg-edge-pill-lg">{explanation.from_node?.display_name || explanation.canonical_edge_key}</span>
                <span className="kg-edge-rel-arrow">&rarr; {explanation.relation_type} &rarr;</span>
                <span className="kg-edge-pill-lg">{explanation.to_node?.display_name || explanation.canonical_edge_key}</span>
              </div>

              <div className="kg-explanation-callout">
                <p><strong>Rationale:</strong> {explanation.explanation}</p>
              </div>

              <div className="kg-meta-matrix">
                <div className="kg-meta-item">
                  <span className="kg-meta-label">Verification State</span>
                  <span className={`kg-verification-badge state-${explanation.verification_state}`}>
                    {explanation.verification_state.replaceAll('_', ' ')}
                  </span>
                </div>
                <div className="kg-meta-item">
                  <span className="kg-meta-label">Evidence Source</span>
                  <span className="kg-meta-val">{explanation.source || 'Official Registry'}</span>
                </div>
                <div className="kg-meta-item">
                  <span className="kg-meta-label">Source Type</span>
                  <span className="kg-meta-val">{explanation.source_type?.replaceAll('_', ' ') || 'SYSTEM'}</span>
                </div>
                <div className="kg-meta-item">
                  <span className="kg-meta-label">Freshness</span>
                  <span className={`kg-freshness-tag ${explanation.freshness || 'FRESH'}`}>
                    {explanation.freshness || 'FRESH'}
                  </span>
                </div>
              </div>

              {explanation.evidence_ids?.length > 0 && (
                <div className="kg-evidence-refs">
                  <span className="kg-meta-label">Supporting Evidence References</span>
                  <div className="kg-evidence-tag-list">
                    {explanation.evidence_ids.map((id) => (
                      <span key={id} className="kg-evidence-tag">
                        <CheckCircle2 size={11} /> {id}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {explanation.limitations?.length > 0 && (
                <div className="kg-limitations-box">
                  <span className="kg-limitations-title"><AlertTriangle size={12} /> Epistemological Caveats</span>
                  <ul>
                    {explanation.limitations.map((lim, idx) => (
                      <li key={idx}>{lim}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          ) : null}
        </div>
      )}

      {/* Epistemological Disclaimer Footer */}
      <div className="kg-footer-disclaimer">
        <Info size={13} className="text-muted" />
        <span>
          <strong>Epistemological Disclaimer:</strong> The knowledge graph is an integration and
          explainability layer. It connects verified system claims with explicit uncertainty and does
          not independently establish the truth of underlying external claims.
        </span>
      </div>
    </div>
  );
}
