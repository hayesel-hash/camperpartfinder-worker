// Supplied reader gateway. Lets the GitHub workflow supplied-reader.yml (and only that workflow,
// on main) claim queued maker documents (Airstream parts books too large for the Drive connector)
// and STAGE their extracted rows. Publication happens inside rv_supplied_stage only when every
// automated gate passed. Auth: short-lived GitHub OIDC token; pattern copied from rv-store-gateway.
import { createRemoteJWKSet, jwtVerify } from "npm:jose@5.10.0";

const jwks = createRemoteJWKSet(new URL("https://token.actions.githubusercontent.com/.well-known/jwks"));
const base = Deno.env.get("SUPABASE_URL")!;
const key = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const repos: Record<string, string> = { "hayesel-hash/camperpartfinder-worker": "1465247938" };
const aud = "rv-supplied-reader-dlijhukwzlqwtmiynncg";
const workflow = ".github/workflows/supplied-reader.yml@refs/heads/main";

const actions: Record<string, { fn: string; args: string[] }> = {
  claim: { fn: "rv_supplied_claim", args: ["n"] },
  stage: { fn: "rv_supplied_stage", args: ["url", "lease", "doc"] },
  fail: { fn: "rv_supplied_fail", args: ["url", "lease", "reason"] },
};

async function rpc(fn: string, args: Record<string, unknown>) {
  const r = await fetch(`${base}/rest/v1/rpc/${fn}`, {
    method: "POST",
    headers: { apikey: key, Authorization: `Bearer ${key}`, "Content-Type": "application/json" },
    body: JSON.stringify(args),
  });
  if (!r.ok) throw new Error("rpc");
  const t = await r.text();
  return t ? JSON.parse(t) : null;
}

Deno.serve(async (req) => {
  if (req.method !== "POST") return new Response("method", { status: 405 });
  try {
    const token = (req.headers.get("Authorization") || "").match(/^Bearer (\S+)$/)?.[1];
    if (!token || token.length > 16000) return new Response("unauthorized", { status: 401 });
    let p;
    try {
      ({ payload: p } = await jwtVerify(token, jwks, {
        issuer: "https://token.actions.githubusercontent.com",
        audience: aud,
        algorithms: ["RS256"],
        requiredClaims: ["exp", "iat", "sub"],
      }));
    } catch {
      return new Response("unauthorized", { status: 401 });
    }
    const repo = String(p.repository);
    if (
      !Object.hasOwn(repos, repo) || String(p.repository_id) !== repos[repo] || p.ref !== "refs/heads/main" ||
      p.workflow_ref !== `${repo}/${workflow}` ||
      !["schedule", "workflow_dispatch", "push"].includes(String(p.event_name))
    ) return new Response("forbidden", { status: 403 });

    const raw = await req.text();
    if (raw.length > 8_000_000) return new Response("size", { status: 413 });
    const body = JSON.parse(raw);
    const action = String(body.action);
    if (action === "auth_probe") return new Response("ok");
    if (!Object.hasOwn(actions, action)) return new Response("action", { status: 400 });
    const args = body.args || {};
    if (Object.keys(args).some((k) => !actions[action].args.includes(k))) {
      return new Response("arguments", { status: 400 });
    }
    return Response.json(await rpc(actions[action].fn, args));
  } catch {
    return Response.json({ error: "gateway operation failed" }, { status: 502 });
  }
});
