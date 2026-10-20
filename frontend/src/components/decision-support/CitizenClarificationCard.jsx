import { useState } from 'react';
import { CheckCircle2, HelpCircle, LoaderCircle, Send } from 'lucide-react';
import { submitCitizenClarification } from '../../services/decisionSupportApi';

export function CitizenClarificationCard({ referenceId, question, onAnswered }) {
  const [selectedOption, setSelectedOption] = useState('');
  const [freeText, setFreeText] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!selectedOption && !freeText) {
      setError('Please select an option or provide text details.');
      return;
    }
    setError(null);
    setSubmitting(true);

    try {
      const payload = {
        question_id: question.question_id,
        selected_option: selectedOption || undefined,
        free_text: freeText || undefined,
        language: 'en',
      };
      const res = await submitCitizenClarification(referenceId, payload);
      setSubmitted(true);
      setMessage(res.message || 'Clarification received.');
      if (onAnswered) onAnswered(res);
    } catch (err) {
      setError(err?.message || 'Failed to submit clarification.');
    } finally {
      setSubmitting(false);
    }
  };

  if (submitted) {
    return (
      <div className="p-4 rounded-xl bg-emerald-950/40 border border-emerald-800/60 text-emerald-200 text-xs flex items-start gap-2.5">
        <CheckCircle2 size={16} className="text-emerald-400 shrink-0 mt-0.5" />
        <div>
          <p className="font-semibold text-emerald-300">Thank you for clarifying!</p>
          <p className="mt-0.5 text-emerald-200/90">{message}</p>
          <p className="text-[11px] text-emerald-400/80 mt-1 italic">
            Your response is logged as a citizen-reported observation to help municipal responders.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-sky-800/60 bg-sky-950/20 text-slate-100 p-4 shadow-lg space-y-3">
      <div className="flex items-start gap-2.5">
        <HelpCircle size={18} className="text-sky-400 shrink-0 mt-0.5" />
        <div className="space-y-1 flex-1">
          <h4 className="text-sm font-semibold text-sky-200">{question.question_text}</h4>
          {question.reason && (
            <p className="text-xs text-sky-300/80">
              <span className="font-medium text-sky-300">Why this helps:</span> {question.reason}
            </p>
          )}
        </div>
      </div>

      <form onSubmit={handleSubmit} className="space-y-3 pt-1">
        {question.options && question.options.length > 0 ? (
          <div className="space-y-1.5">
            {question.options.map((opt, idx) => (
              <label
                key={idx}
                className={`flex items-center gap-2 p-2 rounded-lg border text-xs cursor-pointer transition-colors ${
                  selectedOption === opt
                    ? 'bg-sky-900/60 border-sky-500 text-white font-medium'
                    : 'bg-slate-900/60 border-slate-700/60 text-slate-300 hover:bg-slate-800'
                }`}
              >
                <input
                  type="radio"
                  name={`clarify_${question.question_id}`}
                  value={opt}
                  checked={selectedOption === opt}
                  onChange={() => setSelectedOption(opt)}
                  className="text-sky-500 bg-slate-950 border-slate-700 focus:ring-0"
                />
                <span>{opt}</span>
              </label>
            ))}
          </div>
        ) : (
          <div>
            <textarea
              rows={2}
              placeholder="Provide clarifying details..."
              value={freeText}
              onChange={(e) => setFreeText(e.target.value)}
              className="w-full text-xs bg-slate-950 border border-slate-700 rounded-lg p-2.5 text-slate-200 placeholder:text-slate-500 focus:outline-none focus:border-sky-500"
            />
          </div>
        )}

        {error && <p className="text-xs text-rose-400">{error}</p>}

        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2 pt-1 border-t border-sky-900/40">
          <p className="text-[11px] text-slate-400 italic">
            Your answer will be treated as a reported observation.
          </p>
          <button
            type="submit"
            disabled={submitting}
            className="text-xs bg-sky-600 hover:bg-sky-500 disabled:opacity-50 text-white font-medium px-4 py-1.5 rounded-lg transition-colors flex items-center gap-1.5 shrink-0"
          >
            {submitting ? <LoaderCircle size={13} className="animate-spin" /> : <Send size={13} />}
            Submit Clarification
          </button>
        </div>
      </form>
    </div>
  );
}
