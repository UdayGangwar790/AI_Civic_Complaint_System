import { useEffect, useState } from 'react';
import {
  AlertCircle,
  AlertTriangle,
  Building2,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Clock,
  History,
  LoaderCircle,
  RefreshCw,
  Send,
  Shield,
  TrendingUp,
} from 'lucide-react';
import {
  evaluateCaseEscalation,
  getCaseEscalation,
  getCaseEscalationHistory,
  getCaseGovernmentReferences,
  getCaseGovernmentSubmission,
  getCaseTimelineAnalytics,
  getGovernmentAnalyticsSummary,
  getGovernmentIntegrations,
  getGovernmentStatusHistory,
  getLatestResolutionVerification,
  getResolutionVerificationHistory,
  reconcileGovernmentSubmission,
  submitGovernmentCase,
  submitResolutionVerification,
  syncGovernmentStatus,
  triggerGovernmentStatusSync,
} from '../services/governmentIntegrationApi';

export function GovernmentIntegrationPanel({
  referenceId,
  isStaff = false,
  onStateChange = null,
}) {
  const [summary, setSummary] = useState(null);
  const [references, setReferences] = useState([]);
  const [statusData, setStatusData] = useState(null);
  const [statusHistory, setStatusHistory] = useState([]);
  const [showStatusHistory, setShowStatusHistory] = useState(false);
  const [escalationData, setEscalationData] = useState(null);
  const [escalationHistory, setEscalationHistory] = useState([]);
  const [showEscalationHistory, setShowEscalationHistory] = useState(false);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [escalating, setEscalating] = useState(false);
  const [verificationData, setVerificationData] = useState(null);
  const [verificationHistory, setVerificationHistory] = useState([]);
  const [showVerifHistory, setShowVerifHistory] = useState(false);
  const [verifSubmitting, setVerifSubmitting] = useState(false);
  const [verifResponse, setVerifResponse] = useState('CONFIRMED_RESOLVED');
  const [verifNotes, setVerifNotes] = useState('');
  const [verifPhotoUrl, setVerifPhotoUrl] = useState('');
  const [analyticsData, setAnalyticsData] = useState(null);
  const [showAnalytics, setShowAnalytics] = useState(false);
  const [timelineData, setTimelineData] = useState(null);
  const [showTimeline, setShowTimeline] = useState(false);
  const [error, setError] = useState(null);
  const [actionMsg, setActionMsg] = useState(null);
  const [integrationsList, setIntegrationsList] = useState([]);
  const [showIntegrationsRegistry, setShowIntegrationsRegistry] = useState(false);

  const fetchSummary = (refId) => {
    setLoading(true);
    setError(null);
    getCaseGovernmentSubmission(refId)
      .then((data) => {
        setSummary(data);
        setLoading(false);
      })
      .catch((err) => {
        setError(err?.message || 'Failed to fetch government submission summary.');
        setLoading(false);
      });

    getCaseGovernmentReferences(refId)
      .then((data) => {
        setReferences(data.mappings || []);
      })
      .catch(() => {
        setReferences([]);
      });

    syncGovernmentStatus(refId)
      .then((data) => {
        setStatusData(data);
      })
      .catch(() => {
        setStatusData(null);
      });

    getCaseEscalation(refId)
      .then((data) => {
        setEscalationData(data);
      })
      .catch(() => {
        setEscalationData(null);
      });

    getLatestResolutionVerification(refId)
      .then((data) => {
        setVerificationData(data);
      })
      .catch(() => {
        setVerificationData(null);
      });
  };

  useEffect(() => {
    if (referenceId) {
      fetchSummary(referenceId);
    }
  }, [referenceId]);

  const handleFetchRegistry = () => {
    if (integrationsList.length > 0) {
      setShowIntegrationsRegistry(!showIntegrationsRegistry);
      return;
    }
    getGovernmentIntegrations()
      .then((res) => {
        setIntegrationsList(res.integrations || []);
        setShowIntegrationsRegistry(true);
      })
      .catch((err) => {
        setError(err?.message || 'Could not load registry.');
      });
  };

  const handleSubmit = async () => {
    setActionLoading(true);
    setError(null);
    setActionMsg(null);
    try {
      const res = await submitGovernmentCase(referenceId);
      if (res.success) {
        setActionMsg(res.notice || 'Submission successfully accepted.');
      } else {
        setError(res.notice || res.error_message_safe || 'Submission failed.');
      }
      fetchSummary(referenceId);
      if (onStateChange) onStateChange();
    } catch (err) {
      setError(err?.message || 'Failed to submit complaint to government integration.');
    } finally {
      setActionLoading(false);
    }
  };

  const handleReconcile = async () => {
    setActionLoading(true);
    setError(null);
    setActionMsg(null);
    try {
      const res = await reconcileGovernmentSubmission(referenceId);
      setActionMsg(res.explanation || 'Reconciliation process completed.');
      fetchSummary(referenceId);
      if (onStateChange) onStateChange();
    } catch (err) {
      setError(err?.message || 'Reconciliation failed.');
    } finally {
      setActionLoading(false);
    }
  };

  const handleSyncStatus = async () => {
    setActionLoading(true);
    setError(null);
    setActionMsg(null);
    try {
      const res = await triggerGovernmentStatusSync(referenceId);
      if (res.success) {
        setActionMsg(res.notice || 'Status synchronized successfully.');
        setStatusData(res);
      } else {
        setError(res.notice || res.error || 'Failed to synchronize external status.');
      }
      fetchSummary(referenceId);
      if (onStateChange) onStateChange();
    } catch (err) {
      setError(err?.message || 'Status check failed.');
    } finally {
      setActionLoading(false);
    }
  };

  const handleEvaluateEscalation = async () => {
    setEscalating(true);
    setError(null);
    setActionMsg(null);
    try {
      const res = await evaluateCaseEscalation(referenceId);
      setEscalationData(res);
      setActionMsg(`Escalation evaluated: Decision [${res.decision}] (${res.reason_code})`);
      if (onStateChange) onStateChange();
    } catch (err) {
      setError(err?.message || 'Failed to evaluate case escalation.');
    } finally {
      setEscalating(false);
    }
  };

  const toggleStatusHistory = async () => {
    if (!showStatusHistory && statusHistory.length === 0) {
      try {
        const hist = await getGovernmentStatusHistory(referenceId);
        setStatusHistory(hist.records || []);
      } catch (err) {
        console.error('Failed to load status history:', err);
      }
    }
    setShowStatusHistory(!showStatusHistory);
  };

  const toggleEscalationHistory = async () => {
    if (!showEscalationHistory && escalationHistory.length === 0) {
      try {
        const hist = await getCaseEscalationHistory(referenceId);
        setEscalationHistory(hist.decisions || []);
      } catch (err) {
        console.error('Failed to load escalation history:', err);
      }
    }
    setShowEscalationHistory(!showEscalationHistory);
  };

  if (loading) {
    return (
      <div className="gov-integration-card loading-state" style={{ padding: '16px', textAlign: 'center' }}>
        <LoaderCircle size={20} className="spin" style={{ margin: '0 auto 8px' }} />
        <p style={{ fontSize: '12px', color: 'var(--muted)' }}>Loading government integration status...</p>
      </div>
    );
  }

  const isNotConfigured = !summary || summary.integration_state === 'NOT_CONFIGURED' || summary.integration_state === 'UNAVAILABLE' || summary.integration_state === 'DISABLED';
  const isStaging = summary?.integration_state === 'CONFIGURED_STAGING';
  const isProduction = summary?.integration_state === 'CONFIGURED_PRODUCTION';
  const isUnknown = summary?.submission_state === 'UNKNOWN_OUTCOME' || summary?.reconciliation_required;
  const isSubmitted = summary?.submission_state === 'SUBMITTED' || summary?.submission_state === 'COMPLETED';

  return (
    <div className="gov-integration-card" style={{
      border: '1px solid var(--border)',
      borderRadius: '8px',
      padding: '16px',
      background: 'var(--card-bg, #ffffff)',
      marginTop: '16px',
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Building2 size={18} style={{ color: 'var(--accent, #1e40af)' }} />
          <h4 style={{ margin: 0, fontSize: '14px', fontWeight: 600 }}>Government Integration Layer</h4>
        </div>
        <button
          type="button"
          onClick={() => fetchSummary(referenceId)}
          title="Refresh Integration State"
          style={{ background: 'transparent', border: 'none', cursor: 'pointer', padding: '4px' }}
        >
          <RefreshCw size={14} className={actionLoading ? 'spin' : ''} />
        </button>
      </div>

      {error && (
        <div style={{
          padding: '8px 12px',
          background: 'rgba(239, 68, 68, 0.1)',
          borderLeft: '3px solid var(--error, #ef4444)',
          borderRadius: '4px',
          marginBottom: '12px',
          fontSize: '12px',
          color: 'var(--error, #b91c1c)',
        }}>
          <strong>Error:</strong> {error}
        </div>
      )}

      {actionMsg && (
        <div style={{
          padding: '8px 12px',
          background: 'rgba(34, 197, 94, 0.1)',
          borderLeft: '3px solid var(--success, #22c55e)',
          borderRadius: '4px',
          marginBottom: '12px',
          fontSize: '12px',
          color: 'var(--forest, #15803d)',
        }}>
          {actionMsg}
        </div>
      )}

      {/* State & Authority Badges */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', marginBottom: '12px' }}>
        <span style={{
          fontSize: '11px',
          fontWeight: 600,
          padding: '3px 8px',
          borderRadius: '12px',
          background: isNotConfigured
            ? 'rgba(100, 116, 139, 0.15)'
            : isUnknown
            ? 'rgba(234, 179, 8, 0.15)'
            : isSubmitted
            ? 'rgba(34, 197, 94, 0.15)'
            : isStaging
            ? 'rgba(168, 85, 247, 0.15)'
            : 'rgba(59, 130, 246, 0.15)',
          color: isNotConfigured
            ? '#475569'
            : isUnknown
            ? '#b45309'
            : isSubmitted
            ? '#15803d'
            : isStaging
            ? '#7e22ce'
            : '#1d4ed8',
          display: 'inline-flex',
          alignItems: 'center',
          gap: '4px',
        }}>
          {isNotConfigured ? (
            <AlertCircle size={12} />
          ) : isUnknown ? (
            <AlertTriangle size={12} />
          ) : isSubmitted ? (
            <CheckCircle2 size={12} />
          ) : (
            <Shield size={12} />
          )}
          {summary?.integration_name ? `${summary.integration_name}: ` : ''}
          {isNotConfigured ? 'NOT CONFIGURED' : isStaging ? 'CONFIGURED (STAGING)' : isProduction ? 'CONFIGURED (PRODUCTION)' : summary?.submission_state || 'READY'}
        </span>

        {summary?.authority && (
          <span style={{
            fontSize: '11px',
            padding: '3px 8px',
            borderRadius: '12px',
            background: 'var(--badge-bg, #f1f5f9)',
            color: 'var(--foreground, #334155)',
          }}>
            Target Authority: {summary.authority}
          </span>
        )}
      </div>

      {/* Primary Explicit Truthfulness Copy */}
      <div style={{
        padding: '12px',
        borderRadius: '6px',
        background: isNotConfigured
          ? 'rgba(241, 245, 249, 0.7)'
          : isUnknown
          ? 'rgba(254, 243, 199, 0.6)'
          : 'rgba(240, 253, 244, 0.6)',
        border: isNotConfigured
          ? '1px solid rgba(203, 213, 225, 0.5)'
          : isUnknown
          ? '1px solid rgba(245, 158, 11, 0.3)'
          : '1px solid rgba(34, 197, 94, 0.3)',
        marginBottom: '12px',
      }}>
        <p style={{ margin: 0, fontSize: '12px', lineHeight: 1.5, color: '#1e293b' }}>
          {isNotConfigured && <strong>Government portal integration is not configured. </strong>}
          {summary?.notice}
        </p>
        {summary?.diagnostic_message && summary.diagnostic_message !== summary.notice && (
          <p style={{ margin: '6px 0 0', fontSize: '11px', lineHeight: 1.4, color: '#64748b', fontStyle: 'italic' }}>
            Diagnostic: {summary.diagnostic_message}
          </p>
        )}
      </div>

      {/* Grid Attributes */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
        gap: '8px',
        fontSize: '12px',
        marginBottom: '12px',
      }}>
        <div>
          <span style={{ color: 'var(--muted, #64748b)' }}>External Reference ID: </span>
          <strong>{summary?.external_reference_id || 'None (Unsubmitted)'}</strong>
        </div>

        <div>
          <span style={{ color: 'var(--muted, #64748b)' }}>Government Status: </span>
          <strong>
            {summary?.normalized_status
              ? `${summary.normalized_status} (${summary.external_status || 'raw'})`
              : 'Not Synchronized'}
          </strong>
        </div>

        {summary?.submitted_at && (
          <div>
            <span style={{ color: 'var(--muted, #64748b)' }}>Submitted At: </span>
            <strong>{new Date(summary.submitted_at).toLocaleString()}</strong>
          </div>
        )}

        {summary?.last_status_sync_at && (
          <div>
            <span style={{ color: 'var(--muted, #64748b)' }}>Last Synchronized: </span>
            <strong>{new Date(summary.last_status_sync_at).toLocaleString()}</strong>
          </div>
        )}
      </div>

      {/* M7.3 Government Reference-ID Mapping Section */}
      <div style={{
        marginTop: '12px',
        marginBottom: '14px',
        padding: '12px',
        background: '#ffffff',
        borderRadius: '6px',
        border: '1px solid #e2e8f0',
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
          <h5 style={{ margin: 0, fontSize: '12px', fontWeight: 700, color: '#1e293b' }}>
            Government Reference-ID Mapping (M7.3)
          </h5>
          <span style={{ fontSize: '11px', color: '#64748b' }}>
            CVKI Case Reference: <strong>{referenceId}</strong>
          </span>
        </div>
        <p style={{ margin: '0 0 10px', fontSize: '11px', color: '#64748b' }}>
          Strict separation of identities: CVKI reference IDs are immutable and are never replaced by external government docket numbers.
        </p>

        {references.length === 0 ? (
          <div style={{ padding: '8px', background: '#f8fafc', borderRadius: '4px', fontSize: '11px', color: '#64748b' }}>
            No external government reference mappings recorded yet for this case.
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {references.map((m) => {
              const isConfirmed = m.mapping_state === 'REFERENCE_CONFIRMED';
              const isConflict = m.conflict_detected || m.mapping_state === 'REFERENCE_CONFLICT';
              const isUnknownMap = m.mapping_state === 'UNKNOWN_OUTCOME';
              const isManual = m.mapping_state === 'UNVERIFIED_MANUAL_REFERENCE';

              return (
                <div key={m.mapping_id} style={{
                  padding: '10px',
                  borderRadius: '6px',
                  background: isConflict ? '#fef2f2' : isConfirmed ? '#f0fdf4' : '#f8fafc',
                  border: isConflict ? '1px solid #fca5a5' : isConfirmed ? '1px solid #bbf7d0' : '1px solid #e2e8f0',
                  fontSize: '11px',
                }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '6px' }}>
                    <span style={{ fontWeight: 600, color: '#334155' }}>
                      {m.integration_display_name}
                    </span>
                    <div style={{ display: 'flex', gap: '6px' }}>
                      <span style={{
                        padding: '2px 7px',
                        borderRadius: '10px',
                        fontSize: '10px',
                        fontWeight: 600,
                        background: isConflict
                          ? 'rgba(239, 68, 68, 0.15)'
                          : isConfirmed
                          ? 'rgba(34, 197, 94, 0.15)'
                          : isUnknownMap
                          ? 'rgba(234, 179, 8, 0.15)'
                          : isManual
                          ? 'rgba(168, 85, 247, 0.15)'
                          : 'rgba(100, 116, 139, 0.15)',
                        color: isConflict
                          ? '#b91c1c'
                          : isConfirmed
                          ? '#15803d'
                          : isUnknownMap
                          ? '#b45309'
                          : isManual
                          ? '#7e22ce'
                          : '#475569',
                      }}>
                        {m.mapping_state}
                      </span>
                      <span style={{
                        padding: '2px 7px',
                        borderRadius: '10px',
                        fontSize: '10px',
                        background: m.verification_state === 'verified' ? '#dcfce7' : '#f1f5f9',
                        color: m.verification_state === 'verified' ? '#166534' : '#475569',
                      }}>
                        {m.verification_state.toUpperCase()}
                      </span>
                    </div>
                  </div>

                  <div style={{ marginTop: '6px', display: 'flex', gap: '16px', flexWrap: 'wrap' }}>
                    <div>
                      <span style={{ color: '#64748b' }}>External Tracking ID: </span>
                      <strong style={{ color: isConfirmed ? '#166534' : '#1e293b' }}>
                        {m.government_reference_id || 'None (Unassigned)'}
                      </strong>
                    </div>
                    {m.first_observed_at && (
                      <div>
                        <span style={{ color: '#64748b' }}>First Seen: </span>
                        <span>{new Date(m.first_observed_at).toLocaleString()}</span>
                      </div>
                    )}
                    {m.last_confirmed_at && (
                      <div>
                        <span style={{ color: '#64748b' }}>Last Confirmed: </span>
                        <span>{new Date(m.last_confirmed_at).toLocaleString()}</span>
                      </div>
                    )}
                  </div>

                  {m.explanation && (
                    <div style={{ marginTop: '4px', color: isConflict ? '#991b1b' : '#64748b', fontStyle: 'italic' }}>
                      {m.explanation}
                    </div>
                  )}

                  {isConflict && (
                    <div style={{
                      marginTop: '6px',
                      padding: '6px',
                      borderRadius: '4px',
                      background: 'rgba(239, 68, 68, 0.1)',
                      color: '#b91c1c',
                      fontWeight: 600,
                      display: 'flex',
                      alignItems: 'center',
                      gap: '4px',
                    }}>
                      <AlertTriangle size={12} />
                      Warning: Identity conflict detected. This reference is not marked as confirmed.
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* M7.4 Government Status Synchronization Card */}
      <div style={{
        marginTop: '12px',
        marginBottom: '14px',
        padding: '12px',
        background: '#ffffff',
        borderRadius: '6px',
        border: '1px solid #e2e8f0',
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <RefreshCw size={14} style={{ color: '#2563eb' }} />
            <h5 style={{ margin: 0, fontSize: '12px', fontWeight: 700, color: '#1e293b' }}>
              Government Status Synchronization (M7.4)
            </h5>
          </div>
          <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
            <span style={{
              fontSize: '10px',
              fontWeight: 600,
              padding: '2px 7px',
              borderRadius: '10px',
              background: (statusData?.freshness === 'FRESH' || (!statusData && summary?.normalized_status))
                ? 'rgba(34, 197, 94, 0.15)'
                : statusData?.freshness === 'STALE'
                ? 'rgba(234, 179, 8, 0.15)'
                : 'rgba(100, 116, 139, 0.15)',
              color: (statusData?.freshness === 'FRESH' || (!statusData && summary?.normalized_status))
                ? '#15803d'
                : statusData?.freshness === 'STALE'
                ? '#b45309'
                : '#475569',
            }}>
              {statusData?.freshness || 'FRESH'}
            </span>
            <button
              type="button"
              onClick={toggleStatusHistory}
              style={{
                background: 'transparent',
                border: '1px solid #cbd5e1',
                borderRadius: '4px',
                padding: '2px 6px',
                fontSize: '11px',
                color: '#475569',
                cursor: 'pointer',
                display: 'inline-flex',
                alignItems: 'center',
                gap: '4px',
              }}
            >
              <History size={11} />
              {showStatusHistory ? 'Hide History' : 'Status History'}
              {showStatusHistory ? <ChevronUp size={11} /> : <ChevronDown size={11} />}
            </button>
          </div>
        </div>

        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
          gap: '8px',
          fontSize: '11px',
          background: '#f8fafc',
          padding: '8px',
          borderRadius: '4px',
        }}>
          <div>
            <span style={{ color: '#64748b' }}>Normalized Status: </span>
            <strong style={{ color: '#1e293b' }}>
              {(statusData?.normalized_status || summary?.normalized_status || 'UNKNOWN').toUpperCase()}
            </strong>
          </div>
          <div>
            <span style={{ color: '#64748b' }}>Raw Upstream Status: </span>
            <span style={{ fontStyle: 'italic' }}>
              {statusData?.latest_raw_status || summary?.external_status || 'None'}
            </span>
          </div>
          <div>
            <span style={{ color: '#64748b' }}>Last Checked: </span>
            <span>
              {statusData?.last_checked_at
                ? new Date(statusData.last_checked_at).toLocaleTimeString()
                : (summary?.last_status_sync_at ? new Date(summary.last_status_sync_at).toLocaleTimeString() : 'Not checked')}
            </span>
          </div>
          <div>
            <span style={{ color: '#64748b' }}>Sync State: </span>
            <span style={{ fontWeight: 600 }}>
              {statusData?.synchronization_state || (summary?.submission_state === 'SUBMITTED' ? 'SYNCED' : 'PENDING')}
            </span>
          </div>
        </div>

        {/* Expandable Status Observation History */}
        {showStatusHistory && (
          <div style={{ marginTop: '10px', paddingTop: '8px', borderTop: '1px solid #e2e8f0' }}>
            <span style={{ fontSize: '11px', fontWeight: 600, color: '#334155', display: 'block', marginBottom: '6px' }}>
              Append-Oriented Status History:
            </span>
            {statusHistory.length === 0 ? (
              <p style={{ margin: 0, fontSize: '11px', color: '#64748b' }}>No historical status transitions recorded yet.</p>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                {statusHistory.map((h) => (
                  <div key={h.sync_id} style={{
                    padding: '6px 8px',
                    borderRadius: '4px',
                    background: '#f1f5f9',
                    fontSize: '11px',
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    flexWrap: 'wrap',
                    gap: '4px',
                  }}>
                    <div>
                      <strong>{(h.normalized_external_status || 'UNKNOWN').toUpperCase()}</strong>
                      <span style={{ color: '#64748b', marginLeft: '6px' }}>
                        (Raw: '{h.raw_external_status || 'none'}')
                      </span>
                    </div>
                    <div style={{ color: '#64748b', fontSize: '10px' }}>
                      Seen: {new Date(h.first_seen_at).toLocaleString()}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* M7.5 Evidence-Based Escalation Engine Card */}
      <div style={{
        marginTop: '12px',
        marginBottom: '14px',
        padding: '12px',
        background: '#ffffff',
        borderRadius: '6px',
        border: '1px solid #e2e8f0',
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <TrendingUp size={14} style={{ color: '#ea580c' }} />
            <h5 style={{ margin: 0, fontSize: '12px', fontWeight: 700, color: '#1e293b' }}>
              Evidence-Based Escalation Engine (M7.5)
            </h5>
          </div>
          <span style={{
            fontSize: '9px',
            fontWeight: 700,
            padding: '2px 6px',
            borderRadius: '4px',
            background: '#f1f5f9',
            color: '#64748b',
            letterSpacing: '0.3px',
          }}>
            CONFIGURABLE POLICY
          </span>
        </div>

        <p style={{ margin: '0 0 10px', fontSize: '11px', color: '#64748b' }}>
          Deterministic, policy-driven evaluation linking verified government docket status, status age, and evidentiary provenance.
        </p>

        {/* Escalation Evaluation Summary */}
        <div style={{
          padding: '10px',
          borderRadius: '6px',
          background: escalationData?.decision === 'ESCALATE'
            ? 'rgba(239, 68, 68, 0.08)'
            : escalationData?.decision === 'FOLLOW_UP'
            ? 'rgba(234, 179, 8, 0.08)'
            : escalationData?.decision === 'ACTION_REQUIRED'
            ? 'rgba(168, 85, 247, 0.08)'
            : '#f8fafc',
          border: escalationData?.decision === 'ESCALATE'
            ? '1px solid rgba(239, 68, 68, 0.25)'
            : escalationData?.decision === 'FOLLOW_UP'
            ? '1px solid rgba(234, 179, 8, 0.25)'
            : escalationData?.decision === 'ACTION_REQUIRED'
            ? '1px solid rgba(168, 85, 247, 0.25)'
            : '1px solid #e2e8f0',
          fontSize: '11px',
          marginBottom: '10px',
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '6px', marginBottom: '6px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <span style={{
                fontWeight: 700,
                fontSize: '11px',
                padding: '2px 8px',
                borderRadius: '10px',
                background: escalationData?.decision === 'ESCALATE'
                  ? '#fee2e2'
                  : escalationData?.decision === 'FOLLOW_UP'
                  ? '#fef3c7'
                  : escalationData?.decision === 'ACTION_REQUIRED'
                  ? '#f3e8ff'
                  : '#e2e8f0',
                color: escalationData?.decision === 'ESCALATE'
                  ? '#b91c1c'
                  : escalationData?.decision === 'FOLLOW_UP'
                  ? '#b45309'
                  : escalationData?.decision === 'ACTION_REQUIRED'
                  ? '#7e22ce'
                  : '#475569',
              }}>
                {escalationData?.decision ? `DECISION: ${escalationData.decision}` : 'NOT EVALUATED'}
              </span>
              {escalationData?.escalation_level && escalationData.escalation_level !== 'NONE' && (
                <span style={{ fontSize: '10px', color: '#64748b' }}>
                  Level: <strong>{escalationData.escalation_level}</strong>
                </span>
              )}
            </div>

            <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
              {escalationData?.is_in_cooldown && (
                <span style={{
                  fontSize: '10px',
                  fontWeight: 600,
                  padding: '2px 6px',
                  borderRadius: '10px',
                  background: '#fef3c7',
                  color: '#b45309',
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '3px',
                }}>
                  <Clock size={10} /> Cooldown Active
                </span>
              )}
              <span style={{ fontSize: '10px', color: '#64748b' }}>
                Reason: <strong>{escalationData?.reason_code || 'Awaiting Evaluation'}</strong>
              </span>
            </div>
          </div>

          <div style={{ color: '#1e293b', marginBottom: '6px', lineHeight: 1.4 }}>
            {escalationData?.explanation || 'Click "Evaluate Escalation" to run deterministic policy checks against this case.'}
          </div>

          {escalationData?.recommended_action && (
            <div style={{
              padding: '6px 8px',
              borderRadius: '4px',
              background: '#ffffff',
              border: '1px solid #cbd5e1',
              color: '#334155',
              fontSize: '11px',
            }}>
              <strong>Recommended Action: </strong>
              {escalationData.recommended_action}
            </div>
          )}

          {escalationData?.status_age_hours !== undefined && escalationData?.status_age_hours !== null && (
            <div style={{ marginTop: '6px', fontSize: '10px', color: '#64748b' }}>
              External Status Age: <strong>{escalationData.status_age_hours.toFixed(1)} hours</strong>
              {escalationData?.policy_id && ` | Matched Policy: ${escalationData.policy_id}`}
            </div>
          )}
        </div>

        <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', alignItems: 'center' }}>
          <button
            type="button"
            onClick={handleEvaluateEscalation}
            disabled={escalating}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              fontSize: '11px',
              padding: '5px 10px',
              borderRadius: '4px',
              background: '#ea580c',
              color: '#ffffff',
              border: 'none',
              cursor: escalating ? 'not-allowed' : 'pointer',
              fontWeight: 600,
            }}
          >
            <TrendingUp size={12} className={escalating ? 'spin' : ''} />
            {escalating ? 'Evaluating Policy...' : 'Evaluate Escalation'}
          </button>

          <button
            type="button"
            onClick={toggleEscalationHistory}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '4px',
              fontSize: '11px',
              padding: '4px 8px',
              borderRadius: '4px',
              background: 'transparent',
              border: '1px solid #cbd5e1',
              color: '#475569',
              cursor: 'pointer',
            }}
          >
            <History size={11} />
            {showEscalationHistory ? 'Hide Decision History' : 'Decision History'}
            {showEscalationHistory ? <ChevronUp size={11} /> : <ChevronDown size={11} />}
          </button>
        </div>

        {/* Expandable Escalation Decision History */}
        {showEscalationHistory && (
          <div style={{ marginTop: '10px', paddingTop: '8px', borderTop: '1px solid #e2e8f0' }}>
            <span style={{ fontSize: '11px', fontWeight: 600, color: '#334155', display: 'block', marginBottom: '6px' }}>
              Past Escalation Evaluations:
            </span>
            {escalationHistory.length === 0 ? (
              <p style={{ margin: 0, fontSize: '11px', color: '#64748b' }}>No prior escalation evaluations recorded for this case.</p>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                {escalationHistory.map((d) => (
                  <div key={d.decision_id} style={{
                    padding: '6px 8px',
                    borderRadius: '4px',
                    background: '#f8fafc',
                    border: '1px solid #e2e8f0',
                    fontSize: '11px',
                  }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '3px' }}>
                      <strong>{d.decision} ({d.reason_code})</strong>
                      <span style={{ fontSize: '10px', color: '#64748b' }}>
                        {new Date(d.evaluated_at).toLocaleString()}
                      </span>
                    </div>
                    <div style={{ fontSize: '10px', color: '#475569' }}>
                      {d.explanation}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* M7.6 Citizen Resolution Verification Card */}
      <div style={{
        marginTop: '12px',
        padding: '12px',
        background: '#ffffff',
        borderRadius: '6px',
        border: '1px solid #e2e8f0',
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <CheckCircle2 size={16} color="#059669" />
            <h5 style={{ margin: 0, fontSize: '13px', fontWeight: 600 }}>Citizen Resolution Verification (M7.6)</h5>
          </div>
          <span style={{
            fontSize: '11px',
            fontWeight: 600,
            padding: '2px 8px',
            borderRadius: '4px',
            background: verificationData?.verification_status === 'VERIFIED_RESOLVED'
              ? 'rgba(16, 185, 129, 0.15)'
              : verificationData?.verification_status === 'CITIZEN_DISPUTED'
              ? 'rgba(239, 68, 68, 0.15)'
              : 'rgba(100, 116, 139, 0.15)',
            color: verificationData?.verification_status === 'VERIFIED_RESOLVED'
              ? '#059669'
              : verificationData?.verification_status === 'CITIZEN_DISPUTED'
              ? '#dc2626'
              : '#475569',
          }}>
            {verificationData?.verification_status || 'NOT YET VERIFIED'}
          </span>
        </div>

        <p style={{ margin: '0 0 10px', fontSize: '11px', color: '#64748b' }}>
          External portal status &apos;RESOLVED&apos; is an observed claim. Physical resolution requires verified citizen feedback.
        </p>

        {verificationData ? (
          <div style={{
            padding: '8px 10px',
            borderRadius: '4px',
            background: '#f8fafc',
            border: '1px solid #e2e8f0',
            fontSize: '11px',
            marginBottom: '10px',
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
              <span><strong>Citizen Response:</strong> {verificationData.citizen_response}</span>
              <span style={{ color: '#64748b', fontSize: '10px' }}>
                {new Date(verificationData.submitted_at).toLocaleString()}
              </span>
            </div>
            {verificationData.citizen_notes && (
              <div style={{ color: '#334155', fontStyle: 'italic', marginBottom: '4px' }}>
                &ldquo;{verificationData.citizen_notes}&rdquo;
              </div>
            )}
            <div style={{ fontSize: '10px', color: '#64748b' }}>
              Physical Resolution Ground Truth: {verificationData.is_physical_resolution_verified ? 'CONFIRMED' : 'UNCONFIRMED / DISPUTED'}
            </div>
          </div>
        ) : null}

        {/* Verification Submission Form */}
        <div style={{
          padding: '10px',
          background: '#f8fafc',
          borderRadius: '4px',
          border: '1px dashed #cbd5e1',
          marginBottom: '8px',
        }}>
          <span style={{ fontSize: '11px', fontWeight: 600, color: '#334155', display: 'block', marginBottom: '6px' }}>
            Submit Ground Truth Verification:
          </span>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', marginBottom: '6px' }}>
            <select
              value={verifResponse}
              onChange={(e) => setVerifResponse(e.target.value)}
              style={{
                fontSize: '11px',
                padding: '4px 8px',
                borderRadius: '4px',
                border: '1px solid #cbd5e1',
                background: '#ffffff',
              }}
            >
              <option value="CONFIRMED_RESOLVED">Confirm Resolved (Defect Repaired)</option>
              <option value="STILL_UNRESOLVED">Dispute (Still Unresolved)</option>
              <option value="PARTIALLY_RESOLVED">Partially Resolved (Incomplete Work)</option>
              <option value="CANNOT_VERIFY">Cannot Verify (Inaccessible / Unsure)</option>
            </select>
            <input
              type="text"
              placeholder="Optional observations on repair..."
              value={verifNotes}
              onChange={(e) => setVerifNotes(e.target.value)}
              style={{
                flex: 1,
                fontSize: '11px',
                padding: '4px 8px',
                borderRadius: '4px',
                border: '1px solid #cbd5e1',
                minWidth: '150px',
              }}
            />
            <input
              type="text"
              placeholder="Evidence photo URL (optional)..."
              value={verifPhotoUrl}
              onChange={(e) => setVerifPhotoUrl(e.target.value)}
              style={{
                flex: 1,
                fontSize: '11px',
                padding: '4px 8px',
                borderRadius: '4px',
                border: '1px solid #cbd5e1',
                minWidth: '150px',
              }}
            />
          </div>
          <button
            type="button"
            disabled={verifSubmitting}
            onClick={async () => {
              setVerifSubmitting(true);
              try {
                const res = await submitResolutionVerification(referenceId, {
                  citizen_response: verifResponse,
                  citizen_notes: verifNotes || null,
                  evidence_photo_url: verifPhotoUrl || null,
                });
                setVerificationData(res);
                setActionMsg(`Verification recorded: ${res.verification_status}.`);
                setVerifNotes('');
                setVerifPhotoUrl('');
              } catch (err) {
                setError(err?.message || 'Verification submission failed.');
              } finally {
                setVerifSubmitting(false);
              }
            }}
            style={{
              fontSize: '11px',
              padding: '4px 10px',
              borderRadius: '4px',
              background: '#059669',
              color: '#ffffff',
              border: 'none',
              cursor: verifSubmitting ? 'not-allowed' : 'pointer',
              fontWeight: 600,
            }}
          >
            {verifSubmitting ? 'Submitting...' : 'Submit Resolution Feedback'}
          </button>
        </div>

        <button
          type="button"
          onClick={() => {
            if (!showVerifHistory) {
              getResolutionVerificationHistory(referenceId)
                .then((res) => setVerificationHistory(res.verifications || []))
                .catch(() => setVerificationHistory([]));
            }
            setShowVerifHistory(!showVerifHistory);
          }}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '4px',
            fontSize: '11px',
            padding: '3px 8px',
            borderRadius: '4px',
            background: 'transparent',
            border: '1px solid #cbd5e1',
            color: '#475569',
            cursor: 'pointer',
          }}
        >
          <History size={11} />
          {showVerifHistory ? 'Hide Verification History' : 'Verification History'}
          {showVerifHistory ? <ChevronUp size={11} /> : <ChevronDown size={11} />}
        </button>

        {showVerifHistory && (
          <div style={{ marginTop: '8px', paddingTop: '6px', borderTop: '1px solid #e2e8f0' }}>
            {verificationHistory.length === 0 ? (
              <p style={{ margin: 0, fontSize: '10px', color: '#64748b' }}>No prior verification submissions recorded.</p>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                {verificationHistory.map((v) => (
                  <div key={v.verification_id} style={{
                    padding: '4px 6px',
                    borderRadius: '3px',
                    background: '#f8fafc',
                    border: '1px solid #e2e8f0',
                    fontSize: '10px',
                  }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                      <strong>{v.citizen_response} ➔ {v.verification_status}</strong>
                      <span style={{ color: '#64748b' }}>{new Date(v.submitted_at).toLocaleString()}</span>
                    </div>
                    {v.citizen_notes && <div style={{ color: '#475569' }}>{v.citizen_notes}</div>}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* M7.7 Government Response Analytics & Case Timeline Drawer */}
      <div style={{
        marginTop: '12px',
        display: 'flex',
        flexWrap: 'wrap',
        gap: '8px',
      }}>
        <button
          type="button"
          onClick={() => {
            if (!showTimeline) {
              getCaseTimelineAnalytics(referenceId)
                .then((res) => setTimelineData(res))
                .catch((err) => setError(err?.message || 'Could not load timeline.'));
            }
            setShowTimeline(!showTimeline);
          }}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '6px',
            fontSize: '11px',
            padding: '5px 10px',
            borderRadius: '4px',
            background: 'transparent',
            border: '1px solid #94a3b8',
            color: '#334155',
            cursor: 'pointer',
            fontWeight: 500,
          }}
        >
          <Clock size={12} />
          {showTimeline ? 'Hide Case Timeline' : 'Inspect Case Lifecycle Timeline (M7.7)'}
          {showTimeline ? <ChevronUp size={11} /> : <ChevronDown size={11} />}
        </button>

        {isStaff && (
          <button
            type="button"
            onClick={() => {
              if (!showAnalytics) {
                getGovernmentAnalyticsSummary()
                  .then((res) => setAnalyticsData(res))
                  .catch((err) => setError(err?.message || 'Could not load analytics.'));
              }
              setShowAnalytics(!showAnalytics);
            }}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              fontSize: '11px',
              padding: '5px 10px',
              borderRadius: '4px',
              background: '#0284c7',
              color: '#ffffff',
              border: 'none',
              cursor: 'pointer',
              fontWeight: 600,
            }}
          >
            <TrendingUp size={12} />
            {showAnalytics ? 'Hide Government Analytics' : 'Government Response Analytics Dashboard'}
            {showAnalytics ? <ChevronUp size={11} /> : <ChevronDown size={11} />}
          </button>
        )}
      </div>

      {/* Expandable Case Timeline */}
      {showTimeline && timelineData && (
        <div style={{
          marginTop: '10px',
          padding: '10px',
          background: '#f8fafc',
          borderRadius: '6px',
          border: '1px solid #cbd5e1',
          fontSize: '11px',
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
            <strong>Case Lifecycle Timeline: {referenceId}</strong>
            <span style={{ color: '#64748b' }}>
              Duration: {timelineData.total_duration_hours !== null ? `${timelineData.total_duration_hours}h` : 'In Progress'}
            </span>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            {timelineData.events.map((evt) => (
              <div key={evt.event_id} style={{
                padding: '6px 8px',
                background: '#ffffff',
                borderRadius: '4px',
                border: '1px solid #e2e8f0',
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontWeight: 600 }}>
                  <span>{evt.label}</span>
                  <span style={{ fontSize: '10px', color: '#64748b' }}>{new Date(evt.timestamp).toLocaleString()}</span>
                </div>
                <div style={{ fontSize: '10px', color: '#64748b' }}>Source: {evt.source}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Expandable Staff Government Analytics Dashboard */}
      {isStaff && showAnalytics && analyticsData && (
        <div style={{
          marginTop: '10px',
          padding: '12px',
          background: '#f0fdf4',
          borderRadius: '6px',
          border: '1px solid #86efac',
          fontSize: '11px',
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
            <h5 style={{ margin: 0, fontSize: '13px', color: '#166534' }}>Government Response Analytics (M7.7)</h5>
            <span style={{
              fontSize: '10px',
              padding: '2px 6px',
              borderRadius: '4px',
              background: '#dcfce7',
              color: '#15803d',
              fontWeight: 600,
            }}>
              SYSTEM-DERIVED • NOT OFFICIAL SLA
            </span>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: '8px', marginBottom: '10px' }}>
            <div style={{ padding: '8px', background: '#ffffff', borderRadius: '4px', border: '1px solid #e2e8f0' }}>
              <span style={{ color: '#64748b', fontSize: '10px' }}>Linked Cases</span>
              <div style={{ fontSize: '16px', fontWeight: 700 }}>{analyticsData.total_government_linked_cases}</div>
            </div>
            <div style={{ padding: '8px', background: '#ffffff', borderRadius: '4px', border: '1px solid #e2e8f0' }}>
              <span style={{ color: '#64748b', fontSize: '10px' }}>Gov Resolved</span>
              <div style={{ fontSize: '16px', fontWeight: 700 }}>{analyticsData.resolution_verification.total_government_resolved_cases}</div>
            </div>
            <div style={{ padding: '8px', background: '#ffffff', borderRadius: '4px', border: '1px solid #e2e8f0' }}>
              <span style={{ color: '#64748b', fontSize: '10px' }}>Citizen Verified</span>
              <div style={{ fontSize: '16px', fontWeight: 700, color: '#15803d' }}>
                {analyticsData.resolution_verification.verified_resolved_count}
              </div>
            </div>
            <div style={{ padding: '8px', background: '#ffffff', borderRadius: '4px', border: '1px solid #e2e8f0' }}>
              <span style={{ color: '#64748b', fontSize: '10px' }}>Citizen Disputed</span>
              <div style={{ fontSize: '16px', fontWeight: 700, color: '#dc2626' }}>
                {analyticsData.resolution_verification.citizen_disputed_count}
              </div>
            </div>
            <div style={{ padding: '8px', background: '#ffffff', borderRadius: '4px', border: '1px solid #e2e8f0' }}>
              <span style={{ color: '#64748b', fontSize: '10px' }}>Dispute Rate</span>
              <div style={{ fontSize: '16px', fontWeight: 700, color: '#b45309' }}>
                {analyticsData.resolution_verification.dispute_rate !== null
                  ? `${(analyticsData.resolution_verification.dispute_rate * 100).toFixed(1)}%`
                  : 'N/A'}
              </div>
            </div>
            <div style={{ padding: '8px', background: '#ffffff', borderRadius: '4px', border: '1px solid #e2e8f0' }}>
              <span style={{ color: '#64748b', fontSize: '10px' }}>Escalations Triggered</span>
              <div style={{ fontSize: '16px', fontWeight: 700, color: '#ea580c' }}>
                {analyticsData.escalation.follow_up_recommended_count + analyticsData.escalation.escalation_recommended_count}
              </div>
            </div>
          </div>
          <div style={{ fontSize: '10px', color: '#64748b', fontStyle: 'italic' }}>
            {analyticsData.epistemic_disclaimer}
          </div>
        </div>
      )}

      {/* Operational Actions */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', marginTop: '12px' }}>
        {!isSubmitted && !isUnknown && (
          <button
            type="button"
            onClick={handleSubmit}
            disabled={actionLoading || isNotConfigured}
            className="btn-primary"
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              fontSize: '12px',
              padding: '6px 12px',
              borderRadius: '6px',
              cursor: (actionLoading || isNotConfigured) ? 'not-allowed' : 'pointer',
              opacity: isNotConfigured ? 0.6 : 1,
            }}
          >
            <Send size={13} />
            {actionLoading ? 'Dispatching...' : 'Submit to Government Integration'}
          </button>
        )}

        {isUnknown && isStaff && (
          <button
            type="button"
            onClick={handleReconcile}
            disabled={actionLoading}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              fontSize: '12px',
              padding: '6px 12px',
              borderRadius: '6px',
              background: '#b45309',
              color: '#ffffff',
              border: 'none',
              cursor: actionLoading ? 'not-allowed' : 'pointer',
            }}
          >
            <RefreshCw size={13} className={actionLoading ? 'spin' : ''} />
            Reconcile Outcome
          </button>
        )}

        {isSubmitted && (
          <button
            type="button"
            onClick={handleSyncStatus}
            disabled={actionLoading}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              fontSize: '12px',
              padding: '6px 12px',
              borderRadius: '6px',
              background: 'transparent',
              border: '1px solid var(--border)',
              cursor: actionLoading ? 'not-allowed' : 'pointer',
            }}
          >
            <RefreshCw size={13} className={actionLoading ? 'spin' : ''} />
            Sync Government Status
          </button>
        )}

        {isStaff && (
          <button
            type="button"
            onClick={handleFetchRegistry}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              fontSize: '12px',
              padding: '6px 12px',
              borderRadius: '6px',
              background: 'transparent',
              border: '1px solid var(--border)',
              cursor: 'pointer',
              marginLeft: 'auto',
            }}
          >
            <Building2 size={13} />
            {showIntegrationsRegistry ? 'Hide Registry' : 'Inspect Registered Integrations'}
          </button>
        )}
      </div>

      {/* Admin Inspection Drawer / Accordion */}
      {isStaff && showIntegrationsRegistry && (
        <div style={{
          marginTop: '16px',
          padding: '12px',
          background: 'var(--badge-bg, #f8fafc)',
          borderRadius: '6px',
          border: '1px solid var(--border)',
        }}>
          <h5 style={{ margin: '0 0 8px', fontSize: '13px' }}>Government Integration Catalog (Admin Inspection)</h5>
          {integrationsList.length === 0 ? (
            <p style={{ fontSize: '11px', color: 'var(--muted)' }}>No integrations registered.</p>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {integrationsList.map((item) => (
                <div key={item.integration_id} style={{
                  padding: '8px',
                  background: '#ffffff',
                  borderRadius: '4px',
                  border: '1px solid #e2e8f0',
                  fontSize: '11px',
                }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <strong>{item.display_name}</strong>
                    <span style={{
                      fontWeight: 600,
                      color: item.configuration_status === 'AVAILABLE' ? '#15803d' : '#64748b',
                    }}>
                      {item.configuration_status}
                    </span>
                  </div>
                  <div style={{ color: '#64748b', marginTop: '2px' }}>
                    Authority: {item.authority} | Domain: {item.official_domain} | Adapter: {item.adapter_type} | Verification: {item.verification_state}
                  </div>
                  {item.diagnostic_message && (
                    <div style={{ color: '#475569', marginTop: '3px', fontStyle: 'italic' }}>
                      {item.diagnostic_message}
                    </div>
                  )}
                  <div style={{ marginTop: '4px', display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
                    {Object.entries(item.capabilities || {}).map(([cap, supported]) => (
                      <span key={cap} style={{
                        padding: '1px 5px',
                        borderRadius: '3px',
                        background: supported ? 'rgba(34, 197, 94, 0.1)' : 'rgba(148, 163, 184, 0.1)',
                        color: supported ? '#15803d' : '#94a3b8',
                        fontSize: '10px',
                      }}>
                        {cap.replace('_supported', '')}: {supported ? 'Yes' : 'No'}
                      </span>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
