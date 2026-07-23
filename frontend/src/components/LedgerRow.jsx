export default function LedgerRow({ label, value, matched }) {
  return (
    <div className={`flex items-baseline gap-2 py-1.5 rounded-sm transition-colors
      ${matched === true ? "bg-registrar/5 -mx-2 px-2" :
        matched === false ? "bg-seal/5 -mx-2 px-2" : ""}`}>
      <span className="text-sm text-ink-soft shrink-0">{label}</span>
      <span className="flex-1 border-b border-dotted border-paper-line -translate-y-[3px]"
        aria-hidden="true" />
      <span className={`text-sm font-mono text-right
        ${matched === true ? "text-registrar font-medium" :
          matched === false ? "text-seal" : "text-ink"}`}>
        {value || "—"}
      </span>
    </div>
  );
}