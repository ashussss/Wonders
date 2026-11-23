// Webinar times are typed as a wall-clock time in the webinar's own timezone
// (3:00 PM Europe/London), not in the timezone of whoever's browser is open.
// <input type="datetime-local"> gives "YYYY-MM-DDTHH:mm" with no zone, and
// new Date() would read it as the browser's local time, which shifts the
// webinar when the host is in another country.

export const TIMEZONES = [
  "Europe/London", "Europe/Dublin", "Europe/Paris", "Europe/Berlin", "Europe/Stockholm",
  "America/New_York", "America/Chicago", "America/Denver", "America/Los_Angeles", "America/Toronto",
  "Asia/Kolkata", "Asia/Dubai", "Asia/Singapore", "Australia/Sydney", "UTC",
];

function partsIn(date, tz) {
  const f = new Intl.DateTimeFormat("en-GB", {
    timeZone: tz || "UTC", hourCycle: "h23",
    year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit",
  });
  const p = {};
  for (const { type, value } of f.formatToParts(date)) p[type] = value;
  return p;
}

// Offset of tz from UTC at that instant, in minutes.
function offsetMinutes(date, tz) {
  const p = partsIn(date, tz);
  const asUtc = Date.UTC(+p.year, +p.month - 1, +p.day, +p.hour % 24, +p.minute, +p.second);
  return Math.round((asUtc - date.getTime()) / 60000);
}

// "2026-12-08T15:00" in "Europe/London" -> "2026-12-08T15:00:00.000Z"
export function wallToUtcISO(wall, tz) {
  const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(wall || "");
  if (!m) return null;
  const guess = Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4], +m[5]);
  let off = offsetMinutes(new Date(guess), tz);
  let utc = guess - off * 60000;
  const off2 = offsetMinutes(new Date(utc), tz); // around a clock change
  if (off2 !== off) utc = guess - off2 * 60000;
  return new Date(utc).toISOString();
}

// An ISO instant -> "YYYY-MM-DDTHH:mm" as the clock reads in tz, for datetime-local inputs.
export function utcToWall(iso, tz) {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d)) return "";
  const p = partsIn(d, tz);
  return `${p.year}-${p.month}-${p.day}T${String(+p.hour % 24).padStart(2, "0")}:${p.minute}`;
}

// A start time from an import: with an explicit zone it is an instant, without one
// it is already the wall-clock time.
export function importedToWall(raw, tz) {
  if (!raw) return "";
  return /(Z|[+-]\d{2}:?\d{2})$/.test(raw.trim()) ? utcToWall(raw, tz) : raw.slice(0, 16);
}

// "Tue 8 Dec 2026, 15:00 GMT"
export function fmtInTz(iso, tz) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("en-GB", {
      timeZone: tz || "UTC", weekday: "short", day: "numeric", month: "short", year: "numeric",
      hour: "2-digit", minute: "2-digit", timeZoneName: "short",
    });
  } catch { return iso; }
}
