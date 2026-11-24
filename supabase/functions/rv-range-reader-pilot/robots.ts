// RFC 9309 robots.txt matching (ported from supabase/functions/_shared/crawl.ts).
// Groups: consecutive user-agent lines share rules. Groups naming one of our tokens win; otherwise "*".
// Rules: '*' wildcard, trailing '$' anchor, longest match wins, allow wins ties.
export type Rule = { allow: boolean; pattern: string; re: RegExp };
const esc = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const norm = (s: string) => s.replace(/[^\x00-\x7F]/g, (c) => encodeURIComponent(c)).replace(/%[0-9a-f]{2}/gi, (m) => m.toUpperCase());
function compile(allow: boolean, raw: string): Rule {
  let p = norm(raw.trim());
  if (!p.startsWith("/") && !p.startsWith("*")) p = "/" + p;
  const anchored = p.endsWith("$");
  const body = anchored ? p.slice(0, -1) : p;
  return { allow, pattern: p, re: new RegExp("^" + body.split("*").map(esc).join(".*") + (anchored ? "$" : "")) };
}
export function rulesFor(text: string, tokens: string[]): Rule[] {
  type G = { agents: string[]; rules: Rule[] };
  const groups: G[] = []; let cur: G | null = null; let lastAgent = false;
  for (const raw of text.split(/\r\n|\r|\n/)) {
    const line = raw.replace(/#.*/, "").trim();
    const m = line.match(/^([A-Za-z-]+)\s*:\s*(.*)$/); if (!m) continue;
    const key = m[1].toLowerCase(), val = m[2].trim();
    if (key === "user-agent") {
      if (!cur || !lastAgent) { cur = { agents: [], rules: [] }; groups.push(cur); }
      cur.agents.push(val.split("/")[0].trim().toLowerCase()); lastAgent = true; continue;
    }
    lastAgent = false;
    if (!cur) continue;
    if ((key === "allow" || key === "disallow") && val) cur.rules.push(compile(key === "allow", val));
  }
  const ours = groups.filter((g) => g.agents.some((a) => tokens.includes(a)));
  const chosen = ours.length ? ours : groups.filter((g) => g.agents.includes("*"));
  return chosen.flatMap((g) => g.rules);
}
export function allows(rules: Rule[], pathAndQuery: string): boolean {
  const path = norm(pathAndQuery || "/");
  if (path === "/robots.txt") return true;
  let best: Rule | undefined;
  for (const r of rules) {
    if (!r.re.test(path)) continue;
    if (!best || r.pattern.length > best.pattern.length || (r.pattern.length === best.pattern.length && r.allow && !best.allow)) best = r;
  }
  return !best || best.allow;
}
