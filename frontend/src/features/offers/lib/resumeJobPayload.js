import { getProfilePayload, getProfileText } from "../../../shared/api/jobseekerProfile";

/** Keep in sync with job_application.config RESUME_TEXT_MIN_CHARS (default 80 on server). */
export const JOB_APP_RESUME_TEXT_MIN_CHARS = 80;

/** Text and structure from local cabinet for multipart POST /jobs. */
export function getCabinetResumeForJobPayload() {
  const text = getProfileText().trim();
  const p = getProfilePayload();
  const structured =
    p && p.structured && typeof p.structured === "object" && !Array.isArray(p.structured) ? p.structured : null;
  return { text, structured };
}

export function cabinetResumeReady(minChars = JOB_APP_RESUME_TEXT_MIN_CHARS) {
  return getCabinetResumeForJobPayload().text.length >= minChars;
}
