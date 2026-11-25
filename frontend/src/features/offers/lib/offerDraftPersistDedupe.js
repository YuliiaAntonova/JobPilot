/** Pure helpers for offer-draft PUT dedupe (no browser deps). */

export function offerDraftPersistFingerprint(jobId, body) {
  const a = body?.analysis && typeof body.analysis === "object" ? body.analysis : {};
  const rt = a.resume_tailoring && typeof a.resume_tailoring === "object" ? a.resume_tailoring : {};
  return [
    String(jobId || ""),
    String(body?.jd_text || ""),
    String(body?.resume_paste || ""),
    String(body?.cover_letter_text || ""),
    String(body?.tailored_resume_text || ""),
    String(body?.model || ""),
    String(a.company_name || ""),
    String(a.job_title || a.target_job_title || ""),
    String(a.match_score ?? ""),
    String(a.tailored_resume_text || ""),
    String(rt.phase || ""),
    String((a.cover_letter_draft || "").length),
    String((rt.ask_user || []).length),
    String((rt.selected_ids || []).length),
  ].join("\x1e");
}

export function createOfferDraftPutGate() {
  let lastFingerprint = "";
  let inflight = null;
  let inflightFingerprint = "";

  return {
    reset() {
      lastFingerprint = "";
      inflight = null;
      inflightFingerprint = "";
    },
    /** @returns {"skip"|"join"| "run"} */
    decide(fingerprint) {
      if (fingerprint === lastFingerprint) return "skip";
      if (inflight && inflightFingerprint === fingerprint) return "join";
      return "run";
    },
    begin(fingerprint, promise) {
      inflight = promise;
      inflightFingerprint = fingerprint;
      return promise.finally(() => {
        if (inflightFingerprint === fingerprint) {
          inflight = null;
          inflightFingerprint = "";
        }
      });
    },
    markSaved(fingerprint) {
      lastFingerprint = fingerprint;
    },
    getInflight() {
      return inflight;
    },
  };
}
