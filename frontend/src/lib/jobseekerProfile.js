/** Jobseeker cabinet: JWT on server + profile cache in localStorage. */

export const JOBSEEKER_TOKEN_KEY = "jobseeker_token_v1";
export const JOBSEEKER_SESSION_KEY = "jobseeker_session_v1";
export const JOBSEEKER_PROFILE_KEY = "jobseeker_profile_v1";

export function getToken() {
  try {
    return localStorage.getItem(JOBSEEKER_TOKEN_KEY) || "";
  } catch {
    return "";
  }
}

function setToken(token) {
  localStorage.setItem(JOBSEEKER_TOKEN_KEY, token);
}

export function getSession() {
  try {
    const raw = localStorage.getItem(JOBSEEKER_SESSION_KEY);
    if (!raw) return null;
    const s = JSON.parse(raw);
    return s && s.email && getToken() ? s : null;
  } catch {
    return null;
  }
}

/** @param {{ id?: string, email: string }} user */
export function setSession(user) {
  localStorage.setItem(
    JOBSEEKER_SESSION_KEY,
    JSON.stringify({ email: user.email.trim(), userId: user.id || null, loggedIn: true }),
  );
  window.dispatchEvent(new Event("jobseeker-session-changed"));
}

export function clearSession() {
  localStorage.removeItem(JOBSEEKER_TOKEN_KEY);
  localStorage.removeItem(JOBSEEKER_SESSION_KEY);
  window.dispatchEvent(new Event("jobseeker-session-changed"));
}

export function authHeaders(extra = {}) {
  const token = getToken();
  if (!token) return { ...extra };
  return { Authorization: `Bearer ${token}`, ...extra };
}

export async function authFetch(url, options = {}) {
  const headers = { ...authHeaders(), ...(options.headers || {}) };
  return fetch(url, { ...options, headers });
}

/** URL for PDF/files in iframe (Bearer via query access_token). */
export function jobAssetUrl(path) {
  const token = getToken();
  if (!token) return path;
  const sep = path.includes("?") ? "&" : "?";
  return `${path}${sep}access_token=${encodeURIComponent(token)}`;
}

export async function authFetchWithTimeout(url, opts = {}) {
  const { timeoutMs = 90_000, headers, ...rest } = opts;
  const c = new AbortController();
  const t = window.setTimeout(() => c.abort(new DOMException("timeout", "AbortError")), timeoutMs);
  try {
    return await fetch(url, {
      ...rest,
      headers: { ...authHeaders(), ...(headers || {}) },
      signal: c.signal,
    });
  } finally {
    window.clearTimeout(t);
  }
}

/** Parse FastAPI JSON or plain-text/proxy errors (avoids cryptic JSON.parse failures). */
export async function parseApiResponse(r) {
  const text = await r.text();
  if (!text) {
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return {};
  }
  try {
    return JSON.parse(text);
  } catch {
    const snippet = text.trim().slice(0, 200);
    if (!r.ok) {
      throw new Error(
        snippet
          ? `HTTP ${r.status}: ${snippet}`
          : `HTTP ${r.status}. Make sure the backend is running (uvicorn on :8000).`,
      );
    }
    throw new Error(`Server returned non-JSON: ${snippet}`);
  }
}

