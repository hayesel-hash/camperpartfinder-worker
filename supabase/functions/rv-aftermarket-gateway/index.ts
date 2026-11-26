// Aftermarket cross-reference gateway. Lets the GitHub workflow aftermarket-xref.yml (and only
// that workflow, on main) STAGE chart pages and their parsed rows. It cannot publish anything:
// publication is rv_private.publish_aftermarket_replacements_v1, gated on a reviewed page.
// No secrets live in the public repository: the worker proves who it is with a short-lived
// GitHub OIDC token, and this function holds the key. Pattern copied from rv-catalogue-archive-gateway.
import { createRemoteJWKSet, jwtVerify } from "npm:jose@5.10.0";

const jwks = createRemoteJWKSet(new URL("https://token.actions.githubusercontent.com/.well-known/jwks"));
const base = Deno.env.get("SUPABASE_URL")!;
const key = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const repos: Record<string, string> = { "hayesel-hash/camperpartfinder-worker": "1465247938" };
const aud = "rv-aftermarket-dlijhukwzlqwtmiynncg";
const workflow = ".github/workflows/aftermarket-xref.yml@refs/heads/main";

const actions: Record<string, { fn: string; args: string[] }> = {
  stage: { fn: "rv_aftermarket_stage", args: ["page", "page_rows"] },
};

async function rpc(fn: string, args: Record<string, unknown>) {
  const r = await fetch(`${base}/rest/v1/rpc/${fn}`, {
    method: "POST",
    headers: { apikey: key, Authorization: `Bearer ${key}`, "Content-Type": "application/json" },
    body: JSON.stringify(args),
  });
  if (!r.ok) throw new Error("rpc");
  return await r.json();
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
    if (raw.length > 5_000_000) return new Response("size", { status: 413 });
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
