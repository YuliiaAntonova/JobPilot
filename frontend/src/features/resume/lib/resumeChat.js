/** cv.yml-aligned resume editor helpers (sync with backend cv_schema.py). */

import { authFetch, cacheProfilePayload } from "../../../shared/api/jobseekerProfile";
import { compactJobAnswers } from "./resumeChatSections";

export const RESUME_CHAT_GREETING =
  "Hello! We'll build your Harvard-format CV (cv.yml). Start with your name, headline, and experience — same sections as the workshop template.";

export const RESUME_CHAT_DONE =
  "Done! Your cv.yml profile is saved. Download PDF or YAML from your profile.";

function cacheProfileFromApiRow(row) {
  if (!row) return null;
  const payload = {
    structured: row.structured,
    profile_text: row.profile_text || "",
    desired_role: row.desired_role || "",
    chat_answers: row.chat_answers || {},
    source: row.source || "chat",
  };
  cacheProfilePayload(payload);
  return payload;
}

export function sanitizeChatAnswers(answers) {
  return Object.fromEntries(
    Object.entries(compactJobAnswers(answers || {}))
      .map(([k, v]) => [k, String(v || "").trim()])
      .filter(([, v]) => v),
  );
}

export async function saveProfileFromChatAnswers(answers) {
  const cleaned = sanitizeChatAnswers(answers);
  const r = await authFetch("/profile/from-chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ answers: cleaned }),
  });
  const data = await r.json();
  if (!r.ok) {
    throw new Error(typeof data.detail === "string" ? data.detail : JSON.stringify(data));
  }
  return { profile: cacheProfileFromApiRow(data.profile), cvPreview: data.cv_preview || null };
}

/** Write cv/cv.yml + cv/cv.html on disk from current draft answers (no DB save). */
export async function previewCvFilesFromAnswers(answers) {
  const cleaned = sanitizeChatAnswers(answers);
  if (!Object.keys(cleaned).length) return null;
  const r = await authFetch("/profile/preview-cv-files", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ answers: cleaned }),
  });
  const data = await r.json();
  if (!r.ok) {
    throw new Error(typeof data.detail === "string" ? data.detail : JSON.stringify(data));
  }
  return data;
}

function basicsFromStructured(s) {
  if (s?.basics && typeof s.basics === "object") return s.basics;
  const p = s?.personal || {};
  return {
    name: [p.first_name, p.last_name].filter(Boolean).join(" ").trim() || p.full_name || "",
    headline: s.objective || (s.desired_roles && s.desired_roles[0]) || "",
    location: p.location || p.city || "",
    email: p.email || "",
    phone: p.phone || "",
    summary: s.summary || "",
    links: [],
  };
}

function linksTextFromBasics(basics) {
  const links = basics.links;
  if (Array.isArray(links) && links.length) {
    return links
      .map((ln) => `${ln.label || "Link"} | ${ln.url || ln.text || ""}`)
      .filter(Boolean)
      .join("\n");
  }
  return "";
}

/** Restore flat cv.yml answers from saved profile. */
export function chatAnswersFromProfilePayload(payload) {
  if (!payload || typeof payload !== "object") return null;

  if (payload.chat_answers && typeof payload.chat_answers === "object") {
    const a = payload.chat_answers;
    if (a.name || a.headline || a.exp_0_company) {
      return compactJobAnswers(a);
    }
  }

  const s = payload.structured;
  if (!s || typeof s !== "object") return null;

  if (s.basics || s.chat_format === "cv_yml") {
    const answers = {};
    const b = basicsFromStructured(s);
    answers.name = b.name || "";
    answers.headline = b.headline || payload.desired_role || "";
    answers.location = b.location || "";
    answers.email = b.email || "";
    answers.phone = b.phone || "";
    answers.summary = b.summary || "";
    answers.note = b.note || "";
    answers.links = linksTextFromBasics(b);

    (s.skills || []).forEach((group, idx) => {
      if (!group || typeof group !== "object") return;
      answers[`skill_${idx}_group`] = group.group || "";
      answers[`skill_${idx}_items`] = (group.items || []).join(", ");
    });

    (s.experience || []).forEach((job, idx) => {
      if (!job || typeof job !== "object") return;
      answers[`exp_${idx}_company`] = job.company || "";
      answers[`exp_${idx}_title`] = job.title || "";
      answers[`exp_${idx}_location`] = job.location || "";
      answers[`exp_${idx}_period`] = job.period || job.dates || "";
      answers[`exp_${idx}_context`] = job.context || job.project_context || "";
      answers[`exp_${idx}_bullets`] = (job.bullets || job.highlights || []).join("\n");
    });

    (s.experience_earlier || []).forEach((row, idx) => {
      if (!row || typeof row !== "object") return;
      answers[`earlier_${idx}_period`] = row.period || "";
      answers[`earlier_${idx}_company`] = row.company || "";
      answers[`earlier_${idx}_role`] = row.role || "";
      answers[`earlier_${idx}_location`] = row.location || "";
      answers[`earlier_${idx}_stack`] = (row.stack || []).join(", ");
    });

    (s.projects || []).forEach((proj, idx) => {
      if (!proj || typeof proj !== "object") return;
      answers[`proj_${idx}_name`] = proj.name || "";
      answers[`proj_${idx}_url`] = proj.url || "";
      answers[`proj_${idx}_bullets`] = (proj.bullets || []).join("\n");
    });

    (s.education || []).forEach((edu, idx) => {
      if (!edu || typeof edu !== "object") return;
      answers[`edu_${idx}_degree`] = edu.degree || "";
      answers[`edu_${idx}_school`] = edu.school || edu.institution || "";
      answers[`edu_${idx}_period`] = edu.period || "";
      answers[`edu_${idx}_note`] = edu.note || "";
    });

    if (Array.isArray(s.certifications) && s.certifications.length) {
      answers.certifications = s.certifications
        .map((c) => (typeof c === "string" ? c : c.name || ""))
        .filter(Boolean)
        .join("\n");
    }
    if (Array.isArray(s.languages) && s.languages.length) {
      answers.languages = s.languages
        .map((lang) =>
          typeof lang === "string" ? lang : `${lang.name || ""}${lang.level ? ` — ${lang.level}` : ""}`.trim(),
        )
        .filter(Boolean)
        .join("\n");
    }
    const rec = s.recognition;
    if (rec && typeof rec === "object") {
      const books = rec.books;
      if (Array.isArray(books) && books.length) {
        answers.recognition_books = books
          .map((bk) => {
            if (!bk || typeof bk !== "object") return "";
            const parts = [bk.title, bk.publisher, bk.year, bk.url].filter(Boolean);
            return parts.join(" | ");
          })
          .filter(Boolean)
          .join("\n");
      }
      const highlights = rec.highlights;
      if (Array.isArray(highlights) && highlights.length) {
        answers.recognition_highlights = highlights.join("\n");
      }
    }

    const interestsRaw = s.interests;
    if (typeof interestsRaw === "string" && interestsRaw.trim()) {
      answers.interests = interestsRaw.trim();
    } else if (Array.isArray(interestsRaw) && interestsRaw.length) {
      answers.interests = interestsRaw.map((x) => String(x || "").trim()).filter(Boolean).join("\n");
    } else {
      const legacyNote = String(b.note || "").trim();
      if (/^interests\b/i.test(legacyNote)) {
        answers.interests = legacyNote.replace(/^interests\s*[:\-–—]?\s*/i, "").trim();
      }
    }

    return compactJobAnswers(answers);
  }

  return null;
}
