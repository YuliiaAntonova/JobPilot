import { useState } from "react";
import { Download } from "lucide-react";
import { downloadProfileResume, profileHasResume } from "../../lib/jobseekerProfile";

/**
 * @param {{ structured?: object | null, className?: string, size?: "md" | "lg", alwaysShow?: boolean }} props
 */
export default function ResumeDownloadBar({ structured = null, className = "", size = "md", alwaysShow = false }) {
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");

  const ready = profileHasResume(structured);
  const pad = size === "lg" ? "px-6 py-4 text-lg" : "px-4 py-2 text-sm";
  const icon = size === "lg" ? 20 : 16;

  async function handleDownload(format) {
    if (!ready || busy) return;
    setErr("");
    setBusy(format);
    try {
      await downloadProfileResume(format);
    } catch (e) {
      setErr(String(e.message || e));
    } finally {
      setBusy("");
    }
  }

  if (!ready && !alwaysShow) {
    return null;
  }

  return (
    <div className={className}>
      <div className="flex flex-wrap items-center gap-3 rounded-2xl border-2 border-teal-300 bg-teal-50 p-4 shadow-sm">
        <p className="w-full text-sm font-black uppercase tracking-wide text-teal-900">Download resume</p>
        {!ready ? (
          <p className="text-sm font-semibold text-slate-600">
            Complete the career interview or upload a PDF first.
          </p>
        ) : (
          <>
        <button
          type="button"
          disabled={Boolean(busy)}
          onClick={() => handleDownload("pdf")}
          className={`inline-flex items-center justify-center gap-2 rounded-xl bg-teal-600 font-black text-white hover:bg-teal-700 disabled:opacity-50 ${pad}`}
        >
          <Download size={icon} />
          {busy === "pdf" ? "Downloading…" : "Download PDF"}
        </button>
          </>
        )}
      </div>
      {err ? <p className="mt-2 text-sm font-semibold text-red-700">{err}</p> : null}
    </div>
  );
}
