// Store reader gateway. Lets the GitHub workflow store-reader.yml (and only that workflow, on
// main) read store config, load sitemap URLs into the frontier, claim URLs and STAGE page facts.
// It cannot publish: publication is rv_private.publish_store_identities_v1, gated on a reviewed
// store. Auth: short-lived GitHub OIDC token; pattern copied from rv-catalogue-archive-gateway.
import { createRemoteJWKSet, jwtVerify } from "npm:jose@5.10.0";

const jwks = createRemoteJWKSet(new URL("https://token.actions.githubusercontent.com/.well-known/jwks"));
const base = Deno.env.get("SUPABASE_URL")!;
const key = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const repos: Record<string, string> = { "hayesel-hash/camperpartfinder-worker": "1465247938" };
const aud = "rv-store-reader-dlijhukwzlqwtmiynncg";
const workflow = ".github/workflows/store-reader.yml@refs/heads/main";

const actions: Record<string, { fn: string; args: string[] }> = {
  config: { fn: "rv_store_config", args: [] },
  frontier: { fn: "rv_store_frontier", args: ["store", "urls", "final"] },
  claim: { fn: "rv_store_claim", args: ["store", "n"] },
  stage: { fn: "rv_store_stage", args: ["store", "tok", "rows"] },
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
    if (raw.length > 4_000_000) return new Response("size", { status: 413 });
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
