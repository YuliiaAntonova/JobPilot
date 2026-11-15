/** Helpers to edit cv.yml-shaped JSON for job-specific draft (not cabinet profile). */

export function skillsToCommaText(structured) {
  const groups = structured?.skills;
  if (!Array.isArray(groups) || !groups.length) return "";
  const items = [];
  for (const g of groups) {
    if (!g || typeof g !== "object") continue;
    for (const it of g.items || []) {
      const t = String(it || "").trim();
      if (t) items.push(t);
    }
  }
  return items.join(", ");
}

export function applySkillsFromCommaText(structured, commaText) {
  const next = { ...structured };
  const items = String(commaText || "")
    .split(/[,;\n]/)
    .map((s) => s.trim())
    .filter(Boolean);
  const prevGroups = Array.isArray(next.skills) ? next.skills : [];
  const groupLabel =
    prevGroups[0]?.group && String(prevGroups[0].group).toLowerCase() !== "skills"
      ? prevGroups[0].group
      : "Technical";
  next.skills = [{ group: groupLabel, items }];
  return next;
}

export function experienceDraftRows(structured) {
  const rows = Array.isArray(structured?.experience) ? structured.experience : [];
  return rows.map((row, idx) => ({
    idx,
    company: String(row?.company || "").trim(),
    title: String(row?.title || "").trim(),
    period: String(row?.period || "").trim(),
    bulletsText: (row?.bullets || []).map((b) => String(b || "").trim()).filter(Boolean).join("\n"),
  }));
}

export function applyExperienceDraftRows(structured, draftRows) {
  const next = { ...structured };
  next.experience = (draftRows || []).map((row) => ({
    company: String(row.company || "").trim(),
    title: String(row.title || "").trim(),
    location: "",
    period: String(row.period || "").trim(),
    bullets: String(row.bulletsText || "")
      .split("\n")
      .map((ln) => ln.replace(/^[-*•]\s*/, "").trim())
      .filter(Boolean),
  }));
  return next;
}

export function mergeDraftFormIntoStructured(structured, { headline, summary, skillsText, experienceRows }) {
  let next = { ...structured, basics: { ...(structured?.basics || {}) } };
  next.basics.headline = String(headline || "").trim();
  next.basics.summary = String(summary || "").trim();
  next = applySkillsFromCommaText(next, skillsText);
  next = applyExperienceDraftRows(next, experienceRows);
  return next;
}
