import { useEffect, useState, useRef } from 'react';
import { BrowserRouter as Router, Routes, Route, Link, useLocation } from 'react-router-dom';
import {
  AlertCircle,
  ArrowRight,
  BarChart3,
  Bell,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Clock,
  Download,
  ExternalLink,
  FileImage,
  Layers,
  LocateFixed,
  LoaderCircle,
  LogIn,
  LogOut,
  MapPin,
  RefreshCw,
  RotateCcw,
  ScanSearch,
  Search,
  Shield,
  ShieldAlert,
  Sparkles,
  Upload,
  User,
  UserCheck,
  UserPlus,
  UserX,
  X,
} from 'lucide-react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import './App.css';
import {
  API_UPLOAD_LIMIT_BYTES,
  DetectionApiError,
  predictImage,
} from './services/detectionApi';
import {
  getCurrentLocation,
  locationErrorMessage,
  normalizePosition,
  reverseGeocode,
} from './services/locationApi';
import { resolveAuthority, fetchAuthorityMapCases, updateAuthorityCaseStatus } from './services/authorityApi';
import { generateComplaintDraft, ComplaintApiError } from './services/complaintApi';
import {
  createCvkiCase,
  getCvkiCaseStatus,
  getCvkiCase,
  getMyCvkiCases,
  getSubmissionReadiness,
  prepareGovernmentSubmission,
  ComplaintCaseApiError,
} from './services/complaintCaseApi';
import {
  registerCitizen,
  loginCitizen,
  getCurrentUser,
  setAuthSession,
  clearAuthSession,
  logout,
  AuthApiError,
} from './services/authApi';
import {
  analyzeNlpComplaint,
  checkDuplicateComplaint,
  scorePriority,
} from './services/intelligenceApi';
import {
  getNotifications,
  getUnreadNotificationCount,
  markNotificationRead,
  markAllNotificationsRead,
  NotificationApiError,
} from './services/notificationApi';
import {
  fetchDashboardSummary,
  fetchAdminCases,
  fetchAdminCaseDetail,
  assignCase,
  unassignCase,
  fetchAuthorities,
  updateCaseStatus,
  fetchMapCases,
  fetchOperationalAnalytics,
  downloadAnalyticsCsv,
  fetchAuditLogs,
  fetchSecurityOverview,
  AdminApiError,
} from './services/adminApi';

const ACCEPTED_TYPES = ['image/jpeg', 'image/png', 'image/webp'];
const ACCEPTED_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.webp'];

