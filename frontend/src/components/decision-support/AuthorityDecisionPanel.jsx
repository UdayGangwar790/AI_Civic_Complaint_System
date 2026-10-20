import { useEffect, useState } from 'react';
import {
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  ClipboardList,
  Eye,
  FileCheck2,
  Info,
  LoaderCircle,
  ShieldCheck,
  UserCheck,
} from 'lucide-react';
import {
  getDecisionSupport,
  reviewDecisionRecommendation,
} from '../../services/decisionSupportApi';

export function AuthorityDecisionPanel({ referenceId, onOpenInspection }) {
  const [decision, setDecision] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [reviewNotes, setReviewNotes] = useState('');
  const [reviewing, setReviewing] = useState(false);
  const [reviewResult, setReviewResult] = useState(null);

  useEffect(() => {
    let isMounted = true;
    setLoading(true);
    setError(null);

    getDecisionSupport(referenceId)
      .then((data) => {
        if (!isMounted) return;
        setDecision(data);
        setLoading(false);
      })
      .catch((err) => {
        if (!isMounted) return;
        setError(err?.message || 'Decision support recommendations are unavailable.');
        setLoading(false);
      });

    return () => {
      isMounted = false;
    };
  }, [referenceId]);

  const handleReview = async () => {
    if (!referenceId) return;
    setReviewing(true);
    try {
      const res = await reviewDecisionRecommendation(referenceId, {
        review_status: 'REVIEWED',
        review_notes: reviewNotes || 'Human review completed by authority officer.',
        decision_action_taken: 'PROCEED_WITH_RECOMMENDED_ACTIONS',
      });
      setReviewResult(res);
    } catch (err) {
      alert(`Failed to record review: ${err.message}`);
    } finally {
      setReviewing(false);
    }
  };

  if (loading) {
    return (
      <div className="p-4 rounded-xl border border-slate-700 bg-slate-900/60 text-slate-300 flex items-center gap-3">
        <LoaderCircle size={20} className="animate-spin text-cyan-400" />
        <span>Evaluating evidence-aware operational decision support...</span>
      </div>
    );
  }

  if (error || !decision) {
    return (
      <div className="p-4 rounded-xl border border-slate-800 bg-slate-900/40 text-slate-400">
        <div className="flex items-center gap-2 text-slate-300 font-medium mb-1">
          <Info size={16} className="text-amber-400" />
          <span>Operational Decision Support</span>
        </div>
        <p className="text-xs text-slate-400">{error || 'No recommendation available for this case.'}</p>
      </div>
    );
  }

  const qualityBadgeClass = {
    STRONG: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30',
    PARTIAL: 'bg-blue-500/20 text-blue-300 border-blue-500/30',
    WEAK: 'bg-amber-500/20 text-amber-300 border-amber-500/30',
    MISSING: 'bg-slate-500/20 text-slate-300 border-slate-500/30',
    CONFLICTING: 'bg-rose-500/20 text-rose-300 border-rose-500/30',
    STALE: 'bg-orange-500/20 text-orange-300 border-orange-500/30',
  }[decision.evidence_quality] || 'bg-slate-700 text-slate-300 border-slate-600';

  return (
    <div className="rounded-xl border border-slate-700/80 bg-slate-900/90 text-slate-100 p-5 shadow-xl space-y-5">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 pb-4">
        <div>
          <div className="flex items-center gap-2">
            <ShieldCheck size={20} className="text-cyan-400" />
            <h3 className="text-base font-semibold text-slate-100">Operational Decision Support</h3>
          </div>
          <p className="text-xs text-slate-400 mt-0.5">
            Evidence-aware actionable guidance &middot; Rec ID: <span className="font-mono text-slate-300">{decision.recommendation_id?.slice(0, 8)}</span>
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className={`text-xs px-2.5 py-1 rounded-full font-medium border ${qualityBadgeClass}`}>
            Evidence Quality: {decision.evidence_quality}
          </span>
          {decision.human_review_required && (
            <span className="text-xs px-2.5 py-1 rounded-full font-medium bg-amber-500/20 text-amber-300 border border-amber-500/30 flex items-center gap-1">
              <UserCheck size={13} />
              Human Review Required
            </span>
          )}
        </div>
      </div>

      {/* Why This Recommendation */}
      <div className="p-3.5 rounded-lg bg-slate-800/60 border border-slate-700/50">
        <h4 className="text-xs font-semibold text-slate-300 uppercase tracking-wider mb-1 flex items-center gap-1.5">
          <Info size={14} className="text-cyan-400" />
          Why this recommendation?
        </h4>
        <p className="text-sm text-slate-200 leading-relaxed">{decision.explanation}</p>
      </div>

      {/* Uncertainty & Caution notice */}
      {decision.uncertainty && decision.uncertainty.length > 0 && (
        <div className="p-3.5 rounded-lg bg-amber-950/30 border border-amber-600/30 text-amber-200 text-xs space-y-1">
          <div className="font-semibold flex items-center gap-1.5 text-amber-300">
            <AlertTriangle size={14} />
            Explicit System Uncertainties:
          </div>
          <ul className="list-disc list-inside space-y-0.5 text-amber-200/90 pl-1">
            {decision.uncertainty.map((u, idx) => (
              <li key={idx}>{u}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Recommended Actions */}
      <div>
        <h4 className="text-xs font-semibold text-slate-300 uppercase tracking-wider mb-2.5 flex items-center gap-1.5">
          <ClipboardList size={14} className="text-indigo-400" />
          Recommended Operational Actions
        </h4>
        <div className="space-y-2">
          {decision.recommended_actions?.map((act, idx) => (
            <div key={idx} className="p-3 rounded-lg bg-slate-800/40 border border-slate-700/60 flex items-start justify-between gap-3">
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-mono px-2 py-0.5 rounded bg-slate-700 text-slate-300">{act.action_id}</span>
                  <span className="text-sm font-medium text-slate-200">{act.title}</span>
                  <span className="text-[10px] px-2 py-0.5 rounded-full bg-cyan-950 text-cyan-300 border border-cyan-800">
                    CVKI Recommended Action
                  </span>
                </div>
                <p className="text-xs text-slate-300">{act.description}</p>
                {act.safety_warning && (
                  <p className="text-xs text-amber-400 flex items-center gap-1">
                    <AlertCircle size={12} />
                    {act.safety_warning}
                  </p>
                )}
              </div>
              <span className={`text-[10px] uppercase font-semibold px-2 py-1 rounded shrink-0 ${
                act.priority === 'urgent' ? 'bg-rose-900/60 text-rose-200' : 'bg-slate-700 text-slate-300'
              }`}>
                {act.priority || 'standard'}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Field Inspection Checkpoints */}
      {decision.required_inspection && decision.required_inspection.length > 0 && (
        <div className="p-3.5 rounded-lg bg-slate-800/40 border border-slate-700/60 space-y-2">
          <div className="flex items-center justify-between">
            <h4 className="text-xs font-semibold text-slate-300 uppercase tracking-wider flex items-center gap-1.5">
              <Eye size={14} className="text-cyan-400" />
              Required Field Inspection Checkpoints
            </h4>
            {onOpenInspection && (
              <button
                type="button"
                onClick={onOpenInspection}
                className="text-xs bg-cyan-600 hover:bg-cyan-500 text-white font-medium px-3 py-1 rounded-md transition-colors"
              >
                Open Field Protocol
              </button>
            )}
          </div>
          <ul className="list-disc list-inside space-y-1 text-xs text-slate-300 pl-1">
            {decision.required_inspection.map((chk, idx) => (
              <li key={idx}>{chk}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Matched Playbooks */}
      {decision.matched_playbooks && decision.matched_playbooks.length > 0 && (
        <div className="text-xs text-slate-400 flex items-center gap-2">
          <span className="text-slate-500">Matched Playbook:</span>
          {decision.matched_playbooks.map((pb, idx) => (
            <span key={idx} className="font-mono bg-slate-800 px-2 py-0.5 rounded border border-slate-700 text-slate-300">
              {pb}
            </span>
          ))}
        </div>
      )}

      {/* Human Review Action Section */}
      <div className="border-t border-slate-800 pt-4 flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">
        <div className="flex-1">
          <input
            type="text"
            value={reviewNotes}
            onChange={(e) => setReviewNotes(e.target.value)}
            placeholder="Optional review notes before acknowledging..."
            className="w-full text-xs bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-slate-200 placeholder:text-slate-500 focus:outline-none focus:border-cyan-500"
          />
        </div>
        <button
          type="button"
          onClick={handleReview}
          disabled={reviewing || !!reviewResult}
          className="text-xs bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white font-semibold px-4 py-2 rounded-lg transition-colors flex items-center justify-center gap-1.5 shrink-0"
        >
          {reviewing ? <LoaderCircle size={14} className="animate-spin" /> : <FileCheck2 size={14} />}
          {reviewResult ? 'Recommendation Reviewed' : 'Mark Recommendation Reviewed'}
        </button>
      </div>

      {reviewResult && (
        <div className="text-xs text-emerald-400 flex items-center gap-1.5 p-2 bg-emerald-950/40 rounded border border-emerald-800">
          <CheckCircle2 size={14} />
          <span>Review recorded in provenance audit trail (Evidence ID: {reviewResult.evidence_id?.slice(0, 12)}). Case status remains governed by human process.</span>
        </div>
      )}
    </div>
  );
}
