import { motion } from "framer-motion";
import VerdictStamp from "./VerdictStamp";
import LedgerRow from "./LedgerRow";
import ReportDownloader from "./ReportDownloader";

const CHECK_LABELS = {
  roll_no_match: "Roll number",
  reg_no_match: "Register number",
  candidate_name_match: "Candidate name",
  total_marks_match: "Total marks",
  institution_match: "Issuing institution",
};

const VERDICT_MESSAGES = {
  GENUINE:    "This certificate matches the official record.",
  SUSPICIOUS: "Some details don't match the official record.",
  FAKE:       "This certificate doesn't match the official record.",
  UNVERIFIED: "We couldn't reach the official record to verify this certificate.",
};

function CheckMark({ ok }) {
  return ok ? (
    <svg width="15" height="15" viewBox="0 0 16 16"
      className="text-registrar shrink-0" aria-hidden="true">
      <path d="M3 8.5l3 3 7-7" stroke="currentColor" strokeWidth="2"
        fill="none" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ) : (
    <svg width="15" height="15" viewBox="0 0 16 16"
      className="text-seal/60 shrink-0" aria-hidden="true">
      <path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" strokeWidth="2"
        fill="none" strokeLinecap="round" />
    </svg>
  );
}

function LoadingState() {
  return (
    <div className="bg-white/40 border border-paper-line rounded-sm h-[420px]
      flex flex-col items-center justify-center gap-4"
      role="status" aria-live="polite">
      <div className="w-24 h-24 animate-hover">
        <svg viewBox="0 0 200 200" className="w-full h-full" aria-hidden="true">
          <circle cx="100" cy="100" r="86" fill="none" stroke="#1E2A44"
            strokeWidth="3" strokeDasharray="2 6" opacity="0.4" />
          <circle cx="100" cy="100" r="72" fill="none" stroke="#1E2A44"
            strokeWidth="2" opacity="0.25" />
        </svg>
      </div>
      <p className="font-mono text-xs tracking-widest text-ink-soft uppercase">
        Checking against official records
      </p>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="bg-white/30 border border-dashed border-paper-line rounded-sm
      h-[420px] flex flex-col items-center justify-center gap-3 text-center px-8">
      <svg width="40" height="40" viewBox="0 0 24 24" fill="none"
        className="text-ink-soft/50" aria-hidden="true">
        <path d="M5 3h9l5 5v13a1 1 0 01-1 1H5a1 1 0 01-1-1V4a1 1 0 011-1z"
          stroke="currentColor" strokeWidth="1.3" />
        <path d="M14 3v5h5" stroke="currentColor" strokeWidth="1.3" />
      </svg>
      <p className="text-ink-soft text-sm max-w-[28ch]">
        Upload a certificate on the left to start a check.
      </p>
    </div>
  );
}

// Marksheet-style details card — shows official data when available,
// falls back to OCR when QR not found or official record unreachable.
function DetailsCard({ displayMetadata, checks, hasOfficialData }) {
  const fromOfficial = displayMetadata?.source === "official_record";

  const fields = [
    { label: "Candidate",       key: "candidate_name", checkKey: "candidate_name_match" },
    { label: "Roll number",     key: "roll_no",        checkKey: "roll_no_match" },
    { label: "Register number", key: "reg_no",         checkKey: "reg_no_match" },
    { label: "Total marks",     key: "total_marks",    checkKey: "total_marks_match" },
    { label: "Institution",     key: "institution",    checkKey: "institution_match" },
  ];

  return (
    <div className="bg-white/60 border border-paper-line rounded-sm p-6">
      <div className="flex items-center justify-between pb-2 mb-3 border-b border-paper-line gap-2 flex-wrap">
        <h3 className="font-display text-base text-ink">Printed details</h3>
        {fromOfficial ? (
          <span className="text-xs font-mono text-registrar bg-registrar/10
            px-2 py-0.5 rounded-sm flex items-center gap-1">
            <svg width="10" height="10" viewBox="0 0 16 16" fill="none" aria-hidden="true">
              <path d="M3 8.5l3 3 7-7" stroke="currentColor" strokeWidth="2.5"
                strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
            Official record
          </span>
        ) : (
          <span className="text-xs font-mono text-caution bg-caution/10
            px-2 py-0.5 rounded-sm">
            OCR extracted
          </span>
        )}
      </div>

      <div>
        {fields.map(({ label, key, checkKey }) => {
          // Only show match/mismatch colour when we have official data to compare
          const matched = hasOfficialData
            ? (checks[checkKey] === true ? true : checks[checkKey] === false ? false : undefined)
            : undefined;
          return (
            <LedgerRow
              key={key}
              label={label}
              value={displayMetadata?.[key]}
              matched={matched}
            />
          );
        })}
      </div>

      {!fromOfficial && (
        <p className="text-xs text-ink-soft/60 mt-3 pt-2 border-t border-paper-line">
          {displayMetadata
            ? "QR code not found or official record unreachable — details extracted by OCR and may contain minor errors."
            : "No details could be extracted from this certificate."}
        </p>
      )}
    </div>
  );
}

