"""Encrypt processed books into drop files: base64(IV || AES-256-CBC(json)).

usage: python3 -I make_drops.py <scratch>   (encrypts every books_out/*.json without a drop yet)
"""
import base64, json, os, subprocess, sys

S = sys.argv[1]
kf = os.path.join(S, "drop_master_key.txt")
if not os.path.exists(kf):
    open(kf, "w").write(os.urandom(32).hex())
key = open(kf).read().strip()
out = os.path.join(S, "drops2"); os.makedirs(out, exist_ok=True)
made = []
for f in sorted(os.listdir(os.path.join(S, "books_out"))):
    name = f[:-5]; dst = os.path.join(out, name + ".b64")
    if os.path.exists(dst):
        continue
    plain = open(os.path.join(S, "books_out", f), "rb").read()
    iv = os.urandom(16)
    ct = subprocess.run(["openssl", "enc", "-aes-256-cbc", "-K", key, "-iv", iv.hex()], input=plain,
                        capture_output=True, check=True).stdout
    back = subprocess.run(["openssl", "enc", "-d", "-aes-256-cbc", "-K", key, "-iv", iv.hex()], input=ct,
                          capture_output=True, check=True).stdout
    assert back == plain
    open(dst, "w").write(base64.encodebytes(iv + ct).decode())
    made.append(name)
print(json.dumps({"made": made, "total": len(os.listdir(out))}))