function formatClassName(className) {
  return className
    .replaceAll('_', ' ')
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatDate(isoString) {
  if (!isoString) return 'Date unavailable';
  try {
    const d = new Date(isoString);
    return d.toLocaleDateString('en-GB', {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
    });
  } catch {
    return isoString;
  }
}

function formatLocationSummary(loc) {
  if (!loc) return 'Location unavailable';
  if (typeof loc === 'string') return loc.trim() || 'Location unavailable';
  const parts = [loc.road, loc.area, loc.city].filter(Boolean);
  if (parts.length > 0) return parts.join(', ');
  if (
    Number.isFinite(loc.latitude)
    && Number.isFinite(loc.longitude)
    && !(Math.abs(loc.latitude) < 1e-6 && Math.abs(loc.longitude) < 1e-6)
  ) {
    return `${Number(loc.latitude).toFixed(4)}, ${Number(loc.longitude).toFixed(4)}`;
  }
  return 'Location unavailable';
}

function hasUsableMapCoordinates(item) {
  const { latitude, longitude } = item;
  return Number.isFinite(latitude)
    && Number.isFinite(longitude)
    && latitude >= -90
    && latitude <= 90
    && longitude >= -180
    && longitude <= 180
    && !(Math.abs(latitude) < 1e-6 && Math.abs(longitude) < 1e-6);
}

function formatReadinessStatus(status) {
  if (!status) return 'Not Evaluated';
  return String(status).replaceAll('_', ' ').toUpperCase();
}

function validateFile(file) {
  if (!file) return 'Choose an image before analyzing.';
  const hasSupportedType = ACCEPTED_TYPES.includes(file.type)
    || ACCEPTED_EXTENSIONS.some((extension) => file.name.toLowerCase().endsWith(extension));
  if (!hasSupportedType) return 'Choose a JPG, PNG, or WEBP image.';
  if (file.size === 0) return 'That image is empty. Choose another file.';
  if (file.size > API_UPLOAD_LIMIT_BYTES) return 'That image is larger than the 10 MB upload limit.';
  return null;
}

function AuthModal({ initialMode, onClose, onSuccess }) {
  const [tab, setTab] = useState(initialMode || 'login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError('');

    if (!email || !email.includes('@')) {
      setError('Please provide a valid email address.');
      return;
    }
    if (!password || password.length < 8) {
      setError('Password must be at least 8 characters long.');
      return;
    }

    setLoading(true);
    try {
      if (tab === 'register') {
        const response = await registerCitizen({ email, password });
        setAuthSession(response.user);
        onSuccess(response.user);
      } else {
        const response = await loginCitizen({ email, password });
        setAuthSession(response.user);
        onSuccess(response.user);
      }
      onClose();
    } catch (err) {
      setError(err instanceof AuthApiError ? err.message : 'Authentication failed. Please check your credentials.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose} role="dialog" aria-modal="true" aria-labelledby="auth-modal-title">
      <div className="modal-card auth-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div className="auth-tabs" role="tablist">
            <button
              type="button"
              role="tab"
              aria-selected={tab === 'login'}
              className={`auth-tab-btn ${tab === 'login' ? 'active' : ''}`}
              onClick={() => { setTab('login'); setError(''); }}
            >
              <LogIn size={15} /> Sign In
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={tab === 'register'}
              className={`auth-tab-btn ${tab === 'register' ? 'active' : ''}`}
              onClick={() => { setTab('register'); setError(''); }}
            >
              <UserPlus size={15} /> Register
            </button>
          </div>
          <button className="icon-close-btn" type="button" onClick={onClose} aria-label="Close dialog">
            <X size={18} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="auth-form">
          <h3 id="auth-modal-title">
            {tab === 'register' ? 'Create a Citizen Account' : 'Citizen Sign In'}
          </h3>
          <p className="auth-subtitle">
            {tab === 'register'
              ? 'Register securely to save and track your civic complaints.'
              : 'Sign in to access your complaint cases and track status.'}
          </p>

          <label className="form-label" htmlFor="auth-email">
            Email address
            <input
              id="auth-email"
              type="email"
              className="form-input"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="citizen@example.com"
              required
              autoFocus
            />
          </label>

          <label className="form-label" htmlFor="auth-password">
            Password
            <input
              id="auth-password"
              type="password"
              className="form-input"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Minimum 8 characters"
              required
            />
          </label>

          {error && (
            <div className="message error-message auth-error" role="alert">
              <AlertCircle size={16} /> <span>{error}</span>
            </div>
          )}

          <div className="modal-actions">
            <button className="primary-button full-width" type="submit" disabled={loading}>
              {loading ? <LoaderCircle className="spin" size={17} /> : (tab === 'register' ? <UserPlus size={17} /> : <LogIn size={17} />)}
              {loading ? 'Authenticating...' : (tab === 'register' ? 'Register Account' : 'Sign In')}
            </button>
          </div>

          <p className="auth-disclaimer">
            Passwords are encrypted with bcrypt. Your personal identifiers are never shared publicly.
          </p>
        </form>
      </div>
    </div>
  );
}

function NotificationDropdown({ currentUser, onSelectCase }) {
  const [isOpen, setIsOpen] = useState(false);
  const [unreadCount, setUnreadCount] = useState(0);
  const [notifications, setNotifications] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  async function loadNotifications() {
    if (!currentUser) return;
    setLoading(true);
    setError('');
    try {
      const res = await getNotifications(1, 20);
      setNotifications(res.items || []);
      setUnreadCount(res.unread_count || 0);
    } catch (err) {
      setError(err instanceof NotificationApiError ? err.message : 'Could not load notifications.');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    let isMounted = true;
    async function loadCount() {
      if (!currentUser) return;
      try {
        const res = await getUnreadNotificationCount();
        if (isMounted) setUnreadCount(res.unread_count || 0);
      } catch {
        // Non-blocking fallback
      }
    }
    loadCount();
    const interval = setInterval(loadCount, 15000);
    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, [currentUser]);

  function handleToggle() {
    if (!isOpen) {
      loadNotifications();
    }
    setIsOpen(!isOpen);
  }

  async function handleMarkRead(e, notificationId) {
    e.stopPropagation();
    try {
      await markNotificationRead(notificationId);
      setNotifications((prev) =>
        prev.map((n) => (n.notification_id === notificationId ? { ...n, is_read: true } : n))
      );
      setUnreadCount((prev) => Math.max(0, prev - 1));
    } catch {
      // Ignored
    }
  }

  async function handleMarkAllRead() {
    try {
      await markAllNotificationsRead();
      setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true })));
      setUnreadCount(0);
    } catch {
      // Ignored
    }
  }

  function handleItemClick(notif) {
    if (!notif.is_read) {
      markNotificationRead(notif.notification_id).catch(() => {});
      setNotifications((prev) =>
        prev.map((n) => (n.notification_id === notif.notification_id ? { ...n, is_read: true } : n))
      );
      setUnreadCount((prev) => Math.max(0, prev - 1));
    }
    if (notif.reference_id && onSelectCase) {
      onSelectCase(notif.reference_id);
      setIsOpen(false);
    }
  }

  return (
    <div className="notif-wrapper">
      <button
        type="button"
        className="notif-bell-btn"
        onClick={handleToggle}
        title="Notifications"
        aria-label="View notifications"
      >
        <Bell size={16} />
        {unreadCount > 0 && <span className="notif-badge">{unreadCount}</span>}
      </button>

      {isOpen && (
        <div className="notif-dropdown">
          <div className="notif-dropdown-header">
            <h4>Notifications {unreadCount > 0 && `(${unreadCount} new)`}</h4>
            {notifications.some((n) => !n.is_read) && (
              <button
                type="button"
                className="notif-mark-all-btn"
                onClick={handleMarkAllRead}
              >
                Mark all read
              </button>
            )}
          </div>

          {loading ? (
            <div className="modal-loading" style={{ padding: '20px' }}>
              <LoaderCircle className="spin" size={20} />
              <p style={{ fontSize: '11px' }}>Loading notifications...</p>
            </div>
          ) : error ? (
            <div className="notif-empty" style={{ color: 'var(--error)' }}>
              {error}
            </div>
          ) : notifications.length === 0 ? (
            <div className="notif-empty">No notifications yet.</div>
          ) : (
            <ul className="notif-list">
              {notifications.map((notif) => (
                <li
                  key={notif.notification_id}
                  className={`notif-item ${!notif.is_read ? 'unread' : ''}`}
                  onClick={() => handleItemClick(notif)}
                >
                  <div className="notif-item-top">
                    <span className="notif-type-tag">{notif.type?.replaceAll('_', ' ')}</span>
                    <span className={`priority-badge-tag ${notif.priority?.toLowerCase() || 'p3'}`} style={{ fontSize: '9px', padding: '1px 4px' }}>
                      {notif.priority}
                    </span>
                  </div>
                  <h5 className="notif-item-title">{notif.title}</h5>
                  <p className="notif-item-message">{notif.message}</p>
                  <div className="notif-item-bottom">
                    <span>{formatDate(notif.created_at)}</span>
                    {!notif.is_read && (
                      <button
                        type="button"
                        className="notif-mark-read-btn"
                        onClick={(e) => handleMarkRead(e, notif.notification_id)}
                      >
                        Mark read
                      </button>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

function LifecycleProgressBar({ currentStatus }) {
  const steps = [
    { key: 'submitted_to_cvki', label: 'Submitted' },
    { key: 'assigned', label: 'Assigned' },
    { key: 'in_progress', label: 'In Progress' },
    { key: 'resolved', label: 'Resolved' },
    { key: 'closed', label: 'Closed' },
  ];

  const statusOrder = {
    draft: 0,
    submitted_to_cvki: 1,
    under_review: 1.5,
    assigned: 2,
    in_progress: 3,
    resolved: 4,
    closed: 5,
  };

  const currentVal = statusOrder[currentStatus] || 1;
  const progressPercent = Math.min(100, Math.max(0, ((currentVal - 1) / 4) * 100));

  return (
    <div className="lifecycle-timeline" role="progressbar" aria-valuenow={progressPercent} aria-valuemin="0" aria-valuemax="100">
      <div className="timeline-connector">
        <div className="timeline-connector-fill" style={{ width: `${progressPercent}%` }} />
      </div>
      {steps.map((st, index) => {
        const stepVal = index + 1;
        const isCompleted = currentVal > stepVal;
        const isCurrent = currentVal === stepVal || (st.key === 'submitted_to_cvki' && currentStatus === 'under_review' && index === 0);
        return (
          <div
            key={st.key}
            className={`timeline-step ${isCompleted ? 'completed' : ''} ${isCurrent ? 'current' : ''}`}
          >
            <div className="timeline-dot">
              {isCompleted ? <CheckCircle2 size={13} /> : index + 1}
            </div>
            <span className="timeline-label">{st.label}</span>
          </div>
        );
      })}
    </div>
  );
}

function CaseDetailModal({ referenceId, onClose }) {
  const [caseData, setCaseData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [readiness, setReadiness] = useState(null);
  const [isCheckingReadiness, setIsCheckingReadiness] = useState(false);
  const [isPreparingSubmission, setIsPreparingSubmission] = useState(false);
  const [govMessage, setGovMessage] = useState('');
  const [govError, setGovError] = useState('');

  async function handleCheckReadiness() {
    if (!caseData) return;
    setIsCheckingReadiness(true);
    setGovError('');
    setGovMessage('');
    try {
      const res = await getSubmissionReadiness(caseData.reference_id);
      setReadiness(res);
    } catch (err) {
      setGovError(err instanceof ComplaintCaseApiError ? err.message : 'Could not verify submission readiness.');
    } finally {
      setIsCheckingReadiness(false);
    }
  }

  async function handlePrepareSubmission() {
    if (!caseData) return;
    setIsPreparingSubmission(true);
    setGovError('');
    setGovMessage('');
    try {
      const res = await prepareGovernmentSubmission(caseData.reference_id);
      setCaseData((prev) => ({
        ...prev,
        government_submission: {
          package: res.package,
          submission_status: res.submission_status,
          readiness_status: res.readiness_status,
          prepared_at: res.prepared_at,
          limitations: res.limitations,
        },
      }));
      setGovMessage('Government submission package prepared successfully. Note: It has not been sent to any external government portal.');
    } catch (err) {
      setGovError(err instanceof ComplaintCaseApiError ? err.message : 'Could not prepare government submission package.');
    } finally {
      setIsPreparingSubmission(false);
    }
  }

  useEffect(() => {
    let isMounted = true;
    async function loadCase() {
      setLoading(true);
      setError('');
      try {
        const data = await getCvkiCase(referenceId);
        if (isMounted) setCaseData(data);
      } catch (err) {
        if (isMounted) setError(err instanceof ComplaintCaseApiError ? err.message : 'Could not load case details.');
      } finally {
        if (isMounted) setLoading(false);
      }
    }
    if (referenceId) loadCase();
    return () => { isMounted = false; };
  }, [referenceId]);

  return (
    <div className="modal-backdrop" onClick={onClose} role="dialog" aria-modal="true" aria-labelledby="case-detail-title">
      <div className="modal-card case-detail-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h3 id="case-detail-title">Case Details</h3>
          <button className="icon-close-btn" type="button" onClick={onClose} aria-label="Close dialog">
            <X size={18} />
          </button>
        </div>

        {loading && (
          <div className="modal-loading">
            <LoaderCircle className="spin" size={24} />
            <p>Loading case information...</p>
          </div>
        )}

        {error && (
          <div className="message error-message" role="alert">
            <AlertCircle size={17} /> <span>{error}</span>
          </div>
        )}

        {caseData && !loading && (
          <div className="case-detail-content">
            <div className="detail-hero">
              <span className="case-ref-chip">{caseData.reference_id}</span>
              <span className="status-badge">{caseData.status ? caseData.status.replaceAll('_', ' ') : 'Submitted to CVKI'}</span>
            </div>

            <LifecycleProgressBar currentStatus={caseData.status} />

            <div className="detail-section">
              <h4>Complaint Information</h4>
              <p className="detail-title"><strong>Title:</strong> {caseData.complaint?.title || 'Civic Issue'}</p>
              <div className="detail-description-box">
                {caseData.complaint?.description || 'No description provided.'}
              </div>
            </div>

            <div className="detail-section">
              <h4>Issue Classification</h4>
              <div className="detail-grid">
                <p><span>Issue:</span> <strong>{caseData.issue?.label || caseData.issue?.class_name}</strong></p>
                <p><span>Severity:</span> <strong>{caseData.issue?.severity || 'Standard'}</strong></p>
                {caseData.issue?.confidence && (
                  <p><span>Vision Confidence:</span> <strong>{Math.round(caseData.issue.confidence * 100)}%</strong></p>
                )}
                <p><span>Created Date:</span> <strong>{formatDate(caseData.created_at)}</strong></p>
              </div>
            </div>

            <div className="detail-section">
              <h4>Location & Jurisdiction</h4>
              <div className="detail-grid">
                <p><span>Road / Street:</span> <strong>{caseData.location?.road || 'Unavailable'}</strong></p>
                <p><span>Area:</span> <strong>{caseData.location?.area || 'Unavailable'}</strong></p>
                <p><span>City:</span> <strong>{caseData.location?.city || 'Unavailable'}</strong></p>
                <p><span>State:</span> <strong>{caseData.location?.state || 'Unavailable'}</strong></p>
                {caseData.location?.latitude && (
                  <p><span>Coordinates:</span> <strong>{caseData.location.latitude.toFixed(5)}, {caseData.location.longitude.toFixed(5)}</strong></p>
                )}
              </div>
            </div>

            <div className="detail-section">
              <h4>Authority & External Submission</h4>
              <div className="detail-grid">
                <p><span>Responsible Authority:</span> <strong>{caseData.authority?.maintenance_authority?.name || caseData.authority?.road_owner?.name || 'Local Municipal Body'}</strong></p>
                <p><span>Authority Status:</span> <strong>{caseData.authority?.authority_status ? caseData.authority.authority_status.replaceAll('_', ' ') : 'Not Verified'}</strong></p>
                <p><span>Government Status:</span> <strong className="sub-status-text">Government Submission: Not Submitted</strong></p>
              </div>
            </div>

            {caseData.follow_up?.official_guidance && (
              <div className="detail-section official-guidance-section">
                <h4>Government Complaint Guidance</h4>
                <div className="detail-grid">
                  <p><span>Recommended Channel:</span> <strong>{caseData.follow_up.official_guidance.recommended_channel}</strong></p>
                  {caseData.follow_up.official_guidance.official_portal_url && (
                    <p>
                      <span>Official Portal:</span>
                      <a href={caseData.follow_up.official_guidance.official_portal_url} target="_blank" rel="noopener noreferrer" className="official-source-link">
                        {caseData.follow_up.official_guidance.official_portal_url} <ExternalLink size={12} />
                      </a>
                    </p>
                  )}
                  <p><span>Government Status:</span> <strong className="sub-status-text">Not Submitted</strong></p>
                </div>
                {caseData.follow_up.official_guidance.steps.length > 0 && (
                  <div className="guidance-steps-box">
                    <strong>Submission Steps:</strong>
                    <ol className="guidance-steps-ordered">
                      {caseData.follow_up.official_guidance.steps.map((st, idx) => (
                        <li key={idx}>{st}</li>
                      ))}
                    </ol>
                  </div>
                )}
              </div>
            )}

            {caseData.priority_analysis && (
              <div className="detail-section priority-section">
                <h4>Civic Priority & Risk Triage</h4>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                  <span className={`priority-badge-tag ${caseData.priority_analysis.priority_level.toLowerCase()}`}>
                    {caseData.priority_analysis.priority_level} — {caseData.priority_analysis.risk_level} Priority
                  </span>
                  <span className="priority-score-pill">Score: {caseData.priority_analysis.priority_score} / 100</span>
                </div>
                {caseData.priority_analysis.reasons?.length > 0 && (
                  <div className="priority-reasons-box">
                    <strong style={{ fontSize: '11px', color: 'var(--forest)' }}>Why this priority?</strong>
                    <ul className="reasons-list">
                      {caseData.priority_analysis.reasons.map((r, idx) => (
                        <li key={idx}>{r}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}

            {caseData.duplicate_analysis && (
              <div className="detail-section duplicate-section">
                <h4>Duplicate Report Analysis</h4>
                <div className="detail-grid">
                  <p><span>Detection Status:</span> <strong className={`duplicate-badge ${caseData.duplicate_analysis.classification}`}>{caseData.duplicate_analysis.classification.replaceAll('_', ' ')}</strong></p>
                  {caseData.duplicate_analysis.matched_reference_id && (
                    <p><span>Matched Reference:</span> <strong>{caseData.duplicate_analysis.matched_reference_id}</strong></p>
                  )}
                  {caseData.duplicate_analysis.distance_meters != null && (
                    <p><span>Distance:</span> <strong>{Math.round(caseData.duplicate_analysis.distance_meters)} m</strong></p>
                  )}
                  {caseData.duplicate_analysis.similarity_score > 0 && (
                    <p><span>Similarity Score:</span> <strong>{Math.round(caseData.duplicate_analysis.similarity_score * 100)}%</strong></p>
                  )}
                </div>
                {caseData.duplicate_analysis.reason && (
                  <p className="intelligence-explanation">{caseData.duplicate_analysis.reason}</p>
                )}
              </div>
            )}

            {caseData.nlp_analysis && (
              <div className="detail-section nlp-section">
                <h4>NLP Complaint Intelligence</h4>
                <div className="detail-grid">
                  <p><span>Detected Language:</span> <strong>{caseData.nlp_analysis.detected_language?.toUpperCase()} ({Math.round(caseData.nlp_analysis.confidence * 100)}%)</strong></p>
                  <p><span>NLP Issue Category:</span> <strong>{caseData.nlp_analysis.issue_category?.replaceAll('_', ' ')}</strong></p>
                </div>
                {caseData.nlp_analysis.severity_signals?.length > 0 && (
                  <div className="signals-tag-row" style={{ marginTop: '6px' }}>
                    <span style={{ fontSize: '11px', color: 'var(--muted)' }}>Severity Signals:</span>
                    {caseData.nlp_analysis.severity_signals.map((sig, idx) => (
                      <span key={`sev-${idx}`} className="signal-chip severity">{sig}</span>
                    ))}
                  </div>
                )}
                {caseData.nlp_analysis.risk_signals?.length > 0 && (
                  <div className="signals-tag-row" style={{ marginTop: '6px' }}>
                    <span style={{ fontSize: '11px', color: 'var(--muted)' }}>Risk Signals:</span>
                    {caseData.nlp_analysis.risk_signals.map((sig, idx) => (
                      <span key={`risk-${idx}`} className="signal-chip risk">{sig}</span>
                    ))}
                  </div>
                )}
                {caseData.nlp_analysis.extracted_entities?.length > 0 && (
                  <div className="extracted-entities-box" style={{ marginTop: '6px' }}>
                    <span style={{ fontSize: '11px', color: 'var(--muted)' }}>Extracted Text Entities:</span>
                    <div className="entity-chips">
                      {caseData.nlp_analysis.extracted_entities.map((ent, idx) => (
                        <span key={idx} className="entity-chip">{ent.name} ({ent.type})</span>
                      ))}
                    </div>
                  </div>
                )}
                {caseData.nlp_analysis.explanation && (
                  <p className="intelligence-explanation">{caseData.nlp_analysis.explanation}</p>
                )}
              </div>
            )}

            {caseData.follow_up?.guidance && (
              <div className="detail-guidance">
                <strong>Follow-up Guidance:</strong>
                <p>{caseData.follow_up.guidance}</p>
              </div>
            )}

            <div className="detail-section gov-submission-section">
              <h4>Government Dispatch &amp; Submission Preparation</h4>

              <div className="gov-status-row">
                <span className="gov-pill cvki-status">
                  <CheckCircle2 size={12} /> CVKI Case: Submitted to CVKI
                </span>
                <span className="gov-pill external-status">
                  <AlertCircle size={12} /> Government Submission: Not Submitted
                </span>
                <span className={`gov-pill readiness-${readiness?.readiness_status || caseData.government_submission?.readiness_status || 'idle'}`}>
                  Readiness: {formatReadinessStatus(readiness?.readiness_status || caseData.government_submission?.readiness_status)}
                </span>
              </div>

              <div className="gov-safety-banner">
                <strong>User Safety Notice:</strong> CVKI case creation ≠ government submission. Preparing a dispatch package formats verified complaint data for official review; it does not automatically submit complaints to government websites or fabricate acknowledgment numbers.
              </div>

              <div className="detail-grid" style={{ marginTop: '8px' }}>
                <p>
                  <span>Authority Verification:</span>
                  <strong>
                    {caseData.authority?.authority_status === 'verified'
                      ? 'Verified'
                      : caseData.authority?.authority_status === 'partially_verified'
                      ? 'Partially Verified'
                      : 'Not Verified'}
                  </strong>
                </p>
                <p>
                  <span>Government Status:</span>
                  <strong className="sub-status-text">NOT_SUBMITTED</strong>
                </p>
              </div>

              <div className="official-evidence-box" style={{ marginTop: '8px' }}>
                <strong style={{ fontSize: '11px', color: 'var(--forest)' }}>Official Evidence Sources:</strong>
                {(() => {
                  const sources = readiness?.official_sources || caseData.government_submission?.official_sources || caseData.authority?.evidence_records || [];
                  if (sources.length === 0) {
                    return <p style={{ fontSize: '11px', color: 'var(--muted)', margin: '4px 0 0' }}>Official government submission destination could not be verified for this case.</p>;
                  }
                  return (
                    <ul className="reasons-list" style={{ marginTop: '4px' }}>
                      {sources.map((src, idx) => (
                        <li key={idx} style={{ fontSize: '11px' }}>
                          <strong>{src.source_name || src.source || 'Official Source'}</strong>
                          {src.domain && ` (${src.domain})`}
                          {(src.url || src.official_source_url) && (
                            <> — <a href={src.url || src.official_source_url} target="_blank" rel="noopener noreferrer" className="official-source-link">{src.url || src.official_source_url} <ExternalLink size={10} /></a></>
                          )}
                        </li>
                      ))}
                    </ul>
                  );
                })()}
              </div>

              {readiness?.reasons?.length > 0 && (
                <div className="priority-reasons-box" style={{ marginTop: '8px' }}>
                  <strong style={{ fontSize: '11px', color: readiness.readiness_status === 'blocked' ? 'var(--error)' : 'var(--forest)' }}>
                    {readiness.readiness_status === 'blocked' ? 'Readiness Blockers:' : 'Evaluation Notes:'}
                  </strong>
                  <ul className="reasons-list">
                    {readiness.reasons.map((r, idx) => (
                      <li key={idx}>{r}</li>
                    ))}
                  </ul>
                </div>
              )}

              {govMessage && (
                <div className="message success-message" style={{ margin: '8px 0', fontSize: '11px' }}>
                  <CheckCircle2 size={14} /> <span>{govMessage}</span>
                </div>
              )}
              {govError && (
                <div className="message error-message" style={{ margin: '8px 0', fontSize: '11px' }}>
                  <AlertCircle size={14} /> <span>{govError}</span>
                </div>
              )}

              <div className="gov-action-buttons">
                <button
                  type="button"
                  className="gov-action-btn"
                  onClick={handleCheckReadiness}
                  disabled={isCheckingReadiness || isPreparingSubmission}
                >
                  {isCheckingReadiness ? <LoaderCircle className="spin" size={13} /> : <ScanSearch size={13} />}
                  Check Submission Readiness
                </button>
                <button
                  type="button"
                  className="gov-action-btn primary"
                  onClick={handlePrepareSubmission}
                  disabled={isPreparingSubmission || isCheckingReadiness || readiness?.readiness_status === 'blocked'}
                >
                  {isPreparingSubmission ? <LoaderCircle className="spin" size={13} /> : <Sparkles size={13} />}
                  Prepare Government Submission
                </button>
              </div>

              {caseData.government_submission?.package && (
                <div className="gov-package-card">
                  <h5>Prepared Government Submission Package</h5>
                  <div className="detail-grid" style={{ fontSize: '11px' }}>
                    <p><span>Prepared At:</span> <strong>{formatDate(caseData.government_submission.prepared_at)}</strong></p>
                    <p><span>Dispatch Status:</span> <strong>{caseData.government_submission.submission_status || 'NOT_SUBMITTED'}</strong></p>
                    <p><span>Road Owner:</span> <strong>{caseData.government_submission.package.road_owner || 'Unassigned'}</strong></p>
                    <p><span>Maintenance Body:</span> <strong>{caseData.government_submission.package.maintenance_authority || 'Unassigned'}</strong></p>
                    {caseData.government_submission.package.builder_or_contractor && (
                      <p><span>Verified Contractor:</span> <strong>{caseData.government_submission.package.builder_or_contractor}</strong></p>
                    )}
                  </div>
                  {caseData.government_submission.limitations?.length > 0 && (
                    <div style={{ marginTop: '6px' }}>
                      <span style={{ fontSize: '10px', color: 'var(--muted)' }}>Limitations:</span>
                      <ul className="reasons-list" style={{ fontSize: '10px' }}>
                        {caseData.government_submission.limitations.map((lim, idx) => (
                          <li key={idx}>{lim}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function DetectionWorkspace({ currentUser, onOpenAuth }) {
  const [selectedFile, setSelectedFile] = useState(null);
  const [previewUrl, setPreviewUrl] = useState('');
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [location, setLocation] = useState(null);
  const [locationState, setLocationState] = useState('idle');
  const [locationError, setLocationError] = useState('');
  const [authority, setAuthority] = useState(null);
  const [authorityError, setAuthorityError] = useState('');
  const [complaint, setComplaint] = useState(null);
  const [complaintText, setComplaintText] = useState('');
  const [complaintTitle, setComplaintTitle] = useState('');
  const [complaintLanguage, setComplaintLanguage] = useState('en');
  const [isGeneratingComplaint, setIsGeneratingComplaint] = useState(false);
  const [complaintError, setComplaintError] = useState('');
  const [copyStatus, setCopyStatus] = useState('');
  const [cvkiCase, setCvkiCase] = useState(null);
  const [caseStatus, setCaseStatus] = useState(null);
  const [caseError, setCaseError] = useState('');
  const [isCreatingCase, setIsCreatingCase] = useState(false);
  const [liveIntelligence, setLiveIntelligence] = useState(null);
  const [isLoadingIntelligence, setIsLoadingIntelligence] = useState(false);
  const [intelligenceWarning, setIntelligenceWarning] = useState('');

  useEffect(() => () => {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
  }, [previewUrl]);

  function handleFileChange(event) {
    const file = event.target.files?.[0] || null;
    const validationError = validateFile(file);
    setResult(null);
    setComplaint(null);
    setComplaintText('');
    setComplaintTitle('');
    setComplaintError('');
    setCvkiCase(null);
    setCaseStatus(null);
    setCaseError('');
    setLiveIntelligence(null);
    setIntelligenceWarning('');
    setError(validationError || '');
    if (validationError) {
      setSelectedFile(null);
      setPreviewUrl((currentUrl) => {
        if (currentUrl) URL.revokeObjectURL(currentUrl);
        return '';
      });
      return;
    }

    setSelectedFile(file);
    setPreviewUrl((currentUrl) => {
      if (currentUrl) URL.revokeObjectURL(currentUrl);
      return URL.createObjectURL(file);
    });
  }

  function resetWorkspace() {
    setSelectedFile(null);
    setResult(null);
    setError('');
    setComplaint(null);
    setComplaintText('');
    setComplaintTitle('');
    setComplaintError('');
    setCvkiCase(null);
    setCaseStatus(null);
    setCaseError('');
    setLiveIntelligence(null);
    setIsLoadingIntelligence(false);
    setIntelligenceWarning('');
    setPreviewUrl((currentUrl) => {
      if (currentUrl) URL.revokeObjectURL(currentUrl);
      return '';
    });
  }

  async function handleAnalyze() {
    const validationError = validateFile(selectedFile);
    if (validationError) {
      setError(validationError);
      return;
    }

    setIsAnalyzing(true);
    setError('');
    setResult(null);
    setComplaint(null);
    setComplaintText('');
    setComplaintTitle('');
    setComplaintError('');
    setCvkiCase(null);
    setCaseStatus(null);
    setCaseError('');
    setLiveIntelligence(null);
    setIsLoadingIntelligence(false);
    setIntelligenceWarning('');
    try {
      const payload = await predictImage(selectedFile);
      setResult(payload);
      setComplaint(null);
      setComplaintText('');
      setComplaintTitle('');
      setCvkiCase(null);
      setCaseStatus(null);
    } catch (caughtError) {
      const message = caughtError instanceof DetectionApiError
        ? caughtError.message
        : 'The image could not be analyzed. Try again.';
      setError(message);
      setResult(null);
    } finally {
      setIsAnalyzing(false);
    }
  }

  async function fetchLiveIntelligence(title, description, issueCat, cvConfidence, locPayload, authPayload) {
    setIsLoadingIntelligence(true);
    setIntelligenceWarning('');
    try {
      const nlp = await analyzeNlpComplaint({
        title,
        description,
        language: complaintLanguage,
        issue_class: issueCat,
      });

      let dup = null;
      if (currentUser) {
        try {
          dup = await checkDuplicateComplaint({
            complaint_text: `${title} ${description}`.trim(),
            issue_category: issueCat,
            latitude: locPayload?.latitude ?? null,
            longitude: locPayload?.longitude ?? null,
          });
        } catch {
          dup = null;
          setIntelligenceWarning('Duplicate analysis is unavailable; priority analysis may omit duplicate signals.');
        }
      }

      const prio = await scorePriority({
        issue_category: issueCat,
        cv_confidence: cvConfidence,
        nlp_analysis: nlp,
        duplicate_analysis: dup,
        location_context: locPayload,
        authority_context: authPayload,
      });

      setLiveIntelligence({ nlp, dup, prio });
    } catch {
      setIntelligenceWarning('Additional complaint intelligence could not be loaded. The draft remains available.');
    } finally {
      setIsLoadingIntelligence(false);
    }
  }

  async function handleGenerateComplaint() {
    if (!result || result.total_detections === 0) return;
    const detection = result.detections.reduce((best, current) => (
      current.confidence > best.confidence ? current : best
    ));
    setIsGeneratingComplaint(true);
    setComplaintError('');
    setCopyStatus('');
    setComplaint(null);
    setComplaintText('');
    setComplaintTitle('');
    setCvkiCase(null);
    setCaseStatus(null);
    setLiveIntelligence(null);
    setIntelligenceWarning('');
    try {
      const locationPayload = location?.address ? {
        road: location.address.road,
        area: location.address.area,
        city: location.address.city,
        district: location.address.district,
        state: location.address.state,
        latitude: location.coordinates.latitude,
        longitude: location.coordinates.longitude,
      } : null;
      const payload = await generateComplaintDraft({
        detection: { class_name: detection.class_name, confidence: detection.confidence },
        location: locationPayload,
        authority: authority?.authority || null,
        language: complaintLanguage,
        imageAttached: Boolean(selectedFile),
      });
      setComplaint(payload);
      setComplaintTitle(payload.title);
      setComplaintText(payload.description);
      setCvkiCase(null);
      setCaseStatus(null);
      fetchLiveIntelligence(payload.title, payload.description, detection.class_name, detection.confidence, locationPayload, authority?.authority || null);
    } catch (caughtError) {
      setComplaintError(caughtError instanceof ComplaintApiError ? caughtError.message : 'The complaint draft could not be generated.');
    } finally {
      setIsGeneratingComplaint(false);
    }
  }

  async function handleCopyComplaint() {
    try {
      await navigator.clipboard.writeText(complaintText);
      setCopyStatus('Copied');
    } catch {
      setCopyStatus('Copy unavailable');
    }
  }

  async function handleCreateCase() {
    if (!complaint || !result) return;

    if (!currentUser) {
      setCaseError('Please sign in or register to create and track your CVKI case.');
      onOpenAuth('login');
      return;
    }

    const detection = result.detections.reduce((best, current) => (
      current.confidence > best.confidence ? current : best
    ));
    setIsCreatingCase(true);
    setCaseError('');
    try {
      const locationPayload = location?.address ? {
        road: location.address.road,
        area: location.address.area,
        city: location.address.city,
        district: location.address.district,
        state: location.address.state,
        latitude: location.coordinates.latitude,
        longitude: location.coordinates.longitude,
      } : null;
      const created = await createCvkiCase({
        issue: { class_name: detection.class_name, label: complaint.issue_label, severity: complaint.severity, confidence: detection.confidence },
        location: locationPayload,
        authority: authority?.authority || null,
        complaint: { language: complaint.language, title: complaintTitle, description: complaintText },
        evidence: complaint.evidence,
        nlp_analysis: liveIntelligence?.nlp || null,
        duplicate_analysis: liveIntelligence?.dup || null,
        priority_analysis: liveIntelligence?.prio || null,
      });
      setCvkiCase(created);
      setCaseStatus(null);
    } catch (caughtError) {
      if (caughtError instanceof ComplaintCaseApiError && caughtError.message.includes('Authentication')) {
        setCaseError('Your session has expired. Please sign in again.');
        onOpenAuth('login');
      } else {
        setCaseError(caughtError instanceof ComplaintCaseApiError ? caughtError.message : 'The CVKI case could not be created.');
      }
    } finally {
      setIsCreatingCase(false);
    }
  }

  async function handleViewCaseStatus() {
    if (!cvkiCase) return;
    try {
      setCaseStatus(await getCvkiCaseStatus(cvkiCase.reference_id));
      setCaseError('');
    } catch (caughtError) {
      setCaseError(caughtError instanceof ComplaintCaseApiError ? caughtError.message : 'The CVKI case status could not be loaded.');
    }
  }

  async function handleUseLocation() {
    setLocationState('loading');
    setLocationError('');
    setAuthority(null);
    setAuthorityError('');
    try {
      const position = await getCurrentLocation();
      const coordinates = normalizePosition(position);
      setLocation({ coordinates, address: null });
      try {
        const address = await reverseGeocode(coordinates);
        setLocation({ coordinates, address });
        try {
          setAuthority(await resolveAuthority({ coordinates, address }));
        } catch (caughtError) {
          setAuthorityError(caughtError.message || 'Authority information is temporarily unavailable.');
        }
        setLocationState('ready');
      } catch (caughtError) {
        setLocationState('partial');
        setLocationError(caughtError.message || 'Coordinates available, but road information could not be resolved.');
      }
    } catch (caughtError) {
      setLocation(null);
      setLocationState('error');
      setLocationError(locationErrorMessage(caughtError));
    }
  }

  return (
    <section className="workspace" aria-labelledby="workspace-title">
      <div className="workspace-intro">
        <div>
          <p className="eyebrow"><ScanSearch size={16} /> Civic image inspection</p>
          <h2 id="workspace-title">See the issue clearly.</h2>
          <p className="intro-copy">
            Upload a street image and let the M1.13 vision model identify visible civic problems.
          </p>
        </div>
        <div className="model-chip"><span /> M1.13 YOLOv8n ready</div>
      </div>

      <div className="workspace-grid">
        <div className="control-column">
          <div className="panel upload-panel">
            <div className="panel-heading">
              <div className="icon-box"><Upload size={18} /></div>
              <div>
                <h3>Inspect an image</h3>
                <p>JPG, PNG, or WEBP · up to 10 MB</p>
              </div>
            </div>
            <label className="file-drop" htmlFor="image-upload">
              <FileImage size={30} strokeWidth={1.5} />
              <strong>{selectedFile ? 'Choose a different image' : 'Select an image'}</strong>
              <span>{selectedFile ? selectedFile.name : 'Your image stays in this session'}</span>
              <input
                id="image-upload"
                type="file"
                accept=".jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp"
                onChange={handleFileChange}
                disabled={isAnalyzing}
              />
            </label>
            {previewUrl && (
              <div className="preview-frame">
                <img src={previewUrl} alt="Selected civic inspection" />
              </div>
            )}
            <div className="action-row">
              <button className="primary-button" type="button" onClick={handleAnalyze} disabled={!selectedFile || isAnalyzing}>
                {isAnalyzing ? <LoaderCircle className="spin" size={18} /> : <ScanSearch size={18} />}
                {isAnalyzing ? 'Analyzing image' : 'Analyze image'}
                {!isAnalyzing && <ArrowRight size={16} />}
              </button>
              {(selectedFile || result || error) && (
                <button className="icon-button" type="button" onClick={resetWorkspace} disabled={isAnalyzing} title="Reset inspection">
                  <RotateCcw size={18} />
                  <span className="sr-only">Reset inspection</span>
                </button>
              )}
            </div>
            {error && (
              <div className="message error-message" role="alert">
                <AlertCircle size={18} /> <span>{error}</span>
              </div>
            )}
          </div>
          <div className="privacy-note"><CheckCircle2 size={16} /> No images are stored by this workspace.</div>
          <div className="panel location-panel">
            <div className="panel-heading">
              <div className="icon-box"><LocateFixed size={18} /></div>
              <div>
                <h3>Location</h3>
                <p>Only requested when you choose to use it</p>
              </div>
            </div>
            <button className="location-button" type="button" onClick={handleUseLocation} disabled={locationState === 'loading'}>
              {locationState === 'loading' ? <LoaderCircle className="spin" size={17} /> : <LocateFixed size={17} />}
              {locationState === 'loading' ? 'Finding your location' : location ? 'Refresh current location' : 'Use My Current Location'}
            </button>
            {location && (
              <div className="location-details">
                <p><span>Road</span><strong>{location.address?.road || 'Unavailable'}</strong></p>
                <p><span>Area</span><strong>{location.address?.area || 'Unavailable'}</strong></p>
                <p><span>City</span><strong>{location.address?.city || 'Unavailable'}</strong></p>
                <p><span>District</span><strong>{location.address?.district || 'Unavailable'}</strong></p>
                <p><span>State</span><strong>{location.address?.state || 'Unavailable'}</strong></p>
                <p><span>Country</span><strong>{location.address?.country || 'Unavailable'}</strong></p>
                <p><span>Jurisdiction context</span><strong>{location.address?.jurisdiction?.name || 'Unknown'}</strong></p>
                <p><span>Source</span><strong>{location.address?.source || 'Unavailable'}</strong></p>
                <p><span>Resolution</span><strong>{location.address?.resolution_status || 'Unresolved'}</strong></p>
                {!location.address?.road && <div className="location-inline-message">{location.address?.message || 'Coordinates available, but road information could not be resolved.'}</div>}
                <p><span>Coordinates</span><strong>{location.coordinates.latitude.toFixed(5)}, {location.coordinates.longitude.toFixed(5)}</strong></p>
                <p><span>Accuracy</span><strong>±{Math.round(location.coordinates.accuracy_meters)} m</strong></p>
              </div>
            )}
            {locationError && <div className="message error-message" role="alert"><AlertCircle size={17} /><span>{locationError}</span></div>}
            {(locationState === 'error' || locationState === 'partial') && (
              <button className="text-button" type="button" onClick={handleUseLocation}>Try again</button>
            )}
            {authority && (
              <div className="authority-panel">
                <div className="authority-title">
                  <strong>Responsible Authority</strong>
                  <span className={`authority-status ${authority.authority.authority_status}`}>
                    {authority.authority.authority_status.replaceAll('_', ' ')}
                  </span>
                </div>
                {authority.authority.authority_status === 'not_verified' && (
                  <p className="authority-warning">
                    CVKI could not verify the responsible authority from available official sources. Please verify the authority before submitting a government complaint.
                  </p>
                )}
                {authority.authority.road_owner && (
                  <p><span>Road owner</span><strong>{authority.authority.road_owner.name}</strong></p>
                )}
                {authority.authority.maintenance_authority && (
                  <p><span>Maintenance authority</span><strong>{authority.authority.maintenance_authority.name}</strong></p>
                )}
                {authority.authority.builder_or_contractor && (
                  <p><span>Builder / contractor</span><strong>{authority.authority.builder_or_contractor.name}</strong></p>
                )}
                {authority.authority.sources && authority.authority.sources.length > 0 && (
                  <div className="authority-sources-block">
                    <span className="section-mini-heading">Official Sources</span>
                    {authority.authority.sources.map((src) => (
                      <div key={src.source_id} className="official-source-item">
                        <strong>{src.source_name}</strong>
                        <small>{src.source_type?.replaceAll('_', ' ')}</small>
                        {src.source_url && (
                          <a href={src.source_url} target="_blank" rel="noopener noreferrer" className="official-source-link">
                            {src.source_url} <ExternalLink size={11} />
                          </a>
                        )}
                      </div>
                    ))}
                  </div>
                )}
                {authority.authority.evidence && authority.authority.evidence.length > 0 && (
                  <div className="authority-evidence">
                    <span className="section-mini-heading">Evidence</span>
                    {authority.authority.evidence.map((item, idx) => (
                      <strong key={`${item.source_name}-${idx}`}>
                        {item.source_name}: {item.claim}
                      </strong>
                    ))}
                  </div>
                )}
                {authority.authority.limitations && authority.authority.limitations.length > 0 && (
                  <div className="authority-limitations">
                    <span className="section-mini-heading">Limitations</span>
                    {authority.authority.limitations.map((item) => (
                      <strong key={item}>{item}</strong>
                    ))}
                  </div>
                )}
              </div>
            )}
            {authorityError && <div className="message error-message" role="alert"><AlertCircle size={17} /><span>{authorityError}</span></div>}
          </div>
        </div>

        <div className="panel result-panel">
          <div className="panel-heading result-heading">
            <div>
              <p className="eyebrow">Analysis output</p>
              <h3>{result ? `${result.total_detections} issue${result.total_detections === 1 ? '' : 's'} found` : 'Annotated result'}</h3>
            </div>
            {result && <span className="result-version">{result.model_version}</span>}
          </div>
          {result ? (
            <>
              <div className="annotated-frame">
                <img src={result.annotated_image} alt="Annotated detection result" />
              </div>
              {result.total_detections === 0 ? (
                <div className="message success-message"><CheckCircle2 size={18} /><span>No civic issue detected in this image.</span></div>
              ) : (
                <div className="detection-list">
                  {result.detections.map((detection, index) => (
                    <div className="detection-row" key={`${detection.class_id}-${index}`}>
                      <div className="detection-marker" />
                      <div className="detection-info">
                        <strong>{formatClassName(detection.class_name)}</strong>
                        <span>{detection.class_name}</span>
                      </div>
                      <div className="confidence-value">{Math.round(detection.confidence * 100)}%</div>
                      <div className="bbox-value">{detection.bbox.x1}, {detection.bbox.y1} → {detection.bbox.x2}, {detection.bbox.y2}</div>
                    </div>
                  ))}
                </div>
              )}
              {result.total_detections > 0 && (
                <div className="complaint-panel">
                  <div className="complaint-heading">
                    <div><p className="eyebrow">Citizen draft</p><h3>Prepare a complaint</h3></div>
                    <span className="draft-only-badge">Draft only</span>
                  </div>
                  <div className="complaint-controls">
                    <label htmlFor="complaint-language">Language</label>
                    <select id="complaint-language" value={complaintLanguage} onChange={(event) => setComplaintLanguage(event.target.value)} disabled={isGeneratingComplaint}>
                      <option value="en">English</option>
                      <option value="hi">Hindi</option>
                      <option value="hinglish">Hinglish</option>
                    </select>
                    <button className="secondary-button" type="button" onClick={handleGenerateComplaint} disabled={isGeneratingComplaint}>
                      {isGeneratingComplaint ? <LoaderCircle className="spin" size={16} /> : <FileImage size={16} />}
                      {complaint ? 'Regenerate' : 'Generate Complaint'}
                    </button>
                  </div>
                  {complaint && (
                    <>
                      <div className="complaint-meta"><span>{complaint.issue_label}</span><span>{complaint.severity} priority</span><span>{complaint.authority_status.replaceAll('_', ' ')}</span></div>
                      <input className="complaint-title-input" value={complaintTitle} onChange={(event) => setComplaintTitle(event.target.value)} aria-label="Editable complaint title" />
                      <textarea className="complaint-text" value={complaintText} onChange={(event) => setComplaintText(event.target.value)} aria-label="Editable complaint draft" />
                      <div className="complaint-actions">
                        <button className="secondary-button" type="button" onClick={handleCopyComplaint}>
                          <CheckCircle2 size={16} /> {copyStatus || 'Copy Complaint'}
                        </button>
                        <button className="secondary-button case-create-button" type="button" onClick={handleCreateCase} disabled={isCreatingCase}>
                          {isCreatingCase ? <LoaderCircle className="spin" size={16} /> : <CheckCircle2 size={16} />}
                          {isCreatingCase ? 'Creating CVKI Case' : 'Create CVKI Case'}
                        </button>
                      </div>
                      <span className="draft-note">M2.9 creates an editable draft only. M3.2/M3.3 stores an authenticated citizen case; it does not submit to government systems.</span>

                      {isLoadingIntelligence && (
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '11px', color: 'var(--muted)', marginTop: '8px' }}>
                          <LoaderCircle className="spin" size={13} /> Analyzing complaint intelligence and priority triage...
                        </div>
                      )}

                      {liveIntelligence && (
                        <div className="intelligence-card">
                          <div className="intelligence-header-row">
                            <span className="intelligence-title">
                              <Sparkles size={15} /> Civic Intelligence & Triage
                            </span>
                            {liveIntelligence.prio && (
                              <span className={`priority-badge-tag ${liveIntelligence.prio.priority_level.toLowerCase()}`}>
                                {liveIntelligence.prio.priority_level} — {liveIntelligence.prio.risk_level} Priority
                              </span>
                            )}
                            {intelligenceWarning && (
                              <div className="location-inline-message" role="status">{intelligenceWarning}</div>
                            )}
                          </div>

                          {liveIntelligence.prio && (
                            <div className="priority-preview-block">
                              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                <strong style={{ fontSize: '11px', color: 'var(--forest)' }}>Decision-Support Priority Score:</strong>
                                <span className="priority-score-pill">{liveIntelligence.prio.priority_score} / 100</span>
                              </div>
                              {liveIntelligence.prio.reasons?.length > 0 && (
                                <div className="priority-reasons-box" style={{ marginTop: '6px' }}>
                                  <span style={{ fontSize: '11px', fontWeight: '600' }}>Why this priority?</span>
                                  <ul className="reasons-list">
                                    {liveIntelligence.prio.reasons.map((r, idx) => (
                                      <li key={idx}>{r}</li>
                                    ))}
                                  </ul>
                                </div>
                              )}
                            </div>
                          )}

                          {liveIntelligence.dup && (
                            <div className="duplicate-preview-block" style={{ borderTop: '1px solid #eef3ec', paddingTop: '8px' }}>
                              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                <strong style={{ fontSize: '11px', color: 'var(--forest)' }}>Duplicate Report Analysis:</strong>
                                <span className={`duplicate-badge ${liveIntelligence.dup.classification}`}>
                                  {liveIntelligence.dup.classification.replaceAll('_', ' ')}
                                </span>
                              </div>
                              <p className="intelligence-explanation" style={{ marginTop: '4px' }}>
                                {liveIntelligence.dup.reason}
                              </p>
                            </div>
                          )}

                          {liveIntelligence.nlp && (
                            <div className="nlp-preview-block" style={{ borderTop: '1px solid #eef3ec', paddingTop: '8px' }}>
                              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                                <strong style={{ fontSize: '11px', color: 'var(--forest)' }}>NLP Text Intelligence:</strong>
                                <span style={{ fontSize: '11px', color: 'var(--muted)', background: '#f1f5f9', padding: '2px 6px', borderRadius: '4px' }}>
                                  Language: {liveIntelligence.nlp.detected_language?.toUpperCase()} ({Math.round(liveIntelligence.nlp.confidence * 100)}%)
                                </span>
                              </div>
                              {(liveIntelligence.nlp.severity_signals?.length > 0 || liveIntelligence.nlp.risk_signals?.length > 0) && (
                                <div className="signals-tag-row" style={{ marginBottom: '6px' }}>
                                  <span>Signals Detected:</span>
                                  {liveIntelligence.nlp.severity_signals.map((s, idx) => (
                                    <span key={`sev-${idx}`} className="signal-chip severity">{s}</span>
                                  ))}
                                  {liveIntelligence.nlp.risk_signals.map((s, idx) => (
                                    <span key={`risk-${idx}`} className="signal-chip risk">{s}</span>
                                  ))}
                                </div>
                              )}
                              {liveIntelligence.nlp.extracted_entities?.length > 0 && (
                                <div className="extracted-entities-box" style={{ marginBottom: '6px' }}>
                                  <span style={{ fontSize: '11px', color: 'var(--muted)' }}>Extracted Text Entities:</span>
                                  <div className="entity-chips">
                                    {liveIntelligence.nlp.extracted_entities.map((e, idx) => (
                                      <span key={idx} className="entity-chip">{e.name} ({e.type})</span>
                                    ))}
                                  </div>
                                </div>
                              )}
                              <p className="intelligence-explanation">
                                {liveIntelligence.nlp.explanation}
                              </p>
                            </div>
                          )}
                        </div>
                      )}

                      {complaint.guidance && (
                        <div className="official-guidance-card">
                          <div className="guidance-header-row">
                            <div>
                              <span className="eyebrow-accent">M3.5 Citizen Guidance</span>
                              <h4>Official Government Submission Process</h4>
                            </div>
                            <span className="guidance-status-tag">Government Submission: Not Submitted</span>
                          </div>
                          <p className="guidance-channel">
                            <span>Recommended Channel:</span>
                            <strong>{complaint.guidance.recommended_channel}</strong>
                          </p>
                          {complaint.guidance.official_portal_url && (
                            <p className="guidance-portal">
                              <span>Official Portal:</span>
                              <a
                                href={complaint.guidance.official_portal_url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="official-portal-link"
                              >
                                {complaint.guidance.official_portal_url} <ExternalLink size={12} />
                              </a>
                            </p>
                          )}
                          <div className="guidance-steps-box">
                            <strong>Step-by-Step Instructions ({complaint.guidance.language?.toUpperCase()}):</strong>
                            <ol className="guidance-steps-ordered">
                              {complaint.guidance.steps.map((st, idx) => (
                                <li key={idx}>{st}</li>
                              ))}
                            </ol>
                          </div>
                          <div className="guidance-prep-columns">
                            <div className="guidance-prep-col">
                              <strong>What to Attach:</strong>
                              <ul>
                                {complaint.guidance.what_to_attach.map((item, idx) => (
                                  <li key={idx}>{item}</li>
                                ))}
                              </ul>
                            </div>
                            <div className="guidance-prep-col">
                              <strong>What to Write:</strong>
                              <ul>
                                {complaint.guidance.what_to_write.map((item, idx) => (
                                  <li key={idx}>{item}</li>
                                ))}
                              </ul>
                            </div>
                          </div>
                        </div>
                      )}
                      {cvkiCase && (
                        <div className="case-summary">
                          <p><span>CVKI Reference ID</span><strong>{cvkiCase.reference_id}</strong></p>
                          <p><span>Status</span><strong>Submitted to CVKI</strong></p>
                          <p><span>External Government Submission</span><strong>Government Submission: Not Submitted</strong></p>
                          <p><span>Follow-up</span><strong>{cvkiCase.follow_up?.guidance || 'Track status in My Complaints'}</strong></p>
                          <button className="text-button" type="button" onClick={handleViewCaseStatus}>View Case Status</button>
                          {caseStatus && (
                            <div className="case-status-result">
                              <strong>{caseStatus.status.replaceAll('_', ' ')}</strong>
                              <span>{caseStatus.status_description}</span>
                            </div>
                          )}
                        </div>
                      )}
                    </>
                  )}
                  {complaintError && <div className="message error-message" role="alert"><AlertCircle size={17} /><span>{complaintError}</span></div>}
                  {caseError && <div className="message error-message" role="alert"><AlertCircle size={17} /><span>{caseError}</span></div>}
                </div>
              )}
            </>
          ) : (
            <div className="result-empty">
              <div className="empty-icon"><ScanSearch size={28} /></div>
              <h4>Your annotated image will appear here</h4>
              <p>Select an image, then run analysis to see model-detected civic issues.</p>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

function MyComplaintsView({ currentUser, onOpenAuth, onLogout }) {
  const [cases, setCases] = useState([]);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const [loading, setLoading] = useState(Boolean(currentUser));
  const [error, setError] = useState('');
  const [selectedReferenceId, setSelectedReferenceId] = useState(null);

  const limit = 5;

  async function fetchHistory(pageNum = page) {
    if (!currentUser) return;
    setLoading(true);
    setError('');
    try {
      const response = await getMyCvkiCases(pageNum, limit);
      setCases(response.items || []);
      setPage(response.page || pageNum);
      setTotal(response.total || 0);
      setTotalPages(response.pages || 1);
    } catch (err) {
      if (err instanceof ComplaintCaseApiError && err.message.includes('Authentication')) {
        setError('Your session has expired. Please sign in again.');
      } else {
        setError(err instanceof ComplaintCaseApiError ? err.message : 'Could not retrieve complaint history.');
      }
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    let isMounted = true;
    if (!currentUser) return undefined;

    getMyCvkiCases(1, limit)
      .then((response) => {
        if (!isMounted) return;
        setCases(response.items || []);
        setPage(1);
        setTotal(response.total || 0);
        setTotalPages(response.pages || 1);
      })
      .catch((err) => {
        if (!isMounted) return;
        if (err instanceof ComplaintCaseApiError && err.message.includes('Authentication')) {
          setError('Your session has expired. Please sign in again.');
        } else {
          setError(err instanceof ComplaintCaseApiError ? err.message : 'Could not retrieve complaint history.');
        }
      })
      .finally(() => {
        if (isMounted) setLoading(false);
      });

    return () => {
      isMounted = false;
    };
  }, [currentUser]);

  if (!currentUser) {
    return (
      <div className="simple-page unauthorized-page">
        <p className="eyebrow"><User size={16} /> Citizen Authentication Required</p>
        <h2>My Complaints</h2>
        <p className="intro-copy">
          Please sign in to view your CVKI complaint history and track your reported cases.
        </p>
        <div className="auth-prompt-actions">
          <button className="primary-button" type="button" onClick={() => onOpenAuth('login')}>
            <LogIn size={16} /> Sign In
          </button>
          <button className="secondary-button" type="button" onClick={() => onOpenAuth('register')}>
            <UserPlus size={16} /> Register
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="history-page">
      <div className="history-header">
        <div>
          <p className="eyebrow"><User size={15} /> Authenticated Citizen Dashboard</p>
          <h2>My Complaints</h2>
          <p className="user-indicator">Logged in as: <strong>{currentUser.email}</strong></p>
        </div>
        <div className="history-header-actions">
          <button
            className="secondary-button"
            type="button"
            onClick={() => fetchHistory(page)}
            disabled={loading}
            title="Reload cases"
          >
            <RefreshCw className={loading ? 'spin' : ''} size={15} />
            <span>Refresh</span>
          </button>
          <button
            className="secondary-button logout-btn"
            type="button"
            onClick={onLogout}
            title="Sign out of your account"
          >
            <LogOut size={15} />
            <span>Logout</span>
          </button>
        </div>
      </div>

      {error && (
        <div className="message error-message" role="alert">
          <AlertCircle size={18} />
          <span>{error}</span>
          <button className="text-button retry-btn" type="button" onClick={() => fetchHistory(page)}>
            Try again
          </button>
        </div>
      )}

      {loading && cases.length === 0 ? (
        <div className="history-loading">
          <LoaderCircle className="spin" size={32} />
          <p>Loading your complaint history...</p>
        </div>
      ) : cases.length === 0 && !error ? (
        <div className="history-empty-card">
          <div className="empty-icon"><ScanSearch size={28} /></div>
          <h3>You have not created any CVKI cases yet.</h3>
          <p>When you inspect a street problem and create a case, it will appear here for you to track.</p>
          <Link to="/" className="primary-button empty-action">
            <ScanSearch size={16} /> Inspect Street Issue
          </Link>
        </div>
      ) : cases.length > 0 ? (
        <div className="history-table-container">
          <div className="cases-grid">
            {cases.map((c) => (
              <div key={c.reference_id} className="case-card">
                <div className="case-card-header">
                  <span className="case-ref-tag">{c.reference_id}</span>
                  <span className="case-date-tag">{formatDate(c.created_at)}</span>
                </div>

                <div className="case-card-body">
                  <h4 className="case-issue-title">{c.issue_label || formatClassName(c.issue_class || 'Civic Issue')}</h4>
                  <p className="case-loc-summary">
                    📍 {formatLocationSummary(c.location_summary)}
                  </p>
                  <p className="case-complaint-title">
                    &ldquo;{c.title}&rdquo;
                  </p>
                </div>

                <div className="case-card-meta">
                  <div className="status-pill-group">
                    <span className="status-pill submitted">
                      {formatReadinessStatus(c.status)}
                    </span>
                    <span className="status-pill external-not-submitted">
                      Government Submission: {formatReadinessStatus(c.external_submission_status)}
                    </span>
                  </div>
                  <button
                    className="secondary-button view-detail-btn"
                    type="button"
                    onClick={() => setSelectedReferenceId(c.reference_id)}
                  >
                    View Details
                  </button>
                </div>
              </div>
            ))}
          </div>

          <div className="pagination-bar">
            <span className="pagination-info">
              Showing page <strong>{page}</strong> of <strong>{totalPages}</strong> ({total} total case{total === 1 ? '' : 's'})
            </span>
            <div className="pagination-buttons">
              <button
                className="icon-button"
                type="button"
                onClick={() => fetchHistory(page - 1)}
                disabled={page <= 1 || loading}
                title="Previous page"
              >
                <ChevronLeft size={16} />
                <span className="sr-only">Previous page</span>
              </button>
              <button
                className="icon-button"
                type="button"
                onClick={() => fetchHistory(page + 1)}
                disabled={page >= totalPages || loading}
                title="Next page"
              >
                <ChevronRight size={16} />
                <span className="sr-only">Next page</span>
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {selectedReferenceId && (
        <CaseDetailModal
          referenceId={selectedReferenceId}
          onClose={() => setSelectedReferenceId(null)}
        />
      )}
    </div>
  );
}

function RoleProtectedRoute({ currentUser, allowedRoles, children, onOpenAuth }) {
  if (!currentUser) {
    return (
      <div className="role-access-state auth-required">
        <div className="role-access-card">
          <AlertCircle size={44} className="role-access-icon warning" />
          <h2>Sign In Required</h2>
          <p>Authentication is required to access this portal.</p>
          <div className="role-access-actions">
            <button
              type="button"
              className="primary-button"
              onClick={() => onOpenAuth('login')}
            >
              <LogIn size={15} /> Sign In
            </button>
            <Link to="/" className="ghost-button">
              Return to Field Vision
            </Link>
          </div>
        </div>
      </div>
    );
  }

  const role = currentUser.role || 'citizen';
  if (!allowedRoles.includes(role)) {
    return (
      <div className="role-access-state access-denied">
        <div className="role-access-card">
          <AlertCircle size={44} className="role-access-icon error" />
          <h2>Access Denied</h2>
          <p className="access-denied-message">
            Your account (<strong>{currentUser.email}</strong>) has the <strong>{role}</strong> role and is not authorized to access this portal.
          </p>
          <p className="access-denied-subtext">
            Required role: <strong>{allowedRoles.join(' or ')}</strong>.
          </p>
          <div className="role-access-actions">
            <Link to="/" className="primary-button">
              Return to Field Vision
            </Link>
          </div>
        </div>
      </div>
    );
  }

  return children;
}

function AdminCaseDetailModal({ referenceId, onClose, onAssignmentChanged }) {
  const [caseData, setCaseData] = useState(null);
  const [authorities, setAuthorities] = useState([]);
  const [selectedAuthorityId, setSelectedAuthorityId] = useState('');
  const [targetStatus, setTargetStatus] = useState('');
  const [statusReason, setStatusReason] = useState('');
  const [statusUpdating, setStatusUpdating] = useState(false);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [error, setError] = useState(null);
  const [actionMessage, setActionMessage] = useState(null);

  useEffect(() => {
    let isMounted = true;
    async function loadData() {
      setLoading(true);
      setError(null);
      try {
        const [cData, authList] = await Promise.all([
          fetchAdminCaseDetail(referenceId),
          fetchAuthorities().catch(() => []),
        ]);
        if (!isMounted) return;
        setCaseData(cData);
        setAuthorities(authList);
        if (cData.assignment?.assigned_to_user_id) {
          setSelectedAuthorityId(cData.assignment.assigned_to_user_id);
        } else if (authList.length > 0) {
          setSelectedAuthorityId(authList[0].user_id);
        }
      } catch (err) {
        if (!isMounted) return;
        setError(err instanceof AdminApiError ? err.message : 'Failed to load case details.');
      } finally {
        if (isMounted) setLoading(false);
      }
    }
    loadData();
    return () => { isMounted = false; };
  }, [referenceId]);

  async function handleAssign() {
    if (!selectedAuthorityId) {
      setError('Please select an authority account.');
      return;
    }
    const targetAuth = authorities.find((a) => a.user_id === selectedAuthorityId);
    const label = targetAuth ? targetAuth.email : selectedAuthorityId;
    if (!window.confirm(`Are you sure you want to assign case ${referenceId} to ${label}?`)) {
      return;
    }

    setActionLoading(true);
    setActionMessage(null);
    setError(null);
    try {
      const updated = await assignCase(referenceId, selectedAuthorityId);
      setCaseData(updated);
      setActionMessage(`Case successfully assigned to ${updated.assignment?.assigned_to_email || label}.`);
      if (onAssignmentChanged) onAssignmentChanged(updated);
    } catch (err) {
      setError(err instanceof AdminApiError ? err.message : 'Assignment operation failed.');
    } finally {
      setActionLoading(false);
    }
  }

  async function handleUnassign() {
    if (!window.confirm(`Are you sure you want to remove assignment from case ${referenceId}?`)) {
      return;
    }

    setActionLoading(true);
    setActionMessage(null);
    setError(null);
    try {
      const updated = await unassignCase(referenceId);
      setCaseData(updated);
      setActionMessage('Case successfully unassigned.');
      if (onAssignmentChanged) onAssignmentChanged(updated);
    } catch (err) {
      setError(err instanceof AdminApiError ? err.message : 'Unassign operation failed.');
    } finally {
      setActionLoading(false);
    }
  }

  async function handleStatusUpdate(e) {
    e?.preventDefault();
    if (!targetStatus) {
      setError('Please select a target status.');
      return;
    }
    if (targetStatus === 'closed' && !statusReason.trim()) {
      setError('A reason is required when closing a case.');
      return;
    }
    setStatusUpdating(true);
    setActionMessage(null);
    setError(null);
    try {
      const updated = await updateCaseStatus(referenceId, targetStatus, statusReason.trim());
      setCaseData(updated);
      setActionMessage(`Case status successfully updated to "${updated.status}".`);
      setTargetStatus('');
      setStatusReason('');
      if (onAssignmentChanged) onAssignmentChanged(updated);
    } catch (err) {
      setError(err instanceof AdminApiError ? err.message : 'Status update failed.');
    } finally {
      setStatusUpdating(false);
    }
  }

  const isAssigned = caseData?.assignment?.assignment_status === 'assigned' && Boolean(caseData?.assignment?.assigned_to_user_id);
  const allowedTransitions = caseData ? ({
    submitted_to_cvki: ['assigned', 'under_review', 'in_progress', 'closed'],
    under_review: ['assigned', 'in_progress', 'resolved', 'closed'],
    assigned: ['in_progress', 'submitted_to_cvki', 'closed'],
    in_progress: ['resolved', 'assigned', 'closed'],
    resolved: ['closed', 'in_progress'],
    closed: [],
    draft: ['submitted_to_cvki', 'closed'],
  }[caseData.status] || []) : [];

  return (
    <div className="modal-backdrop" onClick={onClose} role="dialog" aria-modal="true" aria-labelledby="admin-case-detail-title">
      <div className="modal-card admin-case-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div className="admin-modal-title-group">
            <h3 id="admin-case-detail-title">Case Operational Review</h3>
            <span className="reference-pill">{referenceId}</span>
          </div>
          <button className="icon-close-btn" type="button" onClick={onClose} aria-label="Close dialog">
            <X size={18} />
          </button>
        </div>

        {loading ? (
          <div className="modal-loading-state">
            <LoaderCircle size={24} className="spin-slow" />
            <span>Loading operational case details...</span>
          </div>
        ) : error && !caseData ? (
          <div className="error-banner">
            <AlertCircle size={16} />
            <span>{error}</span>
          </div>
        ) : caseData ? (
          <div className="admin-case-body">
            <LifecycleProgressBar currentStatus={caseData.status} />

            {error && (
              <div className="error-banner">
                <AlertCircle size={16} />
                <span>{error}</span>
              </div>
            )}
            {actionMessage && (
              <div className="success-banner">
                <CheckCircle2 size={16} />
                <span>{actionMessage}</span>
              </div>
            )}

            {/* Status Workflow Section (M4.5) */}
            <div className="admin-section-box status-workflow-box">
              <div className="section-box-header">
                <div className="section-title-wrap">
                  <Clock size={18} />
                  <h4>Status Workflow &amp; Lifecycle Transition (M4.5)</h4>
                </div>
                <span className="status-chip font-bold">{caseData.status}</span>
              </div>

              {caseData.status === 'closed' ? (
                <p className="text-muted" style={{ margin: '8px 0 0', fontSize: '12px' }}>
                  This case is closed (terminal state). Lifecycle is complete and immutable.
                </p>
              ) : allowedTransitions.length === 0 ? (
                <p className="text-muted" style={{ margin: '8px 0 0', fontSize: '12px' }}>
                  No transitions currently available for this status.
                </p>
              ) : (
                <form onSubmit={handleStatusUpdate} className="status-controls-row">
                  <select
                    className="status-select"
                    value={targetStatus}
                    onChange={(e) => setTargetStatus(e.target.value)}
                    disabled={statusUpdating}
                    required
                  >
                    <option value="">Choose Next Status...</option>
                    {allowedTransitions.map((st) => (
                      <option key={st} value={st}>
                        Transition to: {st.replaceAll('_', ' ').toUpperCase()}
                      </option>
                    ))}
                  </select>
                  <input
                    type="text"
                    className="status-reason-input"
                    placeholder={targetStatus === 'closed' ? 'Reason for closing (required)...' : 'Operational reason (optional)...'}
                    value={statusReason}
                    onChange={(e) => setStatusReason(e.target.value)}
                    disabled={statusUpdating}
                  />
                  <button
                    type="submit"
                    className="primary-button small-btn"
                    disabled={statusUpdating || !targetStatus || (targetStatus === 'closed' && !statusReason.trim())}
                  >
                    {statusUpdating ? <LoaderCircle size={14} className="spin-slow" /> : <CheckCircle2 size={14} />} Transition Status
                  </button>
                </form>
              )}
            </div>

            {/* Assignment Section (M4.4) */}
            <div className="admin-section-box assignment-section-box">
              <div className="section-box-header">
                <div className="section-title-wrap">
                  <UserCheck size={18} />
                  <h4>Case Assignment &amp; Routing (M4.4)</h4>
                </div>
                <span className={`assignment-status-badge ${isAssigned ? 'assigned' : 'unassigned'}`}>
                  {isAssigned ? 'Assigned' : 'Unassigned'}
                </span>
              </div>

              {isAssigned ? (
                <div className="assignment-current-info">
                  <div className="info-grid-2">
                    <div>
                      <span className="info-label">Assigned Authority:</span>
                      <strong className="info-value text-accent">{caseData.assignment.assigned_to_email || caseData.assignment.assigned_to_user_id}</strong>
                    </div>
                    <div>
                      <span className="info-label">Assigned At:</span>
                      <span className="info-value">{formatDate(caseData.assignment.assigned_at)}</span>
                    </div>
                  </div>

                  <div className="reassign-controls">
                    <label htmlFor="reassign-authority-select" className="control-label">Reassign to another Authority:</label>
                    <div className="inline-action-row">
                      <select
                        id="reassign-authority-select"
                        className="admin-select"
                        value={selectedAuthorityId}
                        onChange={(e) => setSelectedAuthorityId(e.target.value)}
                        disabled={actionLoading || authorities.length === 0}
                      >
                        {authorities.map((a) => (
                          <option key={a.user_id} value={a.user_id}>
                            {a.email} ({a.user_id})
                          </option>
                        ))}
                      </select>
                      <button
                        type="button"
                        className="primary-button small-btn"
                        onClick={handleAssign}
                        disabled={actionLoading || authorities.length === 0 || selectedAuthorityId === caseData.assignment.assigned_to_user_id}
                      >
                        {actionLoading ? <LoaderCircle size={14} className="spin-slow" /> : <RefreshCw size={14} />} Reassign
                      </button>
                      <button
                        type="button"
                        className="ghost-button danger small-btn"
                        onClick={handleUnassign}
                        disabled={actionLoading}
                      >
                        {actionLoading ? <LoaderCircle size={14} className="spin-slow" /> : <UserX size={14} />} Unassign
                      </button>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="assignment-assign-form">
                  <p className="section-hint">This case is currently unassigned. Route to an operational authority team member:</p>
                  <div className="inline-action-row">
                    <select
                      id="assign-authority-select"
                      className="admin-select"
                      value={selectedAuthorityId}
                      onChange={(e) => setSelectedAuthorityId(e.target.value)}
                      disabled={actionLoading || authorities.length === 0}
                    >
                      {authorities.length === 0 && <option value="">No authority accounts available</option>}
                      {authorities.map((a) => (
                        <option key={a.user_id} value={a.user_id}>
                          {a.email} ({a.user_id})
                        </option>
                      ))}
                    </select>
                    <button
                      type="button"
                      className="primary-button small-btn"
                      onClick={handleAssign}
                      disabled={actionLoading || authorities.length === 0 || !selectedAuthorityId}
                    >
                      {actionLoading ? <LoaderCircle size={14} className="spin-slow" /> : <UserCheck size={14} />} Assign Case
                    </button>
                  </div>
                </div>
              )}
            </div>

            {/* Case Overview Grid */}
            <div className="admin-case-details-grid">
              {/* Left Column: Issue & Complaint */}
              <div className="details-col">
                <div className="admin-section-box">
                  <h4>Civic Issue</h4>
                  <div className="detail-row">
                    <span className="detail-key">Category:</span>
                    <strong className="detail-val">{formatClassName(caseData.issue.class_name)}</strong>
                  </div>
                  <div className="detail-row">
                    <span className="detail-key">Label:</span>
                    <span className="detail-val">{caseData.issue.label}</span>
                  </div>
                  <div className="detail-row">
                    <span className="detail-key">CV Confidence:</span>
                    <span className="detail-val">{(caseData.issue.confidence * 100).toFixed(1)}%</span>
                  </div>
                  <div className="detail-row">
                    <span className="detail-key">Reported Severity:</span>
                    <span className="detail-val">{caseData.issue.severity}</span>
                  </div>
                  <div className="detail-row">
                    <span className="detail-key">Status:</span>
                    <span className="detail-val"><strong className="status-chip">{caseData.status}</strong></span>
                  </div>
                </div>

                <div className="admin-section-box">
                  <h4>Citizen Complaint</h4>
                  <p className="complaint-title-text">{caseData.complaint.title}</p>
                  <p className="complaint-desc-text">{caseData.complaint.description}</p>
                  <div className="detail-row">
                    <span className="detail-key">Language:</span>
                    <span className="detail-val">{caseData.complaint.language?.toUpperCase() || 'EN'}</span>
                  </div>
                </div>

                <div className="admin-section-box">
                  <h4>Location &amp; Authority</h4>
                  <p className="location-text">{formatLocationSummary(caseData.location)}</p>
                  <div className="detail-row">
                    <span className="detail-key">Jurisdiction:</span>
                    <span className="detail-val">{caseData.authority?.authority_name || 'Unassigned Jurisdiction'}</span>
                  </div>
                  <div className="detail-row">
                    <span className="detail-key">Department:</span>
                    <span className="detail-val">{caseData.authority?.department || 'Municipal Operations'}</span>
                  </div>
                </div>
              </div>

              {/* Right Column: AI Intelligence & Submission */}
              <div className="details-col">
                <div className="admin-section-box">
                  <h4>Triage Priority (M3.8)</h4>
                  {caseData.priority_analysis ? (
                    <div>
                      <div className="priority-indicator-row">
                        <span className={`priority-badge priority-${caseData.priority_analysis.priority_level}`}>
                          {caseData.priority_analysis.priority_level}
                        </span>
                        <span className="priority-score-text">
                          Score: <strong>{caseData.priority_analysis.priority_score.toFixed(1)}/100</strong> ({caseData.priority_analysis.risk_level})
                        </span>
                      </div>
                      {caseData.priority_analysis.reasons?.length > 0 && (
                        <ul className="reasons-list">
                          {caseData.priority_analysis.reasons.map((r, i) => (
                            <li key={i}>{r}</li>
                          ))}
                        </ul>
                      )}
                    </div>
                  ) : (
                    <p className="text-muted">No priority analysis recorded.</p>
                  )}
                </div>

                <div className="admin-section-box">
                  <h4>Duplicate Intelligence (M3.7)</h4>
                  {caseData.duplicate_analysis ? (
                    <div>
                      <div className="detail-row">
                        <span className="detail-key">Classification:</span>
                        <span className="detail-val"><strong>{caseData.duplicate_analysis.classification}</strong></span>
                      </div>
                      <div className="detail-row">
                        <span className="detail-key">Similarity:</span>
                        <span className="detail-val">{(caseData.duplicate_analysis.similarity_score * 100).toFixed(1)}%</span>
                      </div>
                      {caseData.duplicate_analysis.matched_reference_id && (
                        <div className="detail-row">
                          <span className="detail-key">Matched Reference:</span>
                          <span className="detail-val font-mono">{caseData.duplicate_analysis.matched_reference_id}</span>
                        </div>
                      )}
                    </div>
                  ) : (
                    <p className="text-muted">No duplicate evaluation stored.</p>
                  )}
                </div>

                <div className="admin-section-box">
                  <h4>Government Dispatch (M3.10)</h4>
                  <div className="detail-row">
                    <span className="detail-key">Dispatch Status:</span>
                    <span className="detail-val">{caseData.government_submission ? 'Prepared' : 'Not Prepared'}</span>
                  </div>
                  <div className="detail-row">
                    <span className="detail-key">External Portal Status:</span>
                    <span className="detail-val">{caseData.external_submission_status || 'not_submitted'}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}

function AdminMapView({ onInspectCase, fetchCases = fetchMapCases }) {
  const [mapCases, setMapCases] = useState([]);
  const [totalMapped, setTotalMapped] = useState(0);
  const [unmappedCount, setUnmappedCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const [priorityFilter, setPriorityFilter] = useState('');
  const [issueFilter, setIssueFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [daysBack, setDaysBack] = useState('');

  const mapContainerRef = useRef(null);
  const mapObjRef = useRef(null);
  const markersLayerRef = useRef(null);

  useEffect(() => {
    let isMounted = true;
    setLoading(true);
    setError(null);

    let createdFrom = undefined;
    if (daysBack) {
      const d = new Date();
      d.setDate(d.getDate() - parseInt(daysBack, 10));
      createdFrom = d.toISOString();
    }

    fetchCases({
      priority: priorityFilter || undefined,
      issue: issueFilter || undefined,
      status: statusFilter || undefined,
      created_from: createdFrom,
      limit: 300,
    })
      .then((res) => {
        if (!isMounted) return;
        const items = res.mapped_cases || [];
        setMapCases(items);
        setTotalMapped(res.total_mapped ?? items.length);
        setUnmappedCount(res.unmapped_cases_count ?? 0);
        setLoading(false);
      })
      .catch((err) => {
        if (!isMounted) return;
        setMapCases([]);
        setTotalMapped(0);
        setUnmappedCount(0);
        setError(err?.message || 'Failed to fetch map data.');
        setLoading(false);
      });

    return () => { isMounted = false; };
  }, [fetchCases, priorityFilter, issueFilter, statusFilter, daysBack]);

  useEffect(() => {
    if (!mapContainerRef.current) return;
    if (!mapObjRef.current) {
      const map = L.map(mapContainerRef.current).setView([20.5937, 78.9629], 5);
      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 19,
        attribution: '&copy; OpenStreetMap contributors',
      }).addTo(map);
      const markersLayer = L.layerGroup().addTo(map);
      mapObjRef.current = map;
      markersLayerRef.current = markersLayer;
    }

    return () => {
      if (mapObjRef.current) {
        mapObjRef.current.remove();
        mapObjRef.current = null;
        markersLayerRef.current = null;
      }
    };
  }, []);

  useEffect(() => {
    if (!mapObjRef.current || !markersLayerRef.current) return;
    const map = mapObjRef.current;
    const layer = markersLayerRef.current;
    layer.clearLayers();

    if (mapCases.length === 0) return;

    const priorityColors = {
      P1: '#dc2626',
      P2: '#ea580c',
      P3: '#d97706',
      P4: '#16a34a',
    };

    const latLngs = [];

    mapCases.forEach((c) => {
      const lat = c.latitude;
      const lon = c.longitude;
      if (!hasUsableMapCoordinates(c)) return;
      latLngs.push([lat, lon]);

      const pLevel = c.priority || 'P3';
      const color = priorityColors[pLevel] || '#164b3a';

      const circle = L.circleMarker([lat, lon], {
        radius: 9,
        fillColor: color,
        color: '#ffffff',
        weight: 2,
        opacity: 1,
        fillOpacity: 0.9,
      });

      const popupDiv = document.createElement('div');
      popupDiv.style.minWidth = '180px';
      const popupContent = document.createElement('div');
      popupContent.style.fontFamily = 'inherit';
      popupContent.style.fontSize = '12px';
      popupContent.style.lineHeight = '1.4';

      const reference = document.createElement('div');
      reference.textContent = c.reference_id || 'CVKI case';
      Object.assign(reference.style, {
        fontWeight: '800',
        fontFamily: 'monospace',
        color: '#0f172a',
        marginBottom: '2px',
      });
      popupContent.appendChild(reference);

      const issue = document.createElement('div');
      issue.textContent = c.issue_label || c.issue || 'Civic Issue';
      Object.assign(issue.style, {
        fontWeight: '700',
        color: '#1e293b',
        marginBottom: '4px',
      });
      popupContent.appendChild(issue);

      const address = document.createElement('div');
      address.textContent = [c.road, c.city].filter(Boolean).join(', ');
      Object.assign(address.style, {
        fontSize: '11px',
        color: '#64748b',
        marginBottom: '6px',
      });
      popupContent.appendChild(address);

      const badges = document.createElement('div');
      Object.assign(badges.style, { display: 'flex', gap: '6px', marginBottom: '8px' });
      const priorityBadge = document.createElement('span');
      priorityBadge.textContent = pLevel;
      Object.assign(priorityBadge.style, {
        background: color,
        color: '#fff',
        padding: '2px 6px',
        borderRadius: '4px',
        fontSize: '10px',
        fontWeight: '800',
      });
      const statusBadge = document.createElement('span');
      statusBadge.textContent = c.status || 'Unknown status';
      Object.assign(statusBadge.style, {
        background: '#e2e8f0',
        color: '#1e293b',
        padding: '2px 6px',
        borderRadius: '4px',
        fontSize: '10px',
        fontWeight: '600',
      });
      badges.append(priorityBadge, statusBadge);
      popupContent.appendChild(badges);

      const inspectButton = document.createElement('button');
      inspectButton.type = 'button';
      inspectButton.textContent = 'Inspect Case Details';
      Object.assign(inspectButton.style, {
        width: '100%',
        background: '#164b3a',
        color: '#ffffff',
        border: '0',
        padding: '5px 8px',
        borderRadius: '5px',
        fontSize: '11px',
        fontWeight: '700',
        cursor: 'pointer',
      });
      inspectButton.addEventListener('click', () => {
        if (onInspectCase) onInspectCase(c.reference_id);
      });
      popupContent.appendChild(inspectButton);
      popupDiv.appendChild(popupContent);

      circle.bindPopup(popupDiv);
      circle.addTo(layer);
    });

    if (latLngs.length > 0) {
      const bounds = L.latLngBounds(latLngs);
      map.fitBounds(bounds, { padding: [40, 40], maxZoom: 14 });
    }
  }, [mapCases, onInspectCase]);

  function handleResetFilters() {
    setPriorityFilter('');
    setIssueFilter('');
    setStatusFilter('');
    setDaysBack('');
  }

  return (
    <div className="map-view-container">
      <div className="map-controls-card">
        <div className="section-head-bar" style={{ margin: 0 }}>
          <div>
            <h3>Civic Operations Spatial Map (M4.6)</h3>
            <p className="section-desc">Real-time geospatial dispatch map plotting confirmed civic complaints with coordinate validation.</p>
          </div>
          <div className="map-stats-row">
            <span className="map-stat-badge">Plotted: <strong>{totalMapped}</strong></span>
            <span className="map-stat-badge" title="Cases missing GPS or coordinates outside valid bounding box">
              Unmapped / No GPS: <strong>{unmappedCount}</strong>
            </span>
          </div>
        </div>

        <div className="map-filter-row">
          <select
            className="admin-filter-select"
            value={priorityFilter}
            onChange={(e) => setPriorityFilter(e.target.value)}
          >
            <option value="">All Priorities</option>
            <option value="P1">P1 Critical</option>
            <option value="P2">P2 High</option>
            <option value="P3">P3 Medium</option>
            <option value="P4">P4 Low</option>
          </select>

          <select
            className="admin-filter-select"
            value={issueFilter}
            onChange={(e) => setIssueFilter(e.target.value)}
          >
            <option value="">All Issues</option>
            <option value="open_damaged_manhole">Open Manhole</option>
            <option value="damaged_missing_road_sign">Road Sign</option>
            <option value="road_waterlogging">Waterlogging</option>
            <option value="other_civic_issue">Other</option>
          </select>

          <select
            className="admin-filter-select"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
          >
            <option value="">All Statuses</option>
            <option value="submitted_to_cvki">Submitted</option>
            <option value="assigned">Assigned</option>
            <option value="in_progress">In Progress</option>
            <option value="resolved">Resolved</option>
            <option value="closed">Closed</option>
            <option value="under_review">Under Review</option>
          </select>

          <select
            className="admin-filter-select"
            value={daysBack}
            onChange={(e) => setDaysBack(e.target.value)}
          >
            <option value="">All Time</option>
            <option value="7">Last 7 Days</option>
            <option value="30">Last 30 Days</option>
            <option value="90">Last 90 Days</option>
          </select>

          {(priorityFilter || issueFilter || statusFilter || daysBack) && (
            <button
              type="button"
              className="ghost-button small-btn"
              onClick={handleResetFilters}
            >
              Reset Filters
            </button>
          )}

          {loading && <LoaderCircle size={16} className="spin-slow" />}
        </div>
      </div>

      {error && (
        <div className="error-banner">
          <AlertCircle size={16} />
          <span>{error}</span>
        </div>
      )}

      <div className="map-leaflet-wrapper">
        <div ref={mapContainerRef} style={{ height: '100%', width: '100%' }} />
      </div>
      {!loading && !error && !mapCases.some(hasUsableMapCoordinates) && (
        <div className="cases-empty-state">
          <MapPin size={28} className="text-muted" />
          <h3>No mappable cases found</h3>
          <p>No cases with valid coordinates match the selected filters.</p>
        </div>
      )}
    </div>
  );
}

function AdminAnalyticsView() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [exporting, setExporting] = useState(false);

  useEffect(() => {
    let isMounted = true;
    fetchOperationalAnalytics()
      .then((res) => {
        if (!isMounted) return;
        setData(res);
        setLoading(false);
      })
      .catch((err) => {
        if (!isMounted) return;
        setError(err instanceof AdminApiError ? err.message : 'Failed to fetch operational analytics.');
        setLoading(false);
      });
    return () => { isMounted = false; };
  }, []);

  async function handleExportCsv() {
    setExporting(true);
    try {
      await downloadAnalyticsCsv();
    } catch {
      alert('Failed to download CSV report.');
    } finally {
      setExporting(false);
    }
  }

  if (loading) {
    return (
      <div className="summary-loading-placeholder">
        <LoaderCircle size={28} className="spin-slow" />
        <span>Aggregating analytics across MongoDB collections...</span>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="error-banner">
        <AlertCircle size={16} />
        <span>{error || 'Unable to load operational analytics.'}</span>
      </div>
    );
  }

  const total = data.total_cases || 1;
  const pCounts = data.priority_distribution || {};
  const issueCounts = data.issue_distribution || {};
  const statusCounts = data.status_distribution || {};
  const dupCounts = data.duplicate_distribution || {};

  return (
    <div className="analytics-view-container">
      <div className="analytics-header-actions">
        <div>
          <h3>Operational Analytics &amp; Insights (M4.7)</h3>
          <p className="section-desc">Ground-truth metrics computed directly via MongoDB aggregation pipelines.</p>
        </div>
        <button
          type="button"
          className="primary-button small-btn"
          onClick={handleExportCsv}
          disabled={exporting}
        >
          {exporting ? <LoaderCircle size={14} className="spin-slow" /> : <Download size={14} />} Export Clean CSV
        </button>
      </div>

      <div className="disclaimer-banner">
        <AlertCircle size={16} />
        <span>Strict Ground-Truth Guarantee: Analytics reflect verified cases in the database. No fabricated statistics or synthetic projections.</span>
      </div>

      <div className="stats-kpi-grid">
        <div className="kpi-card">
          <span className="kpi-label">Total Cases</span>
          <span className="kpi-value">{data.total_cases}</span>
          <span className="kpi-subtext">All submitted reports</span>
        </div>
        <div className="kpi-card kpi-resolved">
          <span className="kpi-label">Resolved Cases</span>
          <span className="kpi-value text-emerald">{data.resolved_cases}</span>
          <span className="kpi-subtext">Resolved or closed</span>
        </div>
        <div className="kpi-card">
          <span className="kpi-label">Resolution Rate</span>
          <span className="kpi-value text-accent">{data.resolution_rate_percent?.toFixed(1) || '0.0'}%</span>
          <span className="kpi-subtext">Turnaround efficiency</span>
        </div>
        <div className="kpi-card">
          <span className="kpi-label">Avg Priority Score</span>
          <span className="kpi-value">{data.average_priority_score?.toFixed(1) || '0.0'}/100</span>
          <span className="kpi-subtext">M3.8 risk score average</span>
        </div>
      </div>

      <div className="analytics-charts-grid">
        <div className="chart-card">
          <h4>Priority Distribution (M3.8 Triage)</h4>
          <div className="chart-bars-list">
            {['P1', 'P2', 'P3', 'P4'].map((pKey) => {
              const count = pCounts[pKey] || 0;
              const pct = total > 0 ? (count / total) * 100 : 0;
              return (
                <div key={pKey} className="chart-bar-item">
                  <div className="chart-bar-header">
                    <span>{pKey} ({pKey === 'P1' ? 'Critical' : pKey === 'P2' ? 'High' : pKey === 'P3' ? 'Medium' : 'Low'})</span>
                    <span>{count} ({pct.toFixed(1)}%)</span>
                  </div>
                  <div className="chart-bar-track">
                    <div
                      className={`chart-bar-fill ${pKey.toLowerCase()}`}
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        <div className="chart-card">
          <h4>Issue Category Breakdown (CV Pipeline)</h4>
          <div className="chart-bars-list">
            {[
              { key: 'open_damaged_manhole', label: 'Open Manholes' },
              { key: 'damaged_missing_road_sign', label: 'Damaged Signs' },
              { key: 'road_waterlogging', label: 'Waterlogging' },
              { key: 'other_civic_issue', label: 'Other Civic' },
            ].map((item) => {
              const count = issueCounts[item.key] || 0;
              const pct = total > 0 ? (count / total) * 100 : 0;
              return (
                <div key={item.key} className="chart-bar-item">
                  <div className="chart-bar-header">
                    <span>{item.label}</span>
                    <span>{count} ({pct.toFixed(1)}%)</span>
                  </div>
                  <div className="chart-bar-track">
                    <div className="chart-bar-fill" style={{ width: `${pct}%` }} />
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        <div className="chart-card">
          <h4>Lifecycle Status Distribution (M4.5)</h4>
          <div className="chart-bars-list">
            {[
              { key: 'submitted_to_cvki', label: 'Submitted to CVKI' },
              { key: 'under_review', label: 'Under Review' },
              { key: 'assigned', label: 'Assigned' },
              { key: 'in_progress', label: 'In Progress' },
              { key: 'resolved', label: 'Resolved' },
              { key: 'closed', label: 'Closed' },
            ].map((st) => {
              const count = statusCounts[st.key] || 0;
              const pct = total > 0 ? (count / total) * 100 : 0;
              return (
                <div key={st.key} className="chart-bar-item">
                  <div className="chart-bar-header">
                    <span>{st.label}</span>
                    <span>{count} ({pct.toFixed(1)}%)</span>
                  </div>
                  <div className="chart-bar-track">
                    <div className="chart-bar-fill" style={{ width: `${pct}%` }} />
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        <div className="chart-card">
          <h4>Duplicate Intelligence (M3.7)</h4>
          <div className="chart-bars-list">
            {[
              { key: 'unique', label: 'Unique Complaints' },
              { key: 'duplicate', label: 'Confirmed Duplicates' },
              { key: 'possible_duplicate', label: 'Possible Duplicates' },
            ].map((d) => {
              const count = dupCounts[d.key] || 0;
              const pct = total > 0 ? (count / total) * 100 : 0;
              return (
                <div key={d.key} className="chart-bar-item">
                  <div className="chart-bar-header">
                    <span>{d.label}</span>
                    <span>{count} ({pct.toFixed(1)}%)</span>
                  </div>
                  <div className="chart-bar-track">
                    <div className="chart-bar-fill" style={{ width: `${pct}%` }} />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {data.hotspots?.length > 0 && (
        <div className="chart-card">
          <h4>Top Geographic Hotspots &amp; Concentrations</h4>
          <table className="hotspot-table">
            <thead>
              <tr>
                <th>Rank</th>
                <th>Road / Corridor</th>
                <th>City</th>
                <th>Reported Incidents</th>
              </tr>
            </thead>
            <tbody>
              {data.hotspots.slice(0, 8).map((h, idx) => (
                <tr key={idx}>
                  <td><strong>#{idx + 1}</strong></td>
                  <td>{h.road || 'Corridor Unnamed'}</td>
                  <td>{h.city || 'Municipal Area'}</td>
                  <td><strong>{h.count}</strong> cases</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function AdminAuditView() {
  const [overview, setOverview] = useState(null);
  const [logs, setLogs] = useState([]);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [totalLogs, setTotalLogs] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const [actionFilter, setActionFilter] = useState('');
  const [resultFilter, setResultFilter] = useState('');
  const [selectedLog, setSelectedLog] = useState(null);

  useEffect(() => {
    let isMounted = true;
    fetchSecurityOverview()
      .then((res) => {
        if (isMounted) setOverview(res);
      })
      .catch(() => {});
    return () => { isMounted = false; };
  }, []);

  useEffect(() => {
    let isMounted = true;
    setLoading(true);
    setError(null);

    fetchAuditLogs({
      action: actionFilter || undefined,
      result: resultFilter || undefined,
      page,
      page_size: 15,
    })
      .then((res) => {
        if (!isMounted) return;
        setLogs(res.items || []);
        setTotalLogs(res.total || 0);
        setPage(res.page || 1);
        setTotalPages(res.total_pages || 1);
        setLoading(false);
      })
      .catch((err) => {
        if (!isMounted) return;
        setError(err instanceof AdminApiError ? err.message : 'Failed to fetch audit trail.');
        setLoading(false);
      });

    return () => { isMounted = false; };
  }, [actionFilter, resultFilter, page]);

  function handleReset() {
    setActionFilter('');
    setResultFilter('');
    setPage(1);
  }

  return (
    <div className="audit-view-container">
      <div className="section-head-bar" style={{ margin: 0 }}>
        <div>
          <h3>Audit Trail &amp; Security Monitoring (M4.8)</h3>
          <p className="section-desc">Tamper-evident system activity log with recursive credential redaction.</p>
        </div>
        <span className="cases-total-counter">
          Total Logged Events: <strong>{totalLogs}</strong>
        </span>
      </div>

      {overview && (
        <div className="audit-kpi-grid">
          <div className="audit-kpi-card">
            <span className="audit-kpi-title">Total Audit Events</span>
            <span className="audit-kpi-num">{overview.total_events}</span>
          </div>
          <div className={`audit-kpi-card ${overview.failed_events > 0 ? 'alert-card' : ''}`}>
            <span className="audit-kpi-title">Failed Actions</span>
            <span className={`audit-kpi-num ${overview.failed_events > 0 ? 'danger' : ''}`}>
              {overview.failed_events}
            </span>
          </div>
          <div className={`audit-kpi-card ${overview.access_denied_events > 0 ? 'alert-card' : ''}`}>
            <span className="audit-kpi-title">Access Denied (403)</span>
            <span className={`audit-kpi-num ${overview.access_denied_events > 0 ? 'danger' : ''}`}>
              {overview.access_denied_events}
            </span>
          </div>
          <div className="audit-kpi-card">
            <span className="audit-kpi-title">Auth Logins</span>
            <span className="audit-kpi-num">{overview.login_events}</span>
          </div>
        </div>
      )}

      <div className="admin-filters-card" style={{ padding: '12px 16px' }}>
        <div className="filter-dropdowns-row">
          <div className="filter-item">
            <label htmlFor="audit-action-filter">Action:</label>
            <select
              id="audit-action-filter"
              className="admin-filter-select"
              value={actionFilter}
              onChange={(e) => { setActionFilter(e.target.value); setPage(1); }}
            >
              <option value="">All Actions</option>
              <option value="login">Login</option>
              <option value="access_denied">Access Denied</option>
              <option value="case_status_change">Case Status Change</option>
              <option value="case_assigned">Case Assigned</option>
              <option value="case_unassigned">Case Unassigned</option>
              <option value="submission_prepared">Submission Prepared</option>
            </select>
          </div>

          <div className="filter-item">
            <label htmlFor="audit-result-filter">Result:</label>
            <select
              id="audit-result-filter"
              className="admin-filter-select"
              value={resultFilter}
              onChange={(e) => { setResultFilter(e.target.value); setPage(1); }}
            >
              <option value="">All Results</option>
              <option value="success">Success</option>
              <option value="failure">Failure</option>
              <option value="denied">Denied</option>
            </select>
          </div>

          {(actionFilter || resultFilter) && (
            <button
              type="button"
              className="ghost-button small-btn reset-filters-btn"
              onClick={handleReset}
            >
              Reset Filters
            </button>
          )}
        </div>
      </div>

      {error && (
        <div className="error-banner">
          <AlertCircle size={16} />
          <span>{error}</span>
        </div>
      )}

      {loading ? (
        <div className="cases-loading-state">
          <LoaderCircle size={28} className="spin-slow" />
          <span>Loading audit log entries...</span>
        </div>
      ) : logs.length === 0 ? (
        <div className="cases-empty-state">
          <ShieldAlert size={32} className="text-muted" />
          <h3>No Audit Records Found</h3>
          <p>No logged security actions matched the selected filters.</p>
        </div>
      ) : (
        <div className="cases-table-wrap">
          <table className="admin-cases-table">
            <thead>
              <tr>
                <th>Timestamp</th>
                <th>Actor</th>
                <th>Action</th>
                <th>Result</th>
                <th>Resource Reference</th>
                <th>IP Address</th>
                <th>Request ID</th>
                <th>Metadata</th>
              </tr>
            </thead>
            <tbody>
              {logs.map((item) => (
                <tr key={item.event_id}>
                  <td className="font-mono text-bold" style={{ fontSize: '11px' }}>
                    {new Date(item.timestamp).toLocaleString('en-GB', {
                      day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', second: '2-digit'
                    })}
                  </td>
                  <td>
                    <div style={{ fontSize: '12px', fontWeight: 600 }}>{item.actor_email || item.actor_user_id || 'System'}</div>
                    <span className="role-tag" style={{ fontSize: '9px', padding: '1px 5px' }}>{item.actor_role}</span>
                  </td>
                  <td>
                    <span className="issue-label-text" style={{ fontSize: '12px' }}>
                      {item.action}
                    </span>
                  </td>
                  <td>
                    <span className={`result-pill ${item.result}`}>
                      {item.result}
                    </span>
                  </td>
                  <td className="font-mono" style={{ fontSize: '11px' }}>
                    {item.resource_reference_id || '—'}
                  </td>
                  <td style={{ fontSize: '11px', color: '#64748b' }}>
                    {item.ip_address || '—'}
                  </td>
                  <td className="font-mono" style={{ fontSize: '10px' }}>
                    {item.request_id || '—'}
                  </td>
                  <td>
                    <button
                      type="button"
                      className="table-action-btn"
                      onClick={() => setSelectedLog(selectedLog?.event_id === item.event_id ? null : item)}
                    >
                      {selectedLog?.event_id === item.event_id ? 'Hide' : 'Inspect'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {selectedLog && (
            <div style={{ marginTop: '14px', background: '#f8fafc', border: '1px solid #cbd5e1', borderRadius: '8px', padding: '14px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                <strong style={{ fontSize: '13px' }}>Redacted Audit Metadata ({selectedLog.event_id}):</strong>
                <button
                  type="button"
                  className="icon-close-btn"
                  onClick={() => setSelectedLog(null)}
                  aria-label="Close metadata"
                >
                  <X size={14} />
                </button>
              </div>
              <p><strong>Request ID:</strong> {selectedLog.request_id || '—'}</p>
              <p><strong>User-Agent:</strong> {selectedLog.user_agent || '—'}</p>
              <pre className="metadata-code-block">
                {JSON.stringify(selectedLog.metadata || {}, null, 2)}
              </pre>
            </div>
          )}

          {totalPages > 1 && (
            <div className="pagination-bar">
              <span className="pagination-page-indicator">
                Page <strong>{page}</strong> of <strong>{totalPages}</strong>
              </span>
              <div className="pagination-buttons">
                <button
                  type="button"
                  className="icon-button"
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page <= 1 || loading}
                >
                  <ChevronLeft size={16} />
                </button>
                <button
                  type="button"
                  className="icon-button"
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  disabled={page >= totalPages || loading}
                >
                  <ChevronRight size={16} />
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function AdminDashboardView({ currentUser }) {
  const [activeTab, setActiveTab] = useState('overview');
  const [summary, setSummary] = useState(null);
  const [loadingSummary, setLoadingSummary] = useState(true);
  const [summaryError, setSummaryError] = useState(null);

  const [cases, setCases] = useState([]);
  const [totalCases, setTotalCases] = useState(0);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [loadingCases, setLoadingCases] = useState(true);
  const [casesError, setCasesError] = useState(null);

  const [search, setSearch] = useState('');
  const [priorityFilter, setPriorityFilter] = useState('');
  const [issueFilter, setIssueFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [assignmentFilter, setAssignmentFilter] = useState('');
  const [sortBy, setSortBy] = useState('newest');

  const [refreshTrigger, setRefreshTrigger] = useState(0);

  const [selectedCaseRef, setSelectedCaseRef] = useState(null);

  useEffect(() => {
    let isMounted = true;
    fetchDashboardSummary()
      .then((data) => {
        if (isMounted) {
          setSummary(data);
          setLoadingSummary(false);
        }
      })
      .catch((err) => {
        if (isMounted) {
          setSummaryError(err instanceof AdminApiError ? err.message : 'Failed to load summary statistics.');
          setLoadingSummary(false);
        }
      });

    return () => {
      isMounted = false;
    };
  }, [refreshTrigger]);

  useEffect(() => {
    let isMounted = true;
    fetchAdminCases({
      search: search.trim() || undefined,
      priority: priorityFilter || undefined,
      issue: issueFilter || undefined,
      status: statusFilter || undefined,
      assignment: assignmentFilter || undefined,
      sort_by: sortBy,
      page,
      page_size: 15,
    })
      .then((res) => {
        if (isMounted) {
          setCases(res.items);
          setTotalCases(res.total);
          setPage(res.page);
          setTotalPages(res.total_pages);
          setLoadingCases(false);
        }
      })
      .catch((err) => {
        if (isMounted) {
          setCasesError(err instanceof AdminApiError ? err.message : 'Failed to load cases list.');
          setLoadingCases(false);
        }
      });

    return () => {
      isMounted = false;
    };
  }, [search, priorityFilter, issueFilter, statusFilter, assignmentFilter, sortBy, page, refreshTrigger]);

  function handleSearchSubmit(e) {
    e.preventDefault();
    setLoadingCases(true);
    setPage(1);
    setRefreshTrigger((c) => c + 1);
  }

  function handleResetFilters() {
    setSearch('');
    setPriorityFilter('');
    setIssueFilter('');
    setStatusFilter('');
    setAssignmentFilter('');
    setSortBy('newest');
    setPage(1);
    setLoadingCases(true);
    setRefreshTrigger((c) => c + 1);
  }

  function handleFilterChange(setter, val) {
    setter(val);
    setPage(1);
    setLoadingCases(true);
  }

  function handlePageChange(newPage) {
    setPage(newPage);
    setLoadingCases(true);
  }

  function handleAssignmentChanged() {
    setLoadingSummary(true);
    setLoadingCases(true);
    setRefreshTrigger((c) => c + 1);
  }

  return (
    <div className="admin-dashboard-container">
      {/* Top Banner */}
      <div className="admin-banner-card">
        <div className="admin-banner-left">
          <div className="portal-badge admin-badge">
            <Shield size={14} /> Admin Command Center (M4.2 - M4.8)
          </div>
          <h1>Operational Administration &amp; Case Routing</h1>
          <p className="admin-banner-desc">
            Signed in as <strong>{currentUser?.email}</strong> · Role: <span className="role-tag admin">admin</span>
          </p>
        </div>
        <div className="admin-banner-actions">
          <button
            type="button"
            className="ghost-button small-btn"
            onClick={() => {
              setLoadingSummary(true);
              setLoadingCases(true);
              setRefreshTrigger((c) => c + 1);
            }}
            disabled={loadingSummary || loadingCases}
            title="Refresh dashboard data"
          >
            <RefreshCw size={14} className={loadingSummary || loadingCases ? 'spin-slow' : ''} /> Refresh
          </button>
        </div>
      </div>

      {/* Navigation Tabs (M4.2 - M4.8) */}
      <div className="admin-nav-tabs">
        <button
          type="button"
          className={`admin-tab-btn ${activeTab === 'overview' ? 'active' : ''}`}
          onClick={() => setActiveTab('overview')}
        >
          <BarChart3 size={15} /> Overview &amp; Cases
        </button>
        <button
          type="button"
          className={`admin-tab-btn ${activeTab === 'map' ? 'active' : ''}`}
          onClick={() => setActiveTab('map')}
        >
          <MapPin size={15} /> Operations Map (M4.6)
        </button>
        <button
          type="button"
          className={`admin-tab-btn ${activeTab === 'analytics' ? 'active' : ''}`}
          onClick={() => setActiveTab('analytics')}
        >
          <Layers size={15} /> Operational Analytics (M4.7)
        </button>
        <button
          type="button"
          className={`admin-tab-btn ${activeTab === 'audit' ? 'active' : ''}`}
          onClick={() => setActiveTab('audit')}
        >
          <ShieldAlert size={15} /> Audit &amp; Security (M4.8)
        </button>
      </div>

      {activeTab === 'overview' && (
        <>
          {/* Summary KPI Cards */}
      {summaryError ? (
        <div className="error-banner">
          <AlertCircle size={16} />
          <span>{summaryError}</span>
        </div>
      ) : loadingSummary ? (
        <div className="summary-loading-placeholder">
          <LoaderCircle size={24} className="spin-slow" />
          <span>Aggregating operational statistics from MongoDB...</span>
        </div>
      ) : summary ? (
        <>
          <div className="stats-kpi-grid">
            <div className="kpi-card">
              <span className="kpi-label">Total Cases</span>
              <span className="kpi-value">{summary.total_cases}</span>
              <span className="kpi-subtext">All submitted civic reports</span>
            </div>
            <div className="kpi-card kpi-open">
              <span className="kpi-label">Open Cases</span>
              <span className="kpi-value text-amber">{summary.open_cases}</span>
              <span className="kpi-subtext">Active triage / under review</span>
            </div>
            <div className="kpi-card kpi-resolved">
              <span className="kpi-label">Resolved Cases</span>
              <span className="kpi-value text-emerald">{summary.resolved_cases}</span>
              <span className="kpi-subtext">Closed / completed</span>
            </div>
            <div className="kpi-card kpi-unassigned">
              <span className="kpi-label">Unassigned Cases</span>
              <span className="kpi-value text-rose">{summary.unassigned_cases}</span>
              <span className="kpi-subtext">Awaiting authority routing</span>
            </div>
          </div>

          {/* Breakdown Distributions */}
          <div className="distribution-cards-grid">
            {/* Priority Overview */}
            <div className="admin-breakdown-card">
              <h3>Priority Overview (M3.8 Triage)</h3>
              <div className="pill-metric-grid">
                <div className="metric-pill p1">
                  <span className="pill-name">P1 Critical</span>
                  <span className="pill-count">{summary.priority_counts?.P1 || 0}</span>
                </div>
                <div className="metric-pill p2">
                  <span className="pill-name">P2 High</span>
                  <span className="pill-count">{summary.priority_counts?.P2 || 0}</span>
                </div>
                <div className="metric-pill p3">
                  <span className="pill-name">P3 Medium</span>
                  <span className="pill-count">{summary.priority_counts?.P3 || 0}</span>
                </div>
                <div className="metric-pill p4">
                  <span className="pill-name">P4 Low</span>
                  <span className="pill-count">{summary.priority_counts?.P4 || 0}</span>
                </div>
              </div>
            </div>

            {/* Issue Distribution */}
            <div className="admin-breakdown-card">
              <h3>Issue Distribution (CV Detection)</h3>
              <div className="pill-metric-grid">
                <div className="metric-pill issue">
                  <span className="pill-name">Manholes</span>
                  <span className="pill-count">{summary.issue_counts?.open_damaged_manhole || 0}</span>
                </div>
                <div className="metric-pill issue">
                  <span className="pill-name">Road Signs</span>
                  <span className="pill-count">{summary.issue_counts?.damaged_missing_road_sign || 0}</span>
                </div>
                <div className="metric-pill issue">
                  <span className="pill-name">Waterlogging</span>
                  <span className="pill-count">{summary.issue_counts?.road_waterlogging || 0}</span>
                </div>
                <div className="metric-pill issue">
                  <span className="pill-name">Other Civic</span>
                  <span className="pill-count">{summary.issue_counts?.other_civic_issue || 0}</span>
                </div>
              </div>
            </div>

            {/* Case Status Overview */}
            <div className="admin-breakdown-card">
              <h3>Status Overview</h3>
              <div className="pill-metric-grid">
                <div className="metric-pill status">
                  <span className="pill-name">Submitted</span>
                  <span className="pill-count">{summary.status_counts?.submitted_to_cvki || 0}</span>
                </div>
                <div className="metric-pill status">
                  <span className="pill-name">Under Review</span>
                  <span className="pill-count">{summary.status_counts?.under_review || 0}</span>
                </div>
                <div className="metric-pill status">
                  <span className="pill-name">Resolved</span>
                  <span className="pill-count">{summary.status_counts?.resolved || 0}</span>
                </div>
                <div className="metric-pill status">
                  <span className="pill-name">Duplicates</span>
                  <span className="pill-count">{(summary.duplicate_counts?.duplicate || 0) + (summary.duplicate_counts?.possible_duplicate || 0)}</span>
                </div>
              </div>
            </div>
          </div>
        </>
      ) : null}

      {/* Case Management Section (M4.3) */}
      <div className="case-management-section">
        <div className="section-head-bar">
          <div>
            <h2>Case Management &amp; Assignment (M4.3 - M4.4)</h2>
            <p className="section-desc">Search, inspect, filter, and assign cases across the platform.</p>
          </div>
          <span className="cases-total-counter">
            Total Matching Cases: <strong>{totalCases}</strong>
          </span>
        </div>

        {/* Filter & Search Bar */}
        <div className="admin-filters-card">
          <form onSubmit={handleSearchSubmit} className="search-form-row">
            <div className="search-input-wrap">
              <Search size={16} className="search-icon" />
              <input
                type="text"
                className="admin-search-input"
                placeholder="Search reference ID, title, road, city..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
              {search && (
                <button
                  type="button"
                  className="clear-search-btn"
                  onClick={() => { setSearch(''); }}
                  aria-label="Clear search"
                >
                  <X size={14} />
                </button>
              )}
            </div>
            <button type="submit" className="primary-button small-btn">
              Search
            </button>
          </form>

          <div className="filter-dropdowns-row">
            <div className="filter-item">
              <label htmlFor="filter-priority">Priority:</label>
              <select
                id="filter-priority"
                className="admin-filter-select"
                value={priorityFilter}
                onChange={(e) => handleFilterChange(setPriorityFilter, e.target.value)}
              >
                <option value="">All Priorities</option>
                <option value="P1">P1 Critical</option>
                <option value="P2">P2 High</option>
                <option value="P3">P3 Medium</option>
                <option value="P4">P4 Low</option>
              </select>
            </div>

            <div className="filter-item">
              <label htmlFor="filter-issue">Issue:</label>
              <select
                id="filter-issue"
                className="admin-filter-select"
                value={issueFilter}
                onChange={(e) => handleFilterChange(setIssueFilter, e.target.value)}
              >
                <option value="">All Issues</option>
                <option value="open_damaged_manhole">Open Manhole</option>
                <option value="damaged_missing_road_sign">Road Sign</option>
                <option value="road_waterlogging">Waterlogging</option>
                <option value="other_civic_issue">Other</option>
              </select>
            </div>

            <div className="filter-item">
              <label htmlFor="filter-status">Status:</label>
              <select
                id="filter-status"
                className="admin-filter-select"
                value={statusFilter}
                onChange={(e) => handleFilterChange(setStatusFilter, e.target.value)}
              >
                <option value="">All Statuses</option>
                <option value="submitted_to_cvki">Submitted</option>
                <option value="under_review">Under Review</option>
                <option value="resolved">Resolved</option>
                <option value="closed">Closed</option>
              </select>
            </div>

            <div className="filter-item">
              <label htmlFor="filter-assignment">Assignment:</label>
              <select
                id="filter-assignment"
                className="admin-filter-select"
                value={assignmentFilter}
                onChange={(e) => handleFilterChange(setAssignmentFilter, e.target.value)}
              >
                <option value="">All Assignments</option>
                <option value="assigned">Assigned</option>
                <option value="unassigned">Unassigned</option>
              </select>
            </div>

            <div className="filter-item">
              <label htmlFor="filter-sort">Sort:</label>
              <select
                id="filter-sort"
                className="admin-filter-select"
                value={sortBy}
                onChange={(e) => handleFilterChange(setSortBy, e.target.value)}
              >
                <option value="newest">Newest First</option>
                <option value="oldest">Oldest First</option>
                <option value="highest_priority">Highest Priority</option>
              </select>
            </div>

            {(search || priorityFilter || issueFilter || statusFilter || assignmentFilter || sortBy !== 'newest') && (
              <button
                type="button"
                className="ghost-button small-btn reset-filters-btn"
                onClick={handleResetFilters}
              >
                Reset Filters
              </button>
            )}
          </div>
        </div>

        {/* Cases Table */}
        {casesError ? (
          <div className="error-banner">
            <AlertCircle size={16} />
            <span>{casesError}</span>
          </div>
        ) : loadingCases ? (
          <div className="cases-loading-state">
            <LoaderCircle size={28} className="spin-slow" />
            <span>Loading cases...</span>
          </div>
        ) : cases.length === 0 ? (
          <div className="cases-empty-state">
            <AlertCircle size={32} className="text-muted" />
            <h3>No Complaint Cases Found</h3>
            <p>No operational cases matched the specified criteria or no cases exist in the database yet.</p>
            {(search || priorityFilter || issueFilter || statusFilter || assignmentFilter) && (
              <button
                type="button"
                className="ghost-button small-btn"
                onClick={handleResetFilters}
              >
                Clear all filters
              </button>
            )}
          </div>
        ) : (
          <div className="cases-table-wrap">
            <table className="admin-cases-table">
              <thead>
                <tr>
                  <th>Reference</th>
                  <th>Date</th>
                  <th>Issue</th>
                  <th>Location</th>
                  <th>Priority</th>
                  <th>Assignment (M4.4)</th>
                  <th>Status</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {cases.map((c) => {
                  const isAssigned = c.assignment?.assignment_status === 'assigned' && Boolean(c.assignment?.assigned_to_user_id);
                  const pLevel = c.priority_analysis?.priority_level || '—';
                  return (
                    <tr key={c.reference_id} onClick={() => setSelectedCaseRef(c.reference_id)} className="clickable-row">
                      <td className="font-mono text-bold">{c.reference_id}</td>
                      <td>{formatDate(c.created_at)}</td>
                      <td>
                        <div className="table-issue-cell">
                          <span className="issue-label-text">{c.issue.label}</span>
                          <span className="complaint-title-preview">{c.complaint.title}</span>
                        </div>
                      </td>
                      <td className="table-loc-cell">{formatLocationSummary(c.location)}</td>
                      <td>
                        <span className={`priority-tag priority-${pLevel}`}>
                          {pLevel}
                        </span>
                      </td>
                      <td>
                        <span className={`assignment-pill ${isAssigned ? 'assigned' : 'unassigned'}`}>
                          {isAssigned ? (c.assignment?.assigned_to_email || 'Assigned') : 'Unassigned'}
                        </span>
                      </td>
                      <td>
                        <span className="table-status-tag">{c.status}</span>
                      </td>
                      <td>
                        <button
                          type="button"
                          className="table-action-btn primary"
                          onClick={(e) => {
                            e.stopPropagation();
                            setSelectedCaseRef(c.reference_id);
                          }}
                        >
                          Inspect
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>

            {/* Pagination Controls */}
            {totalPages > 1 && (
              <div className="pagination-bar">
                <span className="pagination-page-indicator">
                  Page <strong>{page}</strong> of <strong>{totalPages}</strong> ({totalCases} total)
                </span>
                <div className="pagination-buttons">
                  <button
                    type="button"
                    className="icon-button"
                    onClick={() => handlePageChange(page - 1)}
                    disabled={page <= 1 || loadingCases}
                  >
                    <ChevronLeft size={16} />
                  </button>
                  <button
                    type="button"
                    className="icon-button"
                    onClick={() => handlePageChange(page + 1)}
                    disabled={page >= totalPages || loadingCases}
                  >
                    <ChevronRight size={16} />
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
      </>
      )}

      {activeTab === 'map' && (
        <AdminMapView onInspectCase={(ref) => setSelectedCaseRef(ref)} />
      )}

      {activeTab === 'analytics' && (
        <AdminAnalyticsView />
      )}

      {activeTab === 'audit' && (
        <AdminAuditView />
      )}

      {/* Case Detail & Assignment Modal */}
      {selectedCaseRef && (
        <AdminCaseDetailModal
          referenceId={selectedCaseRef}
          onClose={() => setSelectedCaseRef(null)}
          onAssignmentChanged={handleAssignmentChanged}
        />
      )}
    </div>
  );
}

function AuthorityCaseSummaryModal({ caseData, onClose }) {
  return (
    <div className="modal-backdrop" onClick={onClose} role="dialog" aria-modal="true" aria-labelledby="authority-case-summary-title">
      <div className="modal-card" onClick={(event) => event.stopPropagation()}>
        <div className="modal-header">
          <div>
            <p className="eyebrow">Authority case summary</p>
            <h3 id="authority-case-summary-title">{caseData?.reference_id || 'Case summary unavailable'}</h3>
          </div>
          <button className="icon-close-btn" type="button" onClick={onClose} aria-label="Close case summary">
            <X size={18} />
          </button>
        </div>
        {caseData ? (
          <div className="admin-case-body">
            <div className="admin-section-box">
              <h4>Assigned case</h4>
              <p><strong>Issue:</strong> {caseData.issue_label || caseData.issue}</p>
              <p><strong>Status:</strong> {formatReadinessStatus(caseData.status)}</p>
              <p><strong>Priority:</strong> {caseData.priority || 'Unavailable'}</p>
              <p><strong>Location:</strong> {formatLocationSummary([caseData.road, caseData.city].filter(Boolean).join(', '))}</p>
              <p><strong>Coordinates:</strong> {caseData.latitude}, {caseData.longitude}</p>
              <p><strong>Created:</strong> {formatDate(caseData.created_at)}</p>
            </div>
            <p className="text-muted">This authority view contains operational summary fields only.</p>
          </div>
        ) : (
          <div className="admin-case-body">
            <div className="error-banner" role="alert">This case is no longer available in the assigned-case list. Refresh and try again.</div>
          </div>
        )}
      </div>
    </div>
  );
}

function AuthorityPortalView({ currentUser }) {
  const [activeTab, setActiveTab] = useState('cases');
  const [cases, setCases] = useState([]);
  const [totalAssigned, setTotalAssigned] = useState(0);
  const [unmappedCount, setUnmappedCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [actionMessage, setActionMessage] = useState(null);
  const [selectedCaseRef, setSelectedCaseRef] = useState(null);
  const [actionLoading, setActionLoading] = useState(false);

  async function loadAuthorityCases() {
    setLoading(true);
    setError(null);
    try {
      const res = await fetchAuthorityMapCases({ limit: 2000 });
      setCases(res.mapped_cases || []);
      setTotalAssigned(res.total_matching ?? (res.mapped_cases || []).length);
      setUnmappedCount(res.unmapped_cases_count ?? 0);
    } catch (err) {
      setError(err?.message || 'Failed to load assigned authority cases.');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadAuthorityCases();
  }, []);

  async function handleStatusTransition(referenceId, nextStatus) {
    if (!window.confirm(`Advance case ${referenceId} status to "${nextStatus.replaceAll('_', ' ')}"?`)) {
      return;
    }
    setActionLoading(true);
    setActionMessage(null);
    setError(null);
    try {
      await updateAuthorityCaseStatus(referenceId, nextStatus, `Authority operator ${currentUser?.email} executed transition`);
      setActionMessage(`Case ${referenceId} successfully updated to "${nextStatus}".`);
      await loadAuthorityCases();
    } catch (err) {
      setError(err?.message || 'Status transition failed.');
    } finally {
      setActionLoading(false);
    }
  }

  return (
    <div className="admin-dashboard-container">
      {/* Banner */}
      <div className="admin-banner-card">
        <div className="admin-banner-left">
          <div className="portal-badge authority-badge">
            <Shield size={14} /> Authority Operations Portal (M4.5)
          </div>
          <h1>Assigned Field Cases &amp; Remediation Workflow</h1>
          <p className="admin-banner-desc">
            Signed in as <strong>{currentUser?.email}</strong> · Role: <span className="role-tag authority">authority</span>
          </p>
        </div>
        <div className="admin-banner-actions">
          <button
            type="button"
            className="ghost-button small-btn"
            onClick={loadAuthorityCases}
            disabled={loading || actionLoading}
          >
            <RefreshCw size={14} className={loading ? 'spin-slow' : ''} /> Refresh
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="admin-nav-tabs">
        <button
          type="button"
          className={`admin-tab-btn ${activeTab === 'cases' ? 'active' : ''}`}
          onClick={() => setActiveTab('cases')}
        >
          <Clock size={15} /> My Assigned Cases ({totalAssigned})
        </button>
        <button
          type="button"
          className={`admin-tab-btn ${activeTab === 'map' ? 'active' : ''}`}
          onClick={() => setActiveTab('map')}
        >
          <MapPin size={15} /> Authority Field Map
        </button>
      </div>

      {actionMessage && (
        <div className="success-banner">
          <CheckCircle2 size={16} />
          <span>{actionMessage}</span>
        </div>
      )}

      {error && (
        <div className="error-banner">
          <AlertCircle size={16} />
          <span>{error}</span>
        </div>
      )}

      {activeTab === 'cases' ? (
        <div className="case-management-section">
          {loading ? (
            <div className="cases-loading-state">
              <LoaderCircle size={28} className="spin-slow" />
              <span>Loading assigned cases...</span>
            </div>
          ) : cases.length === 0 && !error ? (
            <div className="cases-empty-state">
              <CheckCircle2 size={32} className="text-muted" />
              <h3>{totalAssigned > 0 ? 'No Mappable Assigned Cases' : 'No Assigned Cases Pending'}</h3>
              <p>
                {totalAssigned > 0
                  ? `${unmappedCount} assigned case${unmappedCount === 1 ? '' : 's'} in this response lack valid coordinates and are not shown in the map-based queue.`
                  : 'You have no cases currently assigned to your authority profile.'}
              </p>
            </div>
          ) : cases.length > 0 ? (
            <div className="cases-table-wrap">
              {unmappedCount > 0 && (
                <div className="location-inline-message" role="status">
                  {unmappedCount} assigned case{unmappedCount === 1 ? '' : 's'} without valid coordinates are omitted from this map-based queue.
                </div>
              )}
              <table className="admin-cases-table">
                <thead>
                  <tr>
                    <th>Reference</th>
                    <th>Issue</th>
                    <th>Location</th>
                    <th>Priority</th>
                    <th>Status</th>
                    <th>Workflow Action</th>
                    <th>Details</th>
                  </tr>
                </thead>
                <tbody>
                  {cases.map((c) => {
                    const pLevel = c.priority || 'P3';
                    const canStart = c.status === 'assigned';
                    const canResolve = c.status === 'in_progress';
                    return (
                      <tr key={c.reference_id}>
                        <td className="font-mono text-bold">{c.reference_id}</td>
                        <td>
                          <div className="table-issue-cell">
                            <span className="issue-label-text">{c.issue_label || c.issue}</span>
                          </div>
                        </td>
                        <td className="table-loc-cell">{formatLocationSummary([c.road, c.city].filter(Boolean).join(', '))}</td>
                        <td>
                          <span className={`priority-tag priority-${pLevel}`}>
                            {pLevel}
                          </span>
                        </td>
                        <td>
                          <span className="table-status-tag">{c.status}</span>
                        </td>
                        <td>
                          {canStart ? (
                            <button
                              type="button"
                              className="table-action-btn primary"
                              onClick={() => handleStatusTransition(c.reference_id, 'in_progress')}
                              disabled={actionLoading}
                            >
                              Start Work
                            </button>
                          ) : canResolve ? (
                            <button
                              type="button"
                              className="table-action-btn primary"
                              style={{ background: '#16a34a' }}
                              onClick={() => handleStatusTransition(c.reference_id, 'resolved')}
                              disabled={actionLoading}
                            >
                              Mark Resolved
                            </button>
                          ) : (
                            <span className="text-muted" style={{ fontSize: '11px' }}>{c.status === 'resolved' ? 'Resolved' : 'No Action'}</span>
                          )}
                        </td>
                        <td>
                          <button
                            type="button"
                            className="table-action-btn"
                            onClick={() => setSelectedCaseRef(c.reference_id)}
                          >
                            Inspect
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : null}
        </div>
      ) : (
        <AdminMapView
          fetchCases={fetchAuthorityMapCases}
          onInspectCase={(ref) => setSelectedCaseRef(ref)}
        />
      )}

      {selectedCaseRef && (
        <AuthorityCaseSummaryModal
          caseData={cases.find((item) => item.reference_id === selectedCaseRef)}
          onClose={() => setSelectedCaseRef(null)}
        />
      )}
    </div>
  );
}

function NavLinks({ currentUser }) {
  const location = useLocation();
  const role = currentUser?.role || 'citizen';
  return (
    <nav className="site-nav" aria-label="Primary navigation">
      <Link to="/" className={location.pathname === '/' ? 'active' : ''}>Inspect</Link>
      <Link to="/my-complaints" className={['/my-complaints', '/dashboard'].includes(location.pathname) ? 'active' : ''}>My Complaints</Link>
      <Link to="/report" className={location.pathname === '/report' ? 'active' : ''}>Report</Link>
      {role === 'admin' && (
        <Link to="/admin" className={location.pathname === '/admin' ? 'active' : ''}>Admin</Link>
      )}
      {role === 'authority' && (
        <Link to="/authority" className={location.pathname === '/authority' ? 'active' : ''}>Authority</Link>
      )}
    </nav>
  );
}

function App() {
  const [currentUser, setCurrentUser] = useState(null);
  const [authReady, setAuthReady] = useState(false);
  const [authRestoreError, setAuthRestoreError] = useState('');
  const [activeModalReferenceId, setActiveModalReferenceId] = useState(null);
  const [isAuthModalOpen, setIsAuthModalOpen] = useState(false);
  const [authModalMode, setAuthModalMode] = useState('login');

  useEffect(() => {
    getCurrentUser()
      .then(setCurrentUser)
      .catch((error) => {
        clearAuthSession();
        setCurrentUser(null);
        if (error instanceof AuthApiError && (error.status === 0 || error.status >= 500)) {
          setAuthRestoreError(error.message);
        }
      })
      .finally(() => setAuthReady(true));
  }, []);

  function handleOpenAuth(mode = 'login') {
    setAuthModalMode(mode);
    setIsAuthModalOpen(true);
  }

  function handleAuthSuccess(user) {
    setCurrentUser(user);
  }

  async function handleLogout() {
    try {
      await logout();
      setCurrentUser(null);
    } catch (error) {
      window.alert(error?.message || 'Logout failed. Please try again.');
    }
  }

  return (
    <Router>
      <div className="app-shell">
        <header className="site-header">
          <Link to="/" className="brand">
            <span className="brand-mark">C</span>
            <span>CVKI <small>field vision</small></span>
          </Link>

          <NavLinks currentUser={currentUser} />

          <div className="header-auth-section">
            {currentUser ? (
              <div className="user-badge-group">
                <NotificationDropdown
                  currentUser={currentUser}
                  onSelectCase={(ref) => setActiveModalReferenceId(ref)}
                />
                <span className="user-email-chip" title={currentUser.email}>
                  <User size={13} />
                  <span className="user-email-text">
                    Logged in as: <strong>{currentUser.email}</strong>
                    {currentUser.role && currentUser.role !== 'citizen' && (
                      <span className={`role-chip role-chip-${currentUser.role}`}>[{currentUser.role}]</span>
                    )}
                  </span>
                </span>
                <button
                  className="icon-button logout-header-btn"
                  type="button"
                  onClick={handleLogout}
                  title="Logout"
                >
                  <LogOut size={15} />
                  <span className="sr-only">Logout</span>
                </button>
              </div>
            ) : (
              <div className="auth-nav-buttons">
                <button
                  className="text-auth-button"
                  type="button"
                  onClick={() => handleOpenAuth('login')}
                >
                  <LogIn size={14} /> Sign In
                </button>
                <button
                  className="primary-button small-btn"
                  type="button"
                  onClick={() => handleOpenAuth('register')}
                >
                  <UserPlus size={14} /> Register
                </button>
              </div>
            )}
          </div>
        </header>

        <main>
          {!authReady ? <div className="role-access-state">Restoring secure session...</div> : <Routes>
            <Route
              path="/"
              element={
                <DetectionWorkspace
                  currentUser={currentUser}
                  onOpenAuth={handleOpenAuth}
                />
              }
            />
            <Route
              path="/report"
              element={
                <DetectionWorkspace
                  currentUser={currentUser}
                  onOpenAuth={handleOpenAuth}
                />
              }
            />
            <Route
              path="/my-complaints"
              element={
                <MyComplaintsView
                  currentUser={currentUser}
                  onOpenAuth={handleOpenAuth}
                  onLogout={handleLogout}
                />
              }
            />
            <Route
              path="/dashboard"
              element={
                <MyComplaintsView
                  currentUser={currentUser}
                  onOpenAuth={handleOpenAuth}
                  onLogout={handleLogout}
                />
              }
            />
            <Route
              path="/admin"
              element={
                <RoleProtectedRoute
                  currentUser={currentUser}
                  allowedRoles={['admin']}
                  onOpenAuth={handleOpenAuth}
                >
                  <AdminDashboardView currentUser={currentUser} />
                </RoleProtectedRoute>
              }
            />
            <Route
              path="/authority"
              element={
                <RoleProtectedRoute
                  currentUser={currentUser}
                  allowedRoles={['authority']}
                  onOpenAuth={handleOpenAuth}
                >
                  <AuthorityPortalView currentUser={currentUser} />
                </RoleProtectedRoute>
              }
            />
          </Routes>}
          {authReady && authRestoreError && (
            <div className="error-banner" role="alert">
              <AlertCircle size={16} />
              <span>{authRestoreError} Protected features remain unavailable until your session can be verified.</span>
            </div>
          )}
        </main>

        <footer className="site-footer">
          <span>CVKI / Civic Vision &amp; Knowledge Intelligence</span>
          <span>M4 · Operations, Workflows, Maps, Analytics &amp; Security Active</span>
        </footer>

        {isAuthModalOpen && (
          <AuthModal
            key={authModalMode}
            initialMode={authModalMode}
            onClose={() => setIsAuthModalOpen(false)}
            onSuccess={handleAuthSuccess}
          />
        )}

        {activeModalReferenceId && (
          <CaseDetailModal
            referenceId={activeModalReferenceId}
            onClose={() => setActiveModalReferenceId(null)}
          />
        )}
      </div>
    </Router>
  );
}

export default App;
