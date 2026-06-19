import { useState } from "react";
import FileUploader from "./components/FileUploader";
import VerificationMetrics from "./components/VerificationMetrics";
import Dashboard from "./components/Dashboard";
import SealMark from "./components/SealMark";

export default function App() {
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(false);

  return (
    <div className="min-h-screen bg-paper text-ink font-body flex flex-col">
      <header className="border-b-2 border-ink/80">
        <div className="max-w-6xl mx-auto px-6 py-5 flex items-center justify-between gap-4 flex-wrap">
          <div className="flex items-center gap-3">
            <SealMark />
            <div>
              <h1 className="font-display text-2xl text-ink leading-none">Attest</h1>
              <p className="text-xs text-ink-soft tracking-wide mt-0.5">Certificate Verification</p>
            </div>
          </div>
          <p className="text-xs text-ink-soft text-right max-w-xs hidden sm:block">
            Checks Tamil Nadu SSLC &amp; HSC certificates against the issuing board's record.
          </p>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-6 py-10 grid grid-cols-1 lg:grid-cols-3 gap-8 flex-1 w-full">
        <div className="lg:col-span-1 space-y-6">
          <FileUploader setResults={setResults} setLoading={setLoading} />
          {results && results.final_decision !== "ERROR" && <VerificationMetrics results={results} />}
        </div>

        <div className="lg:col-span-2">
          <Dashboard results={results} loading={loading} />
        </div>
      </main>

      <footer className="max-w-6xl mx-auto px-6 pb-10 text-xs text-ink-soft/70 w-full">
        This tool cross-checks the QR code printed on the certificate against the issuing board's published record. It does not replace verification directly with the board.
      </footer>
    </div>
  );
}
