/** Normalize cv.yml and legacy structured JSON for cabinet / view pages. */

function basicsOf(structured) {
  if (structured?.basics && typeof structured.basics === "object") return structured.basics;
  return null;
}

function personalOf(structured) {
  return structured?.personal && typeof structured.personal === "object" ? structured.personal : {};
}

export function displayName(structured) {
  const b = basicsOf(structured);
  if (b?.name) return b.name;
  const p = personalOf(structured);
  const n = [p.first_name, p.last_name].filter(Boolean).join(" ").trim();
  return n || p.full_name || "—";
}

export function profileSummary(structured) {
  const b = basicsOf(structured);
  return String(b?.summary || structured?.summary || structured?.objective || "").trim();
}

export function profileContact(structured) {
  const b = basicsOf(structured);
  const p = personalOf(structured);
  return {
    location: b?.location || p.location || p.city || "",
    phone: b?.phone || p.phone || "",
    email: b?.email || p.email || "",
  };
}

export function languagesLine(structured) {
  const L = structured?.languages;
  if (!Array.isArray(L) || !L.length) return "—";
  return L.map((x) => (typeof x === "string" ? x : x?.language || x?.name || String(x))).join(", ");
}

export function skillsForDisplay(structured) {
  const raw = structured?.skills;
  if (!Array.isArray(raw) || !raw.length) return [];
  if (typeof raw[0] === "object" && raw[0] !== null && ("group" in raw[0] || "items" in raw[0])) {
    const chips = [];
    for (const group of raw) {
      if (!group || typeof group !== "object") continue;
      const label = String(group.group || "").trim();
      const items = Array.isArray(group.items) ? group.items : [];
      if (label && items.length) {
        chips.push(`${label}: ${items.map((x) => String(x).trim()).filter(Boolean).join(", ")}`);
      } else if (label) {
        chips.push(label);
      } else {
        chips.push(...items.map((x) => String(x).trim()).filter(Boolean));
      }
    }
    return chips;
  }
  return raw.map((x) => String(x).trim()).filter(Boolean);
}

/** @returns {Array<{ title: string, company: string, dates: string, context: string, bullets: string[] }>} */
export function experienceForDisplay(structured) {
  const exp = structured?.experience;
  if (!Array.isArray(exp) || !exp.length) return [];
  return exp
    .filter((row) => row && typeof row === "object")
    .map((row) => {
      const title = String(row.title || row.position || row.role || "").trim();
      const company = String(row.company || "").trim();
      const dates = String(row.period || row.dates || row.duration || "").trim();
      const context = String(row.context || row.project_context || "").trim();
      const bulletsRaw = row.bullets || row.highlights || row.responsibilities || [];
      const bullets = Array.isArray(bulletsRaw)
        ? bulletsRaw.map((x) => String(x).trim()).filter(Boolean)
        : String(bulletsRaw || row.summary || row.description || "")
            .split("\n")
            .map((x) => x.trim())
            .filter(Boolean);
      return { title, company, dates, context, bullets };
    })
    .filter((row) => row.title || row.company || row.context || row.bullets.length);
}

/** @returns {Array<{ degree: string, school: string, period: string, note: string }>} */
export function educationForDisplay(structured) {
  const edu = structured?.education;
  if (!Array.isArray(edu) || !edu.length) return [];
  return edu
    .filter((row) => row && typeof row === "object")
    .map((row) => ({
      degree: String(row.degree || "").trim(),
      school: String(row.school || row.institution || "").trim(),
      period: String(row.period || row.graduation_date || row.dates || "").trim(),
      note: String(row.note || row.details || "").trim(),
    }))
    .filter((row) => row.degree || row.school);
}
