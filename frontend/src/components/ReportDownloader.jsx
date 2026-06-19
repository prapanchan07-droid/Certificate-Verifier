import { useState } from "react";
import { downloadReport } from "../lib/api";

export default function ReportDownloader({ results }) {
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState(null);

  const handleDownload = async () => {
    setDownloading(true);
    setError(null);

    try {
      const blob = await downloadReport(results);
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `verification-report-${results?.extracted_metadata?.roll_no || "certificate"}.pdf`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      setError("Couldn't generate the report. Try again in a moment.");
    } finally {
      setDownloading(false);
    }
  };

  return (
    <div>
      <button
        onClick={handleDownload}
        disabled={downloading}
        className="w-full bg-ink hover:bg-ink/90 disabled:opacity-60 disabled:cursor-not-allowed text-paper font-medium py-3 rounded-sm transition-colors"
      >
        {downloading ? "Preparing report…" : "Download verification report"}
      </button>
      {error && <p className="text-sm text-seal mt-2" role="alert">{error}</p>}
    </div>
  );
}
