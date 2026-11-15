/** Sync "New offer" draft with PostgreSQL (application_jobs). */

import { mergeOfferDraft, readOfferDraft } from "./offerDraft";
import {
  createOfferDraftPutGate,
  offerDraftPersistFingerprint,
} from "./offerDraftPersistDedupe";
import { authFetch, getToken } from "./jobseekerProfile";

export { offerDraftPersistFingerprint } from "./offerDraftPersistDedupe";

const putGate = createOfferDraftPutGate();

export function serverDraftToLocalPatch(draft) {
  if (!draft || typeof draft !== "object" || !draft.job_id) return null;
  if (!draft.jd_text) return null;
  return {
    job_id: draft.job_id,
    jd_text: draft.jd_text,
    analysis: draft.analysis && typeof draft.analysis === "object" ? draft.analysis : null,
    resume_paste: typeof draft.resume_paste === "string" ? draft.resume_paste : "",
    cover_letter_text: typeof draft.cover_letter_text === "string" ? draft.cover_letter_text : "",
    tailored_resume_text: typeof draft.tailored_resume_text === "string" ? draft.tailored_resume_text : "",
    model: typeof draft.model === "string" ? draft.model : "",
    saved_at: draft.saved_at || null,
  };
}

export async function fetchLatestOfferDraftFromServer() {
  if (!getToken()) return null;
  try {
    const r = await authFetch("/jobs/offer-draft/latest");
    const data = await r.json();
    if (!r.ok) return null;
    return data.draft ?? null;
  } catch {
    return null;
  }
}

/** POST /jobs/jd-draft — JD + analysis (required after Calculate score). */
export async function persistJdDraftOnServer(jdText, analysis) {
  if (!getToken()) return { ok: false, reason: "not_logged_in" };
  if (!jdText?.trim()) return { ok: false, reason: "empty_jd" };
  try {
    const fd = new FormData();
    fd.append("job_description", jdText.trim());
    if (analysis && typeof analysis === "object") {
      fd.append("analysis_json", JSON.stringify(analysis));
    }
    const r = await authFetch("/jobs/jd-draft", { method: "POST", body: fd });
    const data = await r.json();
    if (!r.ok) {
      console.warn("[jd-draft] failed:", data.detail || data);
      return { ok: false, reason: "api_error", detail: data.detail || data };
    }
    return { ok: true, ...data };
  } catch (e) {
    console.warn("[jd-draft] error:", e);
    return { ok: false, reason: "network", detail: String(e) };
  }
}

/** PUT /jobs/{id}/offer-draft — analysis, cover letter, resume. Dedupes identical payloads. */
export async function saveOfferDraftToServer(jobId, patch) {
  if (!getToken() || !jobId) return null;
  const fp = offerDraftPersistFingerprint(jobId, patch);
  const decision = putGate.decide(fp);
  if (decision === "skip") {
    return { job_id: jobId, skipped: true };
  }
  if (decision === "join") {
    return putGate.getInflight();
  }

  const run = (async () => {
    try {
      const r = await authFetch(`/jobs/${jobId}/offer-draft`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(patch),
      });
      const data = await r.json();
      if (!r.ok) {
        console.warn("[offer-draft] save failed:", data.detail || data);
        return null;
      }
      putGate.markSaved(fp);
      return data.draft ?? null;
    } catch (e) {
      console.warn("[offer-draft] save error:", e);
      return null;
    }
  })();

  return putGate.begin(fp, run);
}

/** Reset dedupe cache (tests / logout). */
export function resetOfferDraftPersistDedupe() {
  putGate.reset();
}

/** Local sessionStorage + server (when job_id exists). */
export async function persistOfferDraft(patch) {
  const merged = mergeOfferDraft(patch);
  if (!merged) return null;
  let jobId = patch.job_id || merged.job_id || readOfferDraft()?.job_id;

  if (!jobId && getToken() && merged.jd_text && merged.analysis) {
    const jdRes = await persistJdDraftOnServer(merged.jd_text, merged.analysis);
    jobId = jdRes?.ok ? jdRes.job_id || "" : "";
    if (jobId) mergeOfferDraft({ ...merged, job_id: jobId });
  }

  if (!jobId || !getToken()) return merged;

  const current = readOfferDraft() || merged;
  const body = {
    jd_text: current.jd_text,
    analysis: current.analysis,
    cover_letter_text: current.cover_letter_text,
    tailored_resume_text: current.tailored_resume_text,
    resume_paste: current.resume_paste,
    model: current.model,
  };
  const serverDraft = await saveOfferDraftToServer(jobId, body);
  if (serverDraft?.skipped) {
    return { ...current, job_id: jobId };
  }
  if (serverDraft?.job_id) {
    mergeOfferDraft({
      job_id: serverDraft.job_id,
      saved_at: serverDraft.saved_at,
      jd_text: serverDraft.jd_text || current.jd_text,
      analysis: serverDraft.analysis || current.analysis,
      cover_letter_text: serverDraft.cover_letter_text ?? current.cover_letter_text,
      tailored_resume_text: serverDraft.tailored_resume_text ?? current.tailored_resume_text,
      resume_paste: serverDraft.resume_paste ?? current.resume_paste,
      model: serverDraft.model || current.model,
    });
    return readOfferDraft();
  }
  return merged;
}

