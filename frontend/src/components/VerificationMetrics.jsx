function ScanBar({ label, caption, value, color }) {
  const pct = Math.round(value * 100);
  return (
    <div>
      <div className="flex justify-between items-baseline text-xs mb-1">
        <span className="text-ink-soft">{label}</span>
        <span className="font-mono text-ink">{pct}%</span>
      </div>
      <div className="h-1.5 bg-paper-line/50 rounded-full overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-700 ease-out"
          style={{ width: `${pct}%`, backgroundColor: color }}
        />
      </div>
      <p className="text-[11px] text-ink-soft/70 mt-1">{caption}</p>
    </div>
  );
}

export default function VerificationMetrics({ results }) {
  const { ai_match_score, tamper_probability } = results;

  return (
    <div className="bg-white/60 border border-paper-line rounded-sm p-6 space-y-5">
      <h3 className="font-display text-base text-ink">Document scan</h3>
      <ScanBar
        label="Layout match"
        caption="How closely the layout matches the official template"
        value={ai_match_score}
        color="#2E5677"
      />
      <ScanBar
        label="Signs of tampering"
        caption="Likelihood the document has been altered"
        value={tamper_probability}
        color="#8C3A2E"
      />
    </div>
  );
}
