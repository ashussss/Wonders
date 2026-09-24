// Minimal, safe markdown parser for blog posts -> plain AST (rendered as React elsewhere).
// Supports: ## headings, paragraphs, - / 1. lists (one nesting level), - [ ] checklists,
// ``` code blocks, | tables |, --- rules. Inline: **bold**, `code`.

const LIST_RE = /^(\s*)([-*]|\d+\.)\s+(.*)$/;

function splitRow(line) {
  return line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((c) => c.trim());
}

export function parseMarkdown(md) {
  const lines = (md || "").replace(/\r\n/g, "\n").split("\n");
  const blocks = [];
  let i = 0;
  let para = [];
  const flushPara = () => {
    if (para.length) blocks.push({ type: "p", text: para.join(" ") });
    para = [];
  };

  while (i < lines.length) {
    const line = lines[i];
    const t = line.trim();

    if (t.startsWith("```")) {
      flushPara();
      const code = [];
      i++;
      while (i < lines.length && !lines[i].trim().startsWith("```")) code.push(lines[i++]);
      i++;
      blocks.push({ type: "code", text: code.join("\n") });
      continue;
    }
    if (!t) { flushPara(); i++; continue; }
    if (/^-{3,}$/.test(t)) { flushPara(); i++; continue; }

    const h = t.match(/^(#{1,4})\s+(.+)$/);
    if (h) {
      flushPara();
      blocks.push({ type: "h", level: Math.max(2, Math.min(h[1].length, 4)), text: h[2].replace(/\*\*/g, "") });
      i++;
      continue;
    }

    if (t.startsWith("|")) {
      flushPara();
      const rows = [];
      while (i < lines.length && lines[i].trim().startsWith("|")) rows.push(lines[i++]);
      const cells = rows.filter((r) => !/^\s*\|?\s*:?-{2,}/.test(r)).map(splitRow);
      if (cells.length) blocks.push({ type: "table", head: cells[0], rows: cells.slice(1) });
      continue;
    }

    const m = line.match(LIST_RE);
    if (m && m[1].length < 2) {
      flushPara();
      const ordered = /\d/.test(m[2]);
      const items = [];
      while (i < lines.length) {
        const l = lines[i];
        if (!l.trim()) {
          // allow blank lines inside a list if the list continues
          const next = lines[i + 1];
          const nm = next && next.match(LIST_RE);
          if (nm && nm[1].length < 2 && /\d/.test(nm[2]) === ordered) { i++; continue; }
          if (nm && nm[1].length >= 2 && items.length) { i++; continue; }
          break;
        }
        const lm = l.match(LIST_RE);
        if (lm && lm[1].length < 2) {
          if (/\d/.test(lm[2]) !== ordered) break;
          let text = lm[3];
          const check = text.match(/^\[( |x|X)\]\s+(.*)$/);
          items.push({ text: check ? check[2] : text, check: !!check, children: [] });
          i++;
        } else if (lm && items.length) {
          items[items.length - 1].children.push(lm[3].replace(/^\[( |x|X)\]\s+/, ""));
          i++;
        } else if (/^\s{2,}\S/.test(l) && items.length) {
          const last = items[items.length - 1];
          if (last.children.length) last.children[last.children.length - 1] += " " + l.trim();
          else last.text += " " + l.trim();
          i++;
        } else break;
      }
      blocks.push({ type: ordered ? "ol" : "ul", items, checklist: items.length > 0 && items.every((x) => x.check) });
      continue;
    }

    para.push(t);
    i++;
  }
  flushPara();
  return blocks;
}

export function splitInline(text) {
  // returns [{t:"text"|"b"|"code", v}]
  const out = [];
  const re = /(\*\*[^*]+\*\*|`[^`]+`)/g;
  let last = 0, m;
  while ((m = re.exec(text || ""))) {
    if (m.index > last) out.push({ t: "text", v: text.slice(last, m.index) });
    out.push(m[0].startsWith("**") ? { t: "b", v: m[0].slice(2, -2) } : { t: "code", v: m[0].slice(1, -1) });
    last = m.index + m[0].length;
  }
  if (last < (text || "").length) out.push({ t: "text", v: text.slice(last) });
  return out;
}
