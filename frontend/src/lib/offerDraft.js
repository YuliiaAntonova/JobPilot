/** Session draft for New offer → cover letter step. Wizard reads the same key (ignores extra fields). */

export const JOB_OFFER_DRAFT_KEY = "job_offer_draft_v1";

export function readOfferDraft() {
  try {
    const raw = sessionStorage.getItem(JOB_OFFER_DRAFT_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    const jd_text = parsed.jd_text;
    const analysis = parsed.analysis ?? null;
    if (!jd_text || typeof jd_text !== "string" || !analysis || typeof analysis !== "object") return null;
    return {
      job_id: typeof parsed.job_id === "string" ? parsed.job_id : "",
      jd_text,
      analysis,
      model: typeof parsed.model === "string" ? parsed.model : "",
      resume_paste: typeof parsed.resume_paste === "string" ? parsed.resume_paste : "",
      cover_letter_text:
        typeof parsed.cover_letter_text === "string"
          ? parsed.cover_letter_text
          : (analysis.cover_letter_draft ?? ""),
      tailored_resume_text:
        typeof parsed.tailored_resume_text === "string" ? parsed.tailored_resume_text : "",
      saved_at: typeof parsed.saved_at === "string" ? parsed.saved_at : null,
    };
  } catch {
    return null;
  }
}

export function writeOfferDraft(draft) {
  sessionStorage.setItem(JOB_OFFER_DRAFT_KEY, JSON.stringify(draft));
}

/** Merge with existing draft (step 1 + step 2). */
export function mergeOfferDraft(patch) {
  const existing = readOfferDraft();
  const jd_text = patch.jd_text ?? existing?.jd_text ?? "";
  const analysis = patch.analysis ?? existing?.analysis ?? null;
  if (!jd_text || !analysis) return null;
  const merged = {
    job_id: patch.job_id ?? existing?.job_id ?? "",
    jd_text,
    analysis,
    model: patch.model ?? existing?.model ?? "",
    resume_paste: patch.resume_paste ?? existing?.resume_paste ?? "",
    cover_letter_text: patch.cover_letter_text ?? existing?.cover_letter_text ?? "",
    tailored_resume_text: patch.tailored_resume_text ?? existing?.tailored_resume_text ?? "",
    saved_at: patch.saved_at ?? existing?.saved_at ?? null,
  };
  writeOfferDraft(merged);
  return merged;
}
