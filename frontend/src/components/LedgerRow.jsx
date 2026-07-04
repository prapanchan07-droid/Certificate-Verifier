export default function LedgerRow({ label, value }) {
  return (
    <div className="flex items-baseline gap-2 py-1.5">
      <span className="text-sm text-ink-soft shrink-0">{label}</span>
      <span className="flex-1 border-b border-dotted border-paper-line -translate-y-[3px]" aria-hidden="true" />
      <span className="text-sm font-mono text-ink text-right">{value || "—"}</span>
    </div>
  );
}
