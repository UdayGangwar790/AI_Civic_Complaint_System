import { useEffect, useState } from 'react';
import {
  ExternalLink,
  FileCheck2,
  History,
  Info,
  LoaderCircle,
  ShieldAlert,
  ShieldCheck,
} from 'lucide-react';
import { getCaseProvenance } from '../services/provenanceApi';

export function EvidenceProvenancePanel({ referenceId, isStaff = false }) {
  const [provenance, setProvenance] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showTechnical, setShowTechnical] = useState(false);

  useEffect(() => {
    let isMounted = true;
    setLoading(true);
    setError(null);

    getCaseProvenance(referenceId)
      .then((data) => {
        if (!isMounted) return;
        setProvenance(data);
        setLoading(false);
      })
      .catch((err) => {
        if (!isMounted) return;
        setError(err?.message || 'Evidence provenance chain is unavailable.');
        setLoading(false);
      });

    return () => {
      isMounted = false;
    };
  }, [referenceId]);

  if (loading) {
    return (
      <div className="detail-section geospatial-panel-loading">
        <LoaderCircle size={18} className="spin-slow" />
        <span>Verifying evidence provenance chain &amp; source records...</span>
      </div>
    );
  }

  if (error || !provenance) {
    return (
      <div className="detail-section">
        <h4>Evidence &amp; Provenance Chain</h4>
        <p className="text-muted" style={{ fontSize: '12px' }}>
          {error || 'Provenance records are currently unavailable for this record.'}
        </p>
      </div>
    );
  }

  const claims = provenance.claims || [];
  const summaryState = provenance.summary_verification_state || 'partially_verified';

  return (
    <div className="detail-section provenance-card">
      <div className="provenance-header-row">
        <div className="provenance-title-group">
          <h4>
            <FileCheck2 size={16} /> Evidence &amp; Provenance Engine
          </h4>
          <span className="provenance-count-tag">{claims.length} claims traced</span>
        </div>
        <div className="provenance-badges">
          <span className={`prov-state-badge state-${summaryState}`}>
            {summaryState === 'verified' && <ShieldCheck size={12} />}
            {summaryState === 'partially_verified' && <Info size={12} />}
            {summaryState === 'not_verified' && <ShieldAlert size={12} />}
            {summaryState.toUpperCase().replaceAll('_', ' ')}
          </span>
          {isStaff && (
            <button
              type="button"
              className="prov-toggle-btn"
              onClick={() => setShowTechnical(!showTechnical)}
              title="Toggle technical hash and audit metadata"
            >
              <History size={12} /> {showTechnical ? 'Standard View' : 'Technical Details'}
            </button>
          )}
        </div>
      </div>

      <p className="provenance-subtext text-muted">
        Every system assertion is strictly grounded in verifiable source data. Client-side claims are never treated as verification proof.
      </p>

      <div className="provenance-claims-list">
        {claims.map((claim) => (
          <div key={claim.evidence_id} className={`prov-claim-item state-${claim.verification_state}`}>
            <div className="prov-claim-top">
              <span className="prov-claim-type">
                {(claim.claim_type || '').toUpperCase().replaceAll('_', ' ')}
              </span>
              <div className="prov-claim-pills">
                <span className={`prov-freshness-pill ${claim.freshness}`}>
                  {claim.freshness.toUpperCase()}
                </span>
                <span className={`prov-verification-pill state-${claim.verification_state}`}>
                  {claim.verification_state.replaceAll('_', ' ').toUpperCase()}
                </span>
              </div>
            </div>

            <div className="prov-claim-body">
              <p className="prov-claim-explanation">{claim.explanation}</p>

              <div className="prov-claim-meta-grid">
                <div className="prov-meta-item">
                  <span className="prov-meta-label">Source:</span>
                  <span className="prov-meta-val">
                    {claim.source}
                    <small className="text-muted"> ({(claim.source_type || '').replaceAll('_', ' ')})</small>
                  </span>
                </div>

                {claim.matched_attribute && (
                  <div className="prov-meta-item">
                    <span className="prov-meta-label">Matched Attribute:</span>
                    <span className="prov-meta-val code-font">{claim.matched_attribute}</span>
                  </div>
                )}

                <div className="prov-meta-item">
                  <span className="prov-meta-label">Retrieved:</span>
                  <span className="prov-meta-val text-muted">
                    {new Date(claim.retrieved_at).toLocaleString()}
                  </span>
                </div>

                {claim.source_url && (
                  <div className="prov-meta-item">
                    <span className="prov-meta-label">Source Record:</span>
                    <a
                      href={claim.source_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="prov-source-link"
                    >
                      <ExternalLink size={12} /> View Official Source
                    </a>
                  </div>
                )}
              </div>

              {showTechnical && isStaff && (
                <div className="prov-technical-box">
                  <div className="prov-tech-row">
                    <span>Evidence ID:</span>
                    <code className="prov-hash">{claim.evidence_id}</code>
                  </div>
                  <div className="prov-tech-row">
                    <span>Fingerprint (SHA-256):</span>
                    <code className="prov-hash">{claim.evidence_hash}</code>
                  </div>
                  <div className="prov-tech-row">
                    <span>Version:</span>
                    <span>v{claim.version} ({claim.status})</span>
                  </div>
                </div>
              )}
            </div>
          </div>
        ))}
      </div>

      <div className="prov-footer-box">
        <small className="text-muted">
          ⚖️ Epistemological Notice: Provenance establishes traceability of system claims to underlying data sources; it does not replace statutory ground inspection. Environmental observations are contextual and do not establish causation.
        </small>
      </div>
    </div>
  );
}
