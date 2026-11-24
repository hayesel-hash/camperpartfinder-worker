// Catalogue archive gateway. Lets the GitHub archive workflow (and only that workflow, on main)
// store catalogue PDFs and their page text. No secrets live in the public repository: the
// worker proves who it is with a short-lived GitHub OIDC token, and this function holds the key.
import { createRemoteJWKSet, jwtVerify } from "npm:jose@5.10.0";

const jwks = createRemoteJWKSet(new URL("https://token.actions.githubusercontent.com/.well-known/jwks"));
const base = Deno.env.get("SUPABASE_URL")!;
const key = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const BUCKET = "rv-original-catalogues";
const repos: Record<string, string> = { "hayesel-hash/camperpartfinder-worker": "1465247938" };
const aud = "rv-catalogue-archive-dlijhukwzlqwtmiynncg";
const workflow = ".github/workflows/rv-catalogue-archive.yml@refs/heads/main";

const actions: Record<string, { fn: string; args: string[] }> = {
  claim: { fn: "rv_archive_claim", args: ["worker"] },
  begin: { fn: "rv_archive_begin", args: ["cid", "tok", "doc_sha256", "doc_bytes", "doc_pages", "etag", "last_modified"] },
  pages: { fn: "rv_archive_pages", args: ["cid", "tok", "doc_sha256", "page_rows"] },
  finish: { fn: "rv_archive_finish", args: ["cid", "tok", "outcome", "details"] },
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

async function signUpload(path: string) {
  if (!/^[a-z0-9-]{1,80}\/[A-Za-z0-9_-]{1,120}\/[0-9a-f]{64}\.pdf$/.test(path)) throw new Error("path");
  const r = await fetch(`${base}/storage/v1/object/upload/sign/${BUCKET}/${path}`, {
    method: "POST",
    headers: { apikey: key, Authorization: `Bearer ${key}`, "Content-Type": "application/json", "x-upsert": "true" },
    body: "{}",
  });
  if (!r.ok) throw new Error("sign");
  const { url } = await r.json();
  return `${base}/storage/v1${url}`;
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
    if (raw.length > 2_000_000) return new Response("size", { status: 413 });
    const body = JSON.parse(raw);
    const action = String(body.action);
    if (action === "auth_probe") return new Response("ok");
    if (!Object.hasOwn(actions, action)) return new Response("action", { status: 400 });
    const args = body.args || {};
    if (Object.keys(args).some((k) => !actions[action].args.includes(k))) {
      return new Response("arguments", { status: 400 });
    }

    const result = await rpc(actions[action].fn, args);
    if (action === "begin" && result && result.need_upload && result.path) {
      result.upload_url = await signUpload(result.path);
    }
    return Response.json(result);
  } catch {
    return Response.json({ error: "gateway operation failed" }, { status: 502 });
  }
});
