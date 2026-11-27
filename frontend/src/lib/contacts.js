// One person per line, any column order: the email is found by its shape, a phone is
// the field with mostly digits, and the rest is the name. A header row has no email,
// so it's skipped. Quoted CSV fields ("Doe, Jane") are handled.
export const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
// "<jane@x.com>" (pasted from Outlook) and "mailto:jane@x.com" are still Jane.
export const cleanEmail = (s) => String(s || "").trim().replace(/^<|>$/g, "").replace(/^mailto:/i, "").trim();

// FastAPI sends detail as a string, or (422) a list of {msg, loc}. Toasting the raw list
// threw inside the toast, so the user saw nothing at all when an add failed.
export function apiError(e, fallback) {
  const d = e?.response?.data?.detail;
  if (typeof d === "string" && d) return d;
  if (Array.isArray(d) && d.length) return d.map(x => (x && x.msg) || String(x)).slice(0, 3).join("; ");
  if (!e?.response) return "Can't reach ShowUp right now. Try again in a minute.";
  return fallback;
}
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
// Header names we understand. With a header row, only these columns are used, so a
// "Company" or "City" column never ends up inside someone's name (emails greet people
// by the first word of the name).
const HEAD = {
  email: /^(e-?mail|e-?mail ?address|email ?id|mail)$/,
  first: /^(first|first ?name|firstname|fname|given ?name|forename)$/,
  last: /^(last|last ?name|lastname|lname|surname|family ?name)$/,
  name: /^(name|full ?name|fullname|contact ?name|attendee ?name|registrant ?name|your ?name)$/,
  phone: /^(phone|phone ?number|mobile|mobile ?number|whatsapp|whatsapp ?number|contact ?number|cell|tel|telephone)$/,
};
const normHead = (c) => c.toLowerCase().replace(/[_*:.]/g, " ").replace(/\s+/g, " ").trim();

function headerMap(cells) {
  const m = {};
  cells.forEach((c, i) => {
    const h = normHead(c);
    for (const [k, re] of Object.entries(HEAD)) if (m[k] === undefined && re.test(h)) m[k] = i;
  });
  return m.email !== undefined && (m.first !== undefined || m.name !== undefined || m.last !== undefined || m.phone !== undefined) ? m : null;
}

export function parseContacts(text, source) {
  const seen = new Set();
  const lines = text.split(/\r?\n/).map(l => l.trim()).filter(Boolean);
  const head = lines.length ? headerMap(splitCsvLine(lines[0])) : null;
  return (head ? lines.slice(1) : lines).map(l => {
    const raw = splitCsvLine(l).map(cleanEmail);
    const cells = raw.filter(Boolean);
    let email, phone, name;
    if (head) {
      email = raw[head.email];
      if (!email || !EMAIL_RE.test(email)) email = cells.find(c => EMAIL_RE.test(c));
      const at = (k) => (head[k] === undefined ? "" : (raw[head[k]] || "").trim());
      phone = at("phone") || null;
      name = at("name") || [at("first"), at("last")].filter(Boolean).join(" ");
    } else {
      email = cells.find(c => EMAIL_RE.test(c));
      phone = cells.find(c => c !== email && /^\+?[\d\s()-]{7,}$/.test(c));
      name = cells.filter(c => c !== email && c !== phone).join(" ").trim();
    }
    if (!email) return null;
    return { name: name || email, email: email.toLowerCase(), phone: phone || null, source };
  }).filter(it => it && !seen.has(it.email) && seen.add(it.email));
}
