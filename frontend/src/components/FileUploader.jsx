import { useState, useRef } from "react";
import { motion } from "framer-motion";
import { verifyCertificate } from "../lib/api";

const ACCEPTED_TYPES = ["image/jpeg", "image/png", "image/webp", "application/pdf"];
const MAX_SIZE_MB = 15;

function UploadIcon() {
  return (
    <svg width="28" height="28" viewBox="0 0 24 24" fill="none" className="text-ink-soft/70" aria-hidden="true">
      <path d="M12 16V4M12 4l-4 4M12 4l4 4" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M4 16v3a1 1 0 001 1h14a1 1 0 001-1v-3" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
    </svg>
  );
}

function PdfIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" className="text-ink-soft shrink-0" aria-hidden="true">
      <path d="M5 3h9l5 5v13a1 1 0 01-1 1H5a1 1 0 01-1-1V4a1 1 0 011-1z" stroke="currentColor" strokeWidth="1.3" />
      <path d="M14 3v5h5" stroke="currentColor" strokeWidth="1.3" />
    </svg>
  );
}

function networkErrorResult() {
  return {
    final_decision: "ERROR",
    confidence_score: 0,
    ai_match_score: 0,
    tamper_probability: 0,
    extracted_metadata: {
      candidate_name: null,
      roll_no: null,
      reg_no: null,
      total_marks: null,
      institution: null,
      error: "Couldn't reach the verification server. Check your connection and try again.",
    },
    qr_verification: {
      status: "NOT_FOUND",
      is_secure: false,
      data: null,
      domain: null,
      domain_authenticity: false,
    },
  };
}

export default function FileUploader({ setResults, setLoading }) {
  const [preview, setPreview] = useState(null);
  const [fileName, setFileName] = useState(null);
  const [isDragging, setIsDragging] = useState(false);
  const [validationError, setValidationError] = useState(null);
  const inputRef = useRef(null);

  const processFile = async (file) => {
    if (!file) return;
    setValidationError(null);

    if (!ACCEPTED_TYPES.includes(file.type)) {
      setValidationError("Please upload a JPG, PNG, or PDF file.");
      return;
    }
    if (file.size > MAX_SIZE_MB * 1024 * 1024) {
      setValidationError(`That file is larger than ${MAX_SIZE_MB}MB. Try a smaller scan.`);
      return;
    }

    setFileName(file.name);
    setPreview(file.type !== "application/pdf" ? URL.createObjectURL(file) : null);
    setResults(null);
    setLoading(true);

    try {
      const data = await verifyCertificate(file);
      setResults(data);
    } catch (err) {
      setResults(networkErrorResult());
    } finally {
      setLoading(false);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragging(false);
    processFile(e.dataTransfer.files[0]);
  };

  return (
    <div className="bg-white/60 border border-paper-line rounded-sm p-6 shadow-sm">
      <h2 className="font-display text-lg text-ink mb-1">Upload a certificate</h2>
      <p className="text-sm text-ink-soft mb-4">
        We'll check it against the issuing board's record and scan for signs of tampering.
      </p>

      <label
        onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={handleDrop}
        className={`flex flex-col items-center justify-center gap-2 h-44 border-2 border-dashed rounded-sm cursor-pointer transition-colors ${
          isDragging ? "border-steel bg-steel/5" : "border-paper-line hover:border-steel/60"
        }`}
      >
        <UploadIcon />
        <span className="text-sm text-ink-soft text-center px-4">
          Drag a certificate here, or <span className="text-steel underline">browse your files</span>
        </span>
        <span className="text-xs text-ink-soft/70">JPG, PNG, or PDF · up to {MAX_SIZE_MB}MB</span>
        <input
          ref={inputRef}
          type="file"
          className="hidden"
          onChange={(e) => processFile(e.target.files[0])}
          accept="image/jpeg,image/png,image/webp,application/pdf"
        />
      </label>

      {validationError && (
        <p className="mt-3 text-sm text-seal" role="alert">{validationError}</p>
      )}

      {fileName && !validationError && (
        <motion.div
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          className="mt-4 pt-4 border-t border-paper-line"
        >
          <p className="text-xs text-ink-soft mb-2">Document received</p>
          {preview ? (
            <img src={preview} alt={`Preview of ${fileName}`} className="w-full rounded-sm border border-paper-line" />
          ) : (
            <div className="flex items-center gap-2 text-sm text-ink bg-paper rounded-sm border border-paper-line px-3 py-2">
              <PdfIcon />
              {fileName}
            </div>
          )}
        </motion.div>
      )}
    </div>
  );
}
