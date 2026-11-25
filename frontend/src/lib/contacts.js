// One person per line, any column order: the email is found by its shape, a phone is
// the field with mostly digits, and the rest is the name. A header row has no email,
// so it's skipped. Quoted CSV fields ("Doe, Jane") are handled.
export const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
export function splitCsvLine(line) {
  const out = []; let cur = ""; let q = false;
  for (const ch of line) {
    if (ch === '"') { q = !q; continue; }
    if ((ch === "," || ch === ";" || ch === "\t") && !q) { out.push(cur.trim()); cur = ""; continue; }
    cur += ch;
  }
  out.push(cur.trim());
  return out;
}
export function parseContacts(text, source) {
  const seen = new Set();
  return text.split(/\r?\n/).map(l => l.trim()).filter(Boolean).map(l => {
    const cells = splitCsvLine(l).filter(Boolean);
    const email = cells.find(c => EMAIL_RE.test(c));
    if (!email) return null;
    const phone = cells.find(c => c !== email && /^\+?[\d\s()-]{7,}$/.test(c));
    const name = cells.filter(c => c !== email && c !== phone).join(" ").trim();
    return { name: name || email, email: email.toLowerCase(), phone: phone || null, source };
  }).filter(it => it && !seen.has(it.email) && seen.add(it.email));
}

