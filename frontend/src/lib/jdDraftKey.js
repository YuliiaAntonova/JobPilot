/** Key for current JD to rebuild template (no crypto). */
export function jdDraftKey(jdText) {
  const s = (jdText || "").trim();
  return `${s.length}:${s.slice(0, 200)}`;
}