/** @returns {{ structured: object, profile_text: string, desired_role?: string, chat_answers?: object, source?: string, updatedAt?: number } | null} */
export function getProfilePayload() {
  try {
    const raw = localStorage.getItem(JOBSEEKER_PROFILE_KEY);
    if (!raw) return null;
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

/** @param {object} payload */
export function cacheProfilePayload(payload) {
  const next = { ...payload, updatedAt: Date.now() };
  localStorage.setItem(JOBSEEKER_PROFILE_KEY, JSON.stringify(next));
  window.dispatchEvent(new Event("jobseeker-profile-updated"));
}

/** @deprecated use cacheProfilePayload — local cache only */
export function saveProfilePayload(payload) {
  cacheProfilePayload(payload);
}

export function clearProfilePayload() {
  localStorage.removeItem(JOBSEEKER_PROFILE_KEY);
  window.dispatchEvent(new Event("jobseeker-profile-updated"));
}

export function getProfileText() {
  const p = getProfilePayload();
  if (!p) return "";
  const base =
    typeof p.profile_text === "string"
      ? p.profile_text.trim()
      : typeof p.profile_text_base === "string"
        ? p.profile_text_base.trim()
        : "";
  const dr = typeof p.desired_role === "string" ? p.desired_role.trim() : "";
  const hasDesiredInBase = /\bdesired role\s*:/i.test(base);
  if (dr && base && !hasDesiredInBase) return `${base}\n\nDesired role: ${dr}`;
  if (dr) return `Desired role: ${dr}`;
  return base;
}

/** Profile exists on server / in cache (structured or plain text). */
export function profileHasResume(structuredOverride = null) {
  const payload = getProfilePayload();
  const structured =
    structuredOverride ??
    payload?.structured ??
    null;
  if (structured && typeof structured === "object") {
    const keys = Object.keys(structured).filter((k) => !k.startsWith("_"));
    if (keys.length > 0) return true;
  }
  const text = getProfileText();
  return Boolean(text && text.trim().length >= 20);
}

async function downloadResumeBlob(format, r) {
  if (!r.ok) {
    let detail = `HTTP ${r.status}`;
    try {
      const data = await r.json();
      if (typeof data.detail === "string") detail = data.detail;
    } catch {
      /* binary or empty */
    }
    throw new Error(detail);
  }
  const blob = await r.blob();
  const disposition = r.headers.get("Content-Disposition") || "";
  const match = disposition.match(/filename="([^"]+)"/i);
  const fallback = "resume.pdf";
  const filename = match?.[1] || fallback;
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

/** @param {"pdf"} format @param {{ structured?: object, profile_text?: string, chat_answers?: object }} [overrides] */
export async function downloadProfileResume(format = "pdf", overrides = {}) {
  const overrideChat =
    overrides.chat_answers &&
    typeof overrides.chat_answers === "object" &&
    Object.keys(overrides.chat_answers).length;
  const overrideStructured =
    overrides.structured &&
    typeof overrides.structured === "object" &&
    Object.keys(overrides.structured).length;

  // Cabinet download: always render from PostgreSQL (localStorage chat_answers are stale after ATS save).
  if (!overrideChat && !overrideStructured) {
    await fetchProfileFromServer();
    const path = "/profile/me/resume.pdf";
    const r = await authFetch(path, { method: "GET" });
    await downloadResumeBlob(format, r);
    return;
  }

  const payload = getProfilePayload();
  const chatAnswers = overrideChat
    ? overrides.chat_answers
    : payload?.chat_answers && typeof payload.chat_answers === "object" && Object.keys(payload.chat_answers).length
      ? payload.chat_answers
      : null;
  const structured = overrideStructured ? overrides.structured : payload?.structured;
  if (!structured && !chatAnswers) {
    throw new Error("No structured JSON. Complete the chat or upload a PDF first.");
  }

  const path = "/profile/render-resume.pdf";
  const body = {
    profile_text: overrides.profile_text || payload?.profile_text || getProfileText(),
  };
  if (structured && Object.keys(structured).length) {
    body.structured = structured;
    if (chatAnswers) body.chat_answers = chatAnswers;
  } else if (chatAnswers) {
    body.chat_answers = chatAnswers;
  }

  const r = await authFetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  await downloadResumeBlob(format, r);
}

export function dispatchProfileUpdated() {
  window.dispatchEvent(new Event("jobseeker-profile-updated"));
}

function profileFromApiRow(row) {
  if (!row) return null;
  return {
    structured: row.structured,
    profile_text: row.profile_text || "",
    desired_role: row.desired_role || "",
    source: row.source,
    chat_answers: row.chat_answers,
    updatedAt: row.updated_at ? Date.parse(row.updated_at) || Date.now() : Date.now(),
  };
}

export async function fetchProfileFromServer() {
  if (!getToken()) return getProfilePayload();
  const r = await authFetch("/profile/me");
  if (!r.ok) return getProfilePayload();
  const data = await r.json();
  const payload = profileFromApiRow(data.profile);
  if (payload) cacheProfilePayload(payload);
  return payload;
}

export async function syncProfileAfterAuth() {
  return getProfilePayload();
}

/** @param {string} email @param {string} password */
export async function loginUser(email, password) {
  const r = await fetch("/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email: email.trim(), password }),
  });
  const data = await r.json();
  if (!r.ok) {
    throw new Error(typeof data.detail === "string" ? data.detail : JSON.stringify(data));
  }
  setToken(data.access_token);
  setSession(data.user);
  await syncProfileAfterAuth();
  return data.user;
}

/** @param {string} email @param {string} password */
export async function registerUser(email, password) {
  const r = await fetch("/auth/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email: email.trim(), password }),
  });
  const data = await r.json();
  if (!r.ok) {
    throw new Error(typeof data.detail === "string" ? data.detail : JSON.stringify(data));
  }
  setToken(data.access_token);
  setSession(data.user);
  await syncProfileAfterAuth();
  return data.user;
}