export default function Dashboard({ results, loading }) {
  if (loading) return <LoadingState />;
  if (!results) return <EmptyState />;

  const {
    final_decision,
    confidence_score,
    extracted_metadata,
    display_metadata,
    qr_verification,
    official_verification,
    ml_verification,
  } = results;

  if (final_decision === "ERROR") {
    return (
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}
        className="bg-white/60 border border-paper-line rounded-sm p-8
          flex flex-col items-center text-center gap-4">
        <VerdictStamp verdict="ERROR" confidence={confidence_score} />
        <div>
          <h2 className="font-display text-lg text-ink mb-1">
            We couldn't read this file
          </h2>
          <p className="text-sm text-ink-soft max-w-md">
            {extracted_metadata?.error ||
              "Something went wrong while processing this certificate."}{" "}
            Try a clearer photo, or upload it as a PDF.
          </p>
        </div>
      </motion.div>
    );
  }

  const officialStatus = official_verification?.status;
  const checks = official_verification?.checks || {};
  const hasOfficialData = officialStatus === "MATCHED";
  const matchCount = Object.values(checks).filter(Boolean).length;
  const totalChecks = Object.keys(CHECK_LABELS).length;
  const verdictMessage = VERDICT_MESSAGES[final_decision] ?? "Result inconclusive.";

  // Use display_metadata (official > OCR) if available, fall back to extracted_metadata
  const shownData = display_metadata || {
    candidate_name: extracted_metadata?.candidate_name,
    roll_no:        extracted_metadata?.roll_no,
    reg_no:         extracted_metadata?.reg_no,
    total_marks:    extracted_metadata?.total_marks,
    institution:    extracted_metadata?.institution,
    source:         "ocr_extraction",
  };

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}
      className="space-y-6">

      {/* Verdict band */}
      <div className="bg-white/60 border border-paper-line rounded-sm p-6
        flex items-center gap-6 flex-wrap">
        <VerdictStamp verdict={final_decision} confidence={confidence_score} />
        <div className="flex-1 min-w-[180px]">
          <p className="text-xs uppercase tracking-widest text-ink-soft mb-1">Result</p>
          <p className="font-display text-2xl text-ink mb-2">{verdictMessage}</p>
          <p className="text-sm text-ink-soft">
            Confidence:{" "}
            <span className="font-mono text-ink">{confidence_score}%</span>
          </p>
          {/* ML explanation if available */}
          {ml_verification?.explanation && (
            <p className="text-sm text-ink-soft mt-2 pt-2 border-t border-paper-line">
              {ml_verification.explanation}
            </p>
          )}
        </div>
      </div>

      {/* Official record checks */}
      <div className="bg-white/60 border border-paper-line rounded-sm p-6">
        <div className="flex items-baseline justify-between mb-4 gap-4 flex-wrap">
          <h3 className="font-display text-lg text-ink">
            Checked against the issuing board
          </h3>
          {hasOfficialData && (
            <span className="text-xs font-mono text-ink-soft">
              {matchCount} of {totalChecks} match
            </span>
          )}
        </div>

        {hasOfficialData ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-8 gap-y-2">
            {Object.entries(CHECK_LABELS).map(([key, label]) => (
              <div key={key} className="flex items-center gap-2 text-sm">
                <CheckMark ok={Boolean(checks[key])} />
                <span className="text-ink">{label}</span>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-sm text-ink-soft">
            {officialStatus === "UNAVAILABLE"
              ? "We found a QR code, but couldn't reach the issuing board's record to compare it."
              : qr_verification?.data
              ? "We found a QR code, but the official record check was skipped."
              : "No QR code was found on this certificate, so we couldn't check it against the issuing board's record."}
          </p>
        )}
      </div>

      {/* Details + QR */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">

        {/* Marksheet details card */}
        <DetailsCard
          displayMetadata={shownData}
          checks={checks}
          hasOfficialData={hasOfficialData}
        />

        {/* QR card */}
        <div className="bg-white/60 border border-paper-line rounded-sm p-6">
          <h3 className="font-display text-base text-ink border-b border-paper-line pb-2 mb-3">
            QR code
          </h3>
          {qr_verification?.status === "SCANNED" ? (
            <div className="space-y-2">
              <LedgerRow label="Domain" value={qr_verification.domain} />
              <LedgerRow label="Secure (HTTPS)"
                value={qr_verification.is_secure ? "Yes" : "No"} />
              <LedgerRow label="Recognised official domain"
                value={qr_verification.domain_authenticity ? "Yes" : "No"} />
              <p className="text-xs text-ink-soft/70 break-all font-mono mt-3
                bg-paper border border-paper-line rounded-sm p-2">
                {qr_verification.data}
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              <p className="text-sm text-ink-soft">
                No QR code was found on this certificate.
              </p>
              <p className="text-xs text-caution bg-caution/10 rounded-sm px-3 py-2">
                Without a QR code the details shown are extracted by OCR and
                cannot be cross-checked against the issuing board's record.
              </p>
            </div>
          )}
        </div>
      </div>

      {/* ML feature breakdown — shown when available */}
      {ml_verification?.top_factors?.length > 0 && (
        <div className="bg-white/60 border border-paper-line rounded-sm p-6">
          <h3 className="font-display text-base text-ink border-b border-paper-line pb-2 mb-4">
            AI model — top decision factors
          </h3>
          <div className="space-y-3">
            {ml_verification.top_factors.slice(0, 6).map((f) => (
              <div key={f.feature}>
                <div className="flex justify-between text-xs mb-1">
                  <span className="text-ink-soft font-mono">
                    {f.feature.replace(/_/g, " ")}
                  </span>
                  <span className="text-ink font-mono">
                    value {f.value} · weight {f.importance}
                  </span>
                </div>
                <div className="h-1 bg-paper-line/50 rounded-full overflow-hidden">
                  <div
                    className="h-full rounded-full bg-steel transition-all duration-700"
                    style={{ width: `${Math.round(f.importance * 100 * 5)}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <ReportDownloader results={results} />
    </motion.div>
  );
}