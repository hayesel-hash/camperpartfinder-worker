"""Write staged aftermarket assertion rows as an encrypted payload for the supplied-drops branch, so large
cross-reference tables can be staged by the database (pg_net fetch + decrypt) without pasting thousands of
VALUES rows into SQL. Same format and key table as the supplied-document drops: base64(IV || AES-256-CBC(json)).

    python3 -I xref_payload.py <rows.json> <key_file> <out.b64>

rows.json: a JSON array of objects with the aftermarket_assertions_v1 columns used by stage_sql.COLS.
Load with:  select net.http_get('<raw url>');  then decrypt net._http_response.content with the key and insert
from jsonb_populate_recordset (see scripts/drive_intake/README.md, "Large cross-reference payloads")."""
import base64, json, os, subprocess, sys

rows = json.load(open(sys.argv[1]))
key = open(sys.argv[2]).read().strip()
plain = json.dumps(rows, ensure_ascii=False).encode()
iv = os.urandom(16)
ct = subprocess.run(["openssl", "enc", "-aes-256-cbc", "-K", key, "-iv", iv.hex()], input=plain,
                    capture_output=True, check=True).stdout
back = subprocess.run(["openssl", "enc", "-d", "-aes-256-cbc", "-K", key, "-iv", iv.hex()], input=ct,
                      capture_output=True, check=True).stdout
assert back == plain
open(sys.argv[3], "w").write(base64.encodebytes(iv + ct).decode())
print(json.dumps({"rows": len(rows), "bytes": len(plain)}))