export async function logoutUser() {
  clearSession();
  clearProfilePayload();
}

export async function deleteProfileOnServer() {
  clearProfilePayload();
  return { ok: true };
}

export async function updateDesiredRoleOnServer(desiredRole) {
  const payload = getProfilePayload() || {};
  cacheProfilePayload({ ...payload, desired_role: desiredRole.trim() });
  return getProfilePayload();
}

/** @param {string} profileText Plain resume text (after AI tailoring). */
export async function updateProfileTextOnServer(
  profileText,
  { reparseStructured = true, model, atsSubstitutions } = {},
) {
  const text = profileText.trim();
  if (!getToken()) {
    throw new Error("Sign in to your cabinet to save the resume.");
  }
  const body = {
    profile_text: text,
    reparse_structured: reparseStructured,
    ...(model ? { model } : {}),
  };
  if (Array.isArray(atsSubstitutions) && atsSubstitutions.length) {
    body.ats_substitutions = atsSubstitutions;
  }
  const r = await authFetchWithTimeout("/profile/me", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    timeoutMs: 120_000,
  });
  const data = await r.json();
  if (!r.ok) {
    throw new Error(typeof data.detail === "string" ? data.detail : JSON.stringify(data));
  }
  const payload = profileFromApiRow(data.profile);
  if (payload) cacheProfilePayload(payload);
  return payload;
}

/** Save Harvard structured cv (e.g. cv_tailored) to PostgreSQL. */
export async function saveStructuredProfileToServer(structured, { profileText, source = "tailored" } = {}) {
  if (!getToken()) {
    throw new Error("Sign in to your cabinet to save the resume.");
  }
  if (!structured || typeof structured !== "object" || !Object.keys(structured).length) {
    throw new Error("Structured profile is empty.");
  }
  const r = await authFetchWithTimeout("/profile/from-structured", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      structured,
      profile_text: profileText || undefined,
      source,
    }),
    timeoutMs: 60_000,
  });
  const data = await parseApiResponse(r);
  if (!r.ok) {
    throw new Error(typeof data.detail === "string" ? data.detail : JSON.stringify(data));
  }
  const payload = profileFromApiRow(data.profile);
  if (payload) cacheProfilePayload(payload);
  dispatchProfileUpdated();
  return { profile: payload, cvPreview: data.cv_preview || null };
}

/** URL for iframe preview of workshop cv.html (Bearer via access_token). */
export function profileCvHtmlPreviewUrl(cacheBust = Date.now()) {
  return jobAssetUrl(`/profile/me/cv.html?t=${encodeURIComponent(String(cacheBust))}`);
}

/** JD-specific tailoring preview (does not overwrite cabinet cv.html). */
export function profileJobTailoredDraftHtmlUrl(cacheBust = Date.now()) {
  return jobAssetUrl(`/profile/me/cv-tailored-draft.html?t=${encodeURIComponent(String(cacheBust))}`);
}

export async function uploadResumePdfToServer(file) {
  const fd = new FormData();
  fd.append("resume_pdf", file);
  const r = await authFetchWithTimeout("/profile/from-resume", {
    method: "POST",
    body: fd,
    timeoutMs: 180_000,
  });
  const data = await parseApiResponse(r);
  if (!r.ok) {
    throw new Error(typeof data.detail === "string" ? data.detail : JSON.stringify(data));
  }
  const payload = profileFromApiRow(data.profile);
  if (payload) cacheProfilePayload(payload);
  return payload;
}
