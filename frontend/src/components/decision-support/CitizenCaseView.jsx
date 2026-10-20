import { useEffect, useState } from 'react';
import {
  CheckCircle2,
  Clock,
  HelpCircle,
  LoaderCircle,
  MapPin,
} from 'lucide-react';
import { getCitizenView } from '../../services/decisionSupportApi';
import { CitizenClarificationCard } from './CitizenClarificationCard';

export function CitizenCaseView({ referenceId }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    let isMounted = true;
    setLoading(true);
    setError(null);

    getCitizenView(referenceId)
      .then((res) => {
        if (!isMounted) return;
        setData(res);
        setLoading(false);
      })
      .catch((err) => {
        if (!isMounted) return;
        setError(err?.message || 'Case view is currently unavailable.');
        setLoading(false);
      });

    return () => {
      isMounted = false;
    };
  }, [referenceId, refreshKey]);

  if (loading) {
    return (
      <div className="p-4 rounded-xl border border-slate-700 bg-slate-900/60 text-slate-300 flex items-center gap-3">
        <LoaderCircle size={18} className="animate-spin text-sky-400" />
        <span>Loading case status and guidance...</span>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="p-4 rounded-xl border border-slate-800 bg-slate-900/40 text-slate-400">
        <p className="text-xs text-rose-400">{error || 'Case information unavailable.'}</p>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-slate-700/80 bg-slate-900/90 text-slate-100 p-5 shadow-xl space-y-5">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 pb-3">
        <div>
          <span className="text-xs text-sky-400 font-mono tracking-wide">{data.case_reference}</span>
          <h3 className="text-base font-semibold text-slate-100 mt-0.5">{data.issue_category}</h3>
        </div>
        <span className="text-xs px-3 py-1 rounded-full font-medium bg-slate-800 border border-slate-700 text-slate-200 uppercase">
          Status: {data.status?.replace(/_/g, ' ')}
        </span>
      </div>

      {/* Simplified Explanation */}
      <div className="p-3.5 rounded-lg bg-slate-800/50 border border-slate-700/50 text-sm text-slate-200 leading-relaxed">
        {data.simplified_explanation}
      </div>

      {/* Clarification Questions (M9.3 Active Clarification) */}
      {data.clarification_required && data.clarification_questions && data.clarification_questions.length > 0 && (
        <div className="space-y-3">
          <div className="flex items-center gap-2 text-sky-300 font-medium text-xs uppercase tracking-wider">
            <HelpCircle size={15} />
            <span>Clarification Needed to Assist Responders</span>
          </div>
          {data.clarification_questions.map((q, idx) => (
            <CitizenClarificationCard
              key={idx}
              referenceId={data.case_reference}
              question={q}
              onAnswered={() => setRefreshKey((k) => k + 1)}
            />
          ))}
        </div>
      )}

      {/* Available Evidence & What is Needed */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div className="p-3.5 rounded-lg bg-slate-800/40 border border-slate-700/50 space-y-1.5">
          <h4 className="text-xs font-semibold text-emerald-300 flex items-center gap-1.5">
            <CheckCircle2 size={13} /> Current Evidence Recorded
          </h4>
          <ul className="list-disc list-inside text-xs text-slate-300 space-y-0.5">
            {data.available_evidence?.map((item, idx) => (
              <li key={idx}>{item}</li>
            ))}
          </ul>
        </div>

        <div className="p-3.5 rounded-lg bg-slate-800/40 border border-slate-700/50 space-y-1.5">
          <h4 className="text-xs font-semibold text-amber-300 flex items-center gap-1.5">
            <Clock size={13} /> Additional Information Needed
          </h4>
          <ul className="list-disc list-inside text-xs text-slate-300 space-y-0.5">
            {data.additional_information_needed?.length > 0 ? (
              data.additional_information_needed.map((item, idx) => (
                <li key={idx}>{item}</li>
              ))
            ) : (
              <li className="list-none text-slate-400 italic">No additional citizen data required at this stage.</li>
            )}
          </ul>
        </div>
      </div>

      {/* Public Location Privacy (Approximate coordinates + road/area) */}
      {data.public_location && (
        <div className="p-3 rounded-lg bg-slate-800/30 border border-slate-700/40 text-xs text-slate-300 flex items-start gap-2">
          <MapPin size={15} className="text-rose-400 shrink-0 mt-0.5" />
          <div className="space-y-0.5">
            <span className="font-semibold text-slate-200">Public Location Area:</span>
            <p className="text-slate-300">
              {[data.public_location.road, data.public_location.area, data.public_location.city].filter(Boolean).join(', ') || 'Recorded Location'}
            </p>
            {data.public_location.latitude_approx && (
              <p className="text-[11px] text-slate-400 font-mono">
                Approx coords: ~{data.public_location.latitude_approx}, ~{data.public_location.longitude_approx}
                <span className="text-slate-400 ml-1.5 italic font-sans">
                  ({data.public_location.privacy_note || 'Approximated for residential privacy'})
                </span>
              </p>
            )}
          </div>
        </div>
      )}

      {/* Follow-up Guidance */}
      {data.follow_up_guidance && data.follow_up_guidance.length > 0 && (
        <div className="p-3 rounded-lg bg-indigo-950/20 border border-indigo-800/30 text-xs text-indigo-200 space-y-1">
          <span className="font-semibold text-indigo-300 block">Next Steps &amp; Follow-up:</span>
          <ul className="list-disc list-inside space-y-0.5 text-indigo-200/90 pl-1">
            {data.follow_up_guidance.map((g, idx) => (
              <li key={idx}>{g}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Disclaimer */}
      <div className="text-[11px] text-slate-400 border-t border-slate-800 pt-3 italic">
        {data.disclaimer}
      </div>
    </div>
  );
}
