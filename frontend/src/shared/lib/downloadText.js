/** Download text as .txt in the browser. */

const WEAK_COMPANY = /^(is[\s_]+seeking|confidential|we|our|they|this|that|you|your)$/i;

/** Slug for export filenames; skips weak parsed company names like "is seeking" / "We". */
export function exportFileBase(analysis, companyOverride = "") {
  const company = String(companyOverride || analysis?.company_name || "").trim();
  const title = String(analysis?.job_title || "").trim();
  const weakCompany = !company || WEAK_COMPANY.test(company.replace(/\s+/g, " "));
  if (weakCompany && title) return slugForFilename(title);
  return slugForFilename(company || title || "vacancy");
}

export function slugForFilename(text, maxLen = 36) {
  const s = String(text || "export")
    .trim()
    .replace(/[^\w\u0400-\u04FF\-]+/gu, "_")
    .replace(/_+/g, "_")
    .slice(0, maxLen)
    .replace(/^_|_$/g, "");
  return s || "export";
}

export function downloadTextFile(filename, content) {
  const name = filename.endsWith(".txt") ? filename : `${filename}.txt`;
  const blob = new Blob([content], { type: "text/plain;charset=utf-8" });
  downloadBlob(name, blob);
}

export function downloadBlob(filename, blob) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

/** Download PDF from FastAPI Response (Content-Disposition filename). */
export async function downloadPdfFromResponse(response, fallbackName = "document.pdf") {
  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const data = await response.json();
      if (typeof data.detail === "string") detail = data.detail;
    } catch {
      /* binary or empty */
    }
    throw new Error(detail);
  }
  const blob = await response.blob();
  const disposition = response.headers.get("Content-Disposition") || "";
  const match = disposition.match(/filename="([^"]+)"/i);
  const filename = match?.[1] || fallbackName;
  downloadBlob(filename, blob);
}
