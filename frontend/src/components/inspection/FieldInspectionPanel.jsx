import { useEffect, useState } from 'react';
import {
  AlertTriangle,
  Camera,
  CheckCircle2,
  FileCheck2,
  Info,
  LoaderCircle,
  MapPin,
  Shield,
} from 'lucide-react';
import {
  getInspectionProtocol,
  submitFieldInspection,
} from '../../services/decisionSupportApi';

export function FieldInspectionPanel({ referenceId, onClose }) {
  const [protocol, setProtocol] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Form state
  const [stepObservations, setStepObservations] = useState({});
  const [stepDefects, setStepDefects] = useState({});
  const [evidenceItems, setEvidenceItems] = useState(['field_photo_overview.jpg']);
  const [newEvidence, setNewEvidence] = useState('');
  const [latitude, setLatitude] = useState('');
  const [longitude, setLongitude] = useState('');
  const [generalNotes, setGeneralNotes] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [auditResult, setAuditResult] = useState(null);

  useEffect(() => {
    let isMounted = true;
    setLoading(true);
    setError(null);

    getInspectionProtocol(referenceId)
      .then((data) => {
        if (!isMounted) return;
        setProtocol(data);
        if (data.location_requirements?.expected_case_location) {
          setLatitude(String(data.location_requirements.expected_case_location.latitude || ''));
          setLongitude(String(data.location_requirements.expected_case_location.longitude || ''));
        }
        setLoading(false);
      })
      .catch((err) => {
        if (!isMounted) return;
        setError(err?.message || 'Failed to load field inspection protocol.');
        setLoading(false);
      });

    return () => {
      isMounted = false;
    };
  }, [referenceId]);

  const handleAddEvidence = () => {
    if (!newEvidence.trim()) return;
    setEvidenceItems([...evidenceItems, newEvidence.trim()]);
    setNewEvidence('');
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!protocol) return;

    // Build observations
    const obsList = protocol.inspection_steps.map((st) => ({
      step_id: st.step_id,
      observation_text: stepObservations[st.step_id] || 'Step inspected and documented.',
      defect_confirmed: stepDefects[st.step_id] !== false,
      notes: generalNotes || undefined,
    }));

    const payload = {
      protocol_id: protocol.protocol_id,
      protocol_version: protocol.protocol_version,
      observations: obsList,
      evidence_items: evidenceItems,
      location: latitude && longitude ? { latitude: parseFloat(latitude), longitude: parseFloat(longitude) } : null,
      inspection_timestamp: new Date().toISOString(),
      notes: generalNotes || undefined,
    };

    setSubmitting(true);
    try {
      const res = await submitFieldInspection(referenceId, payload);
      setAuditResult(res);
    } catch (err) {
      alert(`Submission failed: ${err.message}`);
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className="p-5 rounded-xl border border-slate-700 bg-slate-900/90 text-slate-300 flex items-center gap-3">
        <LoaderCircle size={20} className="animate-spin text-cyan-400" />
        <span>Loading structured field inspection protocol...</span>
      </div>
    );
  }

  if (error || !protocol) {
    return (
      <div className="p-5 rounded-xl border border-slate-800 bg-slate-900/40 text-slate-400">
        <p className="text-xs text-rose-400">{error || 'Protocol unavailable.'}</p>
        {onClose && (
          <button type="button" onClick={onClose} className="mt-2 text-xs text-slate-300 underline">
            Close Panel
          </button>
        )}
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-slate-700 bg-slate-900 text-slate-100 p-5 shadow-2xl space-y-5">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 pb-3">
        <div>
          <div className="flex items-center gap-2">
            <Shield size={20} className="text-cyan-400" />
            <h3 className="text-base font-semibold text-slate-100">Field Inspection Protocol</h3>
          </div>
          <p className="text-xs text-slate-400 mt-0.5">
            Protocol: <span className="font-mono text-slate-300">{protocol.protocol_id}</span> (v{protocol.protocol_version}) &middot; Case: <span className="font-mono text-cyan-300">{protocol.case_reference}</span>
          </p>
        </div>
        {onClose && (
          <button
            type="button"
            onClick={onClose}
            className="text-xs text-slate-400 hover:text-white px-2.5 py-1 rounded bg-slate-800"
          >
            Close
          </button>
        )}
      </div>

      {/* Safety Banner */}
      {protocol.safety_notes && protocol.safety_notes.length > 0 && (
        <div className="p-3 rounded-lg bg-amber-950/40 border border-amber-600/40 text-amber-200 text-xs space-y-1">
          <div className="font-semibold flex items-center gap-1.5 text-amber-300">
            <AlertTriangle size={14} />
            Mandatory Field Safety Directives:
          </div>
          <ul className="list-disc list-inside space-y-0.5 text-amber-200/90 pl-1">
            {protocol.safety_notes.map((sn, idx) => (
              <li key={idx}>{sn}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Inspection Form */}
      {!auditResult ? (
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="text-xs font-semibold text-slate-300 uppercase tracking-wider">
            Mandatory Verification Steps
          </div>
          <div className="space-y-3">
            {protocol.inspection_steps.map((st) => (
              <div key={st.step_id} className="p-3.5 rounded-lg bg-slate-800/50 border border-slate-700/60 space-y-2">
                <div className="flex items-start justify-between gap-2">
                  <div className="space-y-0.5">
                    <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-slate-700 text-slate-300">
                      Step {st.order}: {st.step_id}
                    </span>
                    <p className="text-xs font-medium text-slate-200">{st.instruction}</p>
                    <p className="text-[11px] text-slate-400">Purpose: {st.purpose}</p>
                  </div>
                  {st.mandatory && (
                    <span className="text-[10px] font-semibold text-rose-400 bg-rose-950/60 px-2 py-0.5 rounded border border-rose-800 shrink-0">
                      Mandatory
                    </span>
                  )}
                </div>

                <div className="flex flex-col sm:flex-row gap-2 pt-1">
                  <input
                    type="text"
                    placeholder="Enter observation notes..."
                    value={stepObservations[st.step_id] || ''}
                    onChange={(e) => setStepObservations({ ...stepObservations, [st.step_id]: e.target.value })}
                    className="flex-1 text-xs bg-slate-950 border border-slate-700 rounded px-2.5 py-1.5 text-slate-200 focus:outline-none focus:border-cyan-500"
                  />
                  <label className="flex items-center gap-1.5 text-xs text-slate-300 shrink-0 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={stepDefects[st.step_id] !== false}
                      onChange={(e) => setStepDefects({ ...stepDefects, [st.step_id]: e.target.checked })}
                      className="rounded bg-slate-950 border-slate-700 text-cyan-500 focus:ring-0"
                    />
                    <span>Defect Confirmed</span>
                  </label>
                </div>
              </div>
            ))}
          </div>

          {/* Evidence Upload */}
          <div className="p-3.5 rounded-lg bg-slate-800/40 border border-slate-700/50 space-y-2">
            <label className="text-xs font-semibold text-slate-300 flex items-center gap-1.5">
              <Camera size={14} className="text-indigo-400" />
              Attached Evidence References
            </label>
            <div className="flex flex-wrap gap-1.5">
              {evidenceItems.map((item, idx) => (
                <span key={idx} className="text-xs bg-slate-700 px-2 py-1 rounded text-slate-200 font-mono">
                  {item}
                </span>
              ))}
            </div>
            <div className="flex gap-2">
              <input
                type="text"
                placeholder="Attach photo ID or file reference (e.g. photo_closeup.jpg)..."
                value={newEvidence}
                onChange={(e) => setNewEvidence(e.target.value)}
                className="flex-1 text-xs bg-slate-950 border border-slate-700 rounded px-2.5 py-1.5 text-slate-200"
              />
              <button
                type="button"
                onClick={handleAddEvidence}
                className="text-xs bg-slate-700 hover:bg-slate-600 px-3 py-1.5 rounded text-white"
              >
                Add Ref
              </button>
            </div>
          </div>

          {/* GPS Coordinates */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-slate-400 block mb-1 flex items-center gap-1">
                <MapPin size={12} className="text-emerald-400" /> Latitude
              </label>
              <input
                type="number"
                step="any"
                value={latitude}
                onChange={(e) => setLatitude(e.target.value)}
                className="w-full text-xs bg-slate-950 border border-slate-700 rounded px-2.5 py-1.5 text-slate-200"
              />
            </div>
            <div>
              <label className="text-xs text-slate-400 block mb-1 flex items-center gap-1">
                <MapPin size={12} className="text-emerald-400" /> Longitude
              </label>
              <input
                type="number"
                step="any"
                value={longitude}
                onChange={(e) => setLongitude(e.target.value)}
                className="w-full text-xs bg-slate-950 border border-slate-700 rounded px-2.5 py-1.5 text-slate-200"
              />
            </div>
          </div>

          <div>
            <label className="text-xs text-slate-400 block mb-1">General Inspection Notes</label>
            <textarea
              rows={2}
              value={generalNotes}
              onChange={(e) => setGeneralNotes(e.target.value)}
              placeholder="Additional on-site observations or safety notes..."
              className="w-full text-xs bg-slate-950 border border-slate-700 rounded px-2.5 py-1.5 text-slate-200"
            />
          </div>

          <div className="border-t border-slate-800 pt-3">
            <button
              type="submit"
              disabled={submitting}
              className="w-full bg-cyan-600 hover:bg-cyan-500 disabled:opacity-50 text-white font-semibold py-2.5 rounded-lg text-xs transition-colors flex items-center justify-center gap-2"
            >
              {submitting ? <LoaderCircle size={14} className="animate-spin" /> : <FileCheck2 size={14} />}
              Submit Field Inspection &amp; Run Automated Audit
            </button>
          </div>
        </form>
      ) : (
        /* Audit Result View */
        <div className="space-y-4 p-4 rounded-xl bg-slate-800/60 border border-slate-700/80">
          <div className="flex items-center justify-between border-b border-slate-700 pb-3">
            <div className="flex items-center gap-2">
              <CheckCircle2 size={18} className="text-emerald-400" />
              <h4 className="text-sm font-semibold text-slate-100">Field Inspection Audit Result</h4>
            </div>
            <span className="text-xs font-mono bg-slate-950 px-2 py-0.5 rounded text-slate-300">
              {auditResult.inspection_id}
            </span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
            <div className="p-2.5 bg-slate-900 rounded border border-slate-700/60">
              <span className="text-[10px] text-slate-400 uppercase">Audit Outcome</span>
              <p className="text-xs font-bold text-emerald-400 mt-0.5">
                {auditResult.audit_result?.outcome || 'SUPPORTED'}
              </p>
            </div>
            <div className="p-2.5 bg-slate-900 rounded border border-slate-700/60">
              <span className="text-[10px] text-slate-400 uppercase">Geofence Validation</span>
              <p className="text-xs font-medium text-slate-200 mt-0.5">
                {auditResult.geofence_result}
              </p>
            </div>
            <div className="p-2.5 bg-slate-900 rounded border border-slate-700/60">
              <span className="text-[10px] text-slate-400 uppercase">Protocol Completeness</span>
              <p className="text-xs font-medium text-slate-200 mt-0.5">
                {auditResult.completeness}
              </p>
            </div>
          </div>

          <div className="p-3 bg-slate-950/70 rounded text-xs text-slate-300 leading-relaxed">
            <span className="font-semibold text-slate-200 block mb-0.5">Audit Evaluation:</span>
            {auditResult.audit_result?.audit_explanation}
          </div>

          <div className="p-3 bg-blue-950/30 border border-blue-700/40 rounded text-blue-200 text-xs flex items-start gap-2">
            <Info size={14} className="shrink-0 mt-0.5 text-blue-400" />
            <span>
              <strong>Epistemic Invariant:</strong> Field inspection observations are audited as submitted evidence (USER_REPORTED). They assist authority dispatch but do not automatically mark the complaint closed or resolved.
            </span>
          </div>

          <button
            type="button"
            onClick={() => setAuditResult(null)}
            className="text-xs text-cyan-400 hover:text-cyan-300 underline"
          >
            &larr; Submit Another Inspection for Case
          </button>
        </div>
      )}
    </div>
  );
}