/** GET /jobs/applications — list for My companies. */
export async function fetchApplications({ includeClosed = false } = {}) {
  if (!getToken()) return { items: [], total: 0, error: "not_logged_in" };
  try {
    const q = includeClosed ? "?include_closed=true" : "";
    const r = await authFetch(`/jobs/applications${q}`);
    const data = await r.json();
    if (!r.ok) {
      return { items: [], total: 0, error: data.detail || "api_error" };
    }
    return {
      items: Array.isArray(data.items) ? data.items : [],
      total: typeof data.total === "number" ? data.total : 0,
      error: null,
    };
  } catch (e) {
    return { items: [], total: 0, error: String(e) };
  }
}

/** PATCH /jobs/{id}/tracker */
export async function patchApplicationTracker(jobId, patch) {
  if (!getToken() || !jobId) return { ok: false, error: "not_logged_in" };
  try {
    const r = await authFetch(`/jobs/${jobId}/tracker`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch),
    });
    const data = await r.json();
    if (!r.ok) {
      return { ok: false, error: data.detail || "api_error" };
    }
    return { ok: true, item: data.item };
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

/** Load a specific offer draft into sessionStorage and return it (for /saved → /new). */
export async function loadOfferDraftByJobId(jobId) {
  if (!getToken() || !jobId) return null;
  try {
    const r = await authFetch(`/jobs/${jobId}/offer-draft`);
    const data = await r.json();
    if (!r.ok || !data) return null;
    const draft = data.jd_text != null ? data : data.draft;
    const patch = serverDraftToLocalPatch(draft);
    if (!patch) return null;
    const analysis =
      patch.analysis ||
      (draft.tracker
        ? {
            company_name: draft.tracker.company_name || "",
            job_title: draft.tracker.job_title || "",
          }
        : null);
    if (!analysis) return null;
    mergeOfferDraft({ ...patch, analysis });
    return readOfferDraft();
  } catch {
    return null;
  }
}

/** Server + local cache; if DB has only JD — backfill analysis from sessionStorage. */
export async function hydrateOfferDraftFromServer() {
  const local = readOfferDraft();
  const server = await fetchLatestOfferDraftFromServer();
  const serverPatch = serverDraftToLocalPatch(server);

  if (!serverPatch && local) return local;
  if (!serverPatch) return null;

  let analysis = serverPatch.analysis || local?.analysis || null;
  const tracker = server?.tracker;
  if (analysis && tracker && typeof tracker === "object") {
    analysis = {
      ...analysis,
      company_name:
        analysis.company_name || tracker.company_name || analysis.company || "",
      job_title:
        analysis.job_title ||
        tracker.job_title ||
        analysis.target_job_title ||
        "",
    };
  } else if (!analysis && tracker && typeof tracker === "object") {
    analysis = {
      company_name: tracker.company_name || "",
      job_title: tracker.job_title || "",
    };
  }
  if (!analysis) {
    mergeOfferDraft({
      job_id: serverPatch.job_id,
      jd_text: serverPatch.jd_text,
      analysis: local?.analysis,
      resume_paste: serverPatch.resume_paste || local?.resume_paste || "",
      cover_letter_text: serverPatch.cover_letter_text || local?.cover_letter_text || "",
      tailored_resume_text: serverPatch.tailored_resume_text || local?.tailored_resume_text || "",
      model: serverPatch.model || local?.model || "",
    });
    const merged = readOfferDraft();
    if (merged?.analysis && merged.job_id) {
      await saveOfferDraftToServer(merged.job_id, {
        jd_text: merged.jd_text,
        analysis: merged.analysis,
        cover_letter_text: merged.cover_letter_text,
        tailored_resume_text: merged.tailored_resume_text,
        resume_paste: merged.resume_paste,
        model: merged.model,
      });
    }
    return readOfferDraft();
  }

  mergeOfferDraft({
    ...serverPatch,
    analysis,
    cover_letter_text: serverPatch.cover_letter_text || local?.cover_letter_text || "",
    tailored_resume_text: serverPatch.tailored_resume_text || local?.tailored_resume_text || "",
    resume_paste: serverPatch.resume_paste || local?.resume_paste || "",
    model: serverPatch.model || local?.model || "",
  });
  return readOfferDraft();
}
