"""Disk-backed master catalogue staging. Never publishes identities or fitment."""
import hashlib
import json
import os
import re
import sys
from html.parser import HTMLParser
import subprocess
import shutil
import tempfile
import time
import urllib.request
import urllib.parse
import urllib.robotparser
from pathlib import Path

import pymupdf

GATEWAY = "https://dlijhukwzlqwtmiynncg.supabase.co/functions/v1/rv-master-disk-gateway"
AUDIENCE = "rv-master-disk-dlijhukwzlqwtmiynncg"
HOSTS = {"www.fiammaexpert.com", "www.frankana.de", "www.fiammausa.com", "library.suburbanrv.com", "www.coleman-mach.com", "library.coleman-mach.com", "support.lci1.com", "portal.truma.com", "www.dextergroup.com", "www.thetford.com", "www.winnebago.com", "catalog.winnebagoind.com", "manuals.heartlandowners.org", "myrvworks.com", "www.trigano-service.com", "www.alko-tech.com", "lipperteurope.com", "www.rvtechcheatsheet.com", "media.lippert.com", "www.carefreeofcolorado.com", "balrvproducts.com", "www.knott.de", "www.strombergcarlson.com", "valterra.com", "approducts.net", "jrproducts.net", "www.alliancerv.com", "files.ecommercedns.uk", "www.leisurespares.co.uk", "asavage.dyndns.org", "images.carid.com", "b2b.frankana.de"}
# Approved catalogue origins; robots and cross-origin redirect checks remain mandatory.
HOSTS.update(["www.airstream.com","www.reimo.com","www.mf-campingwelt.de","www.camper-nrw.de","www.camping-profi.de","irp.cdn-website.com","www.takalvans.com.au","www.northernrv.com.au"])
DISK_RESERVE = 2 * 1024**3

def disk_capacity(dest):
    return max(0, shutil.disk_usage(dest.parent).free - DISK_RESERVE)
AGENT = "RVPartFinder"
CODE = re.compile(r"(?<![A-Z0-9-])\d{5}(?:-\d{2}[A-Z0-9]|[A-Z]\d{2}[A-Z0-9])(?![A-Z0-9-])")
SKU = re.compile(r"\d{3}/\d{3}(?:-\d{1,3})?")
NUMBER = re.compile(r"[A-Z0-9][A-Z0-9 /.-]{2,30}", re.I)


class Held(Exception):
    pass


class SourceRedirect(Held):
    def __init__(self, target):
        super().__init__("redirect requires source review")
        self.target = target


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise SourceRedirect(newurl)


OPENER = urllib.request.build_opener(NoRedirect())


def checked(url):
    u = urllib.parse.urlsplit(url)
    if u.scheme != "https" or u.hostname not in HOSTS or u.username or u.password or u.port:
        raise Held("source host not allowlisted")
    return u


def open_source(url):
    checked(url)
    return OPENER.open(urllib.request.Request(url, headers={"User-Agent": AGENT}), timeout=120)


ROBOTS_CACHE = {}
ROBOTS_TTL = 300

def robots_policy(host):
    cached = ROBOTS_CACHE.get(host)
    if cached and time.monotonic() - cached[0] < ROBOTS_TTL:
        return cached[1], cached[2]
    # Policy discovery may redirect within its own origin; never consult an unrelated host.
    with open_catalogue(f"https://{host}/robots.txt", policy=lambda url: None) as response:
        content = response.read(262145)
    if len(content) > 262144 or b"<html" in content.lower():
        raise Held("robots policy unavailable")
    lines = content.decode("utf-8", errors="replace").splitlines()
    parser = urllib.robotparser.RobotFileParser()
    parser.parse(lines)
    delay = any(re.match(r"^\s*crawl-delay\s*:\s*[1-9]", line, re.I) for line in lines)
    ROBOTS_CACHE[host] = (time.monotonic(), parser, delay)
    return parser, delay

def robots_check(url):
    u = checked(url)
    parser, delay = robots_policy(u.hostname)
    if not parser.can_fetch(AGENT, url):
        raise Held("robots restriction")
    if delay:
        raise Held("crawl delay requires source review")


def open_catalogue(url, policy=None, opener=None):
    policy = policy or robots_check
    opener = opener or open_source
    origin = checked(url).hostname
    seen = set()
    for _ in range(5):
        if url in seen:
            raise Held("catalogue redirect loop")
        seen.add(url)
        policy(url)
        try:
            return opener(url)
        except SourceRedirect as exc:
            target = urllib.parse.urljoin(url, exc.target)
            if checked(target).hostname != origin:
                raise Held(f"cross-host redirect requires source review: {origin} -> {checked(target).hostname}")
            url = target
    raise Held("catalogue redirect limit")


def download(url, dest):
    digest = hashlib.sha256()
    total = 0
    with open_catalogue(url) as response, dest.open("wb") as f:
        capacity = disk_capacity(dest)
        if int(response.headers.get("Content-Length", "0")) > capacity:
            raise Held("insufficient runner disk capacity; larger runner required")
        while chunk := response.read(1024 * 1024):
            total += len(chunk)
            if total > capacity:
                raise Held("insufficient runner disk capacity; larger runner required")
            digest.update(chunk)
            f.write(chunk)
    with dest.open("rb") as f:
        if f.read(5) != b"%PDF-":
            raise Held("not a PDF")
    return digest.hexdigest(), total


def rpc(action, args=None):
    token_url = os.environ["ACTIONS_ID_TOKEN_REQUEST_URL"]
    token_url += ("&" if "?" in token_url else "?") + urllib.parse.urlencode({"audience": AUDIENCE})
    req = urllib.request.Request(token_url, headers={"Authorization": "Bearer " + os.environ["ACTIONS_ID_TOKEN_REQUEST_TOKEN"]})
    with OPENER.open(req, timeout=30) as response:
        jwt = json.load(response)["value"]
    req = urllib.request.Request(GATEWAY, data=json.dumps({"action": action, "args": args or {}}).encode(), headers={"Authorization": "Bearer " + jwt, "Content-Type": "application/json"}, method="POST")
    with OPENER.open(req, timeout=60) as response:
        return json.load(response)




def positioned_rows(page, p):
    # Explicit labelled columns only; recover unruled tables and split headers.
    pn = re.compile(r"(?:spare\s+)?part\s*(?:no\.?|number|#|nr\.?)|p\s*/\s*n|part\s*[- ]?nr\.?|artikelnummer|ersatzteilnummer", re.I)
    ds = re.compile(r"(?:part\s+)?description|designation|bezeichnung|benennung|omschrijving|désignation", re.I)
    words = page.get_text("words")
    lines = []
    for w in sorted(words, key=lambda w:(w[1],w[0])):
        if not lines or abs(w[1]-lines[-1][0][1])>3:
            lines.append([w])
        else:
            lines[-1].append(w)
    lines=[sorted(line,key=lambda w:w[0]) for line in lines]
    out=[]
    for h,line in enumerate(lines):
        if re.search(r"\b(?:supplier|vendor|brand|manufacturer|hersteller)\b"," ".join(w[4] for w in line),re.I):
            continue
        heads=[]
        for i in range(len(line)):
            for n in (1,2,3):
                ws=line[i:i+n]
                if len(ws)!=n or any(b[0]-a[2]>18 for a,b in zip(ws,ws[1:])):
                    continue
                t=" ".join(w[4] for w in ws)
                if pn.fullmatch(t): heads.append(("pn",ws[0][0],ws[-1][2]))
                if ds.fullmatch(t): heads.append(("ds",ws[0][0],ws[-1][2]))
        ns=[x for x in heads if x[0]=="pn"]
        dd=[x for x in heads if x[0]=="ds"]
        if len(ns)!=1 or len(dd)!=1: continue
        nx,dx=ns[0][1],dd[0][1]
        if abs(nx-dx)<25: continue
        # Stop at next heading or large vertical gap; do not scan unrelated sections.
        prev=line[0][1]
        for row in lines[h+1:]:
            y=row[0][1]
            if y-prev>38: break
            prev=y
            candidates=[w for w in row if abs(w[0]-nx)<15 and re.fullmatch(r"[A-Z0-9][A-Z0-9.-]{3,24}",w[4]) and re.search(r"\d",w[4]) and not re.fullmatch(r"\d{4}|\d+\.\d{1,2}",w[4])]
            if len(candidates)!=1: continue
            w=candidates[0]
            tail=[v for v in row if v[0]>=dx-12 and (dx>nx or v[2]<nx-5)]
            if not tail or abs(tail[0][0]-dx)>20: continue
            desc=" ".join(v[4] for v in tail)
            if len(desc)>240 or not re.search(r"[A-Za-z]{3}",desc) or re.match(r"^(?:model|serial|price|dimension|qty|quantity|voltage|page)\b",desc,re.I): continue
            out.append({"page":p,"number":w[4],"position":f"x{round(w[0])} y{round(w[1])} col{round(nx)}","description":desc,"method":"labelled-column-v1"})
    return list({(r["number"],r["position"]):r for r in out}.values())


def generic_table_rows(page,p):
    # Only accept a labelled part-number column with a description column.
    # A document can mix OEMs; publication is separately scoped by publisher.
    results=[]
    for strategy in ("lines","text"):
        try:
            tables=page.find_tables(strategy=strategy).tables
        except Exception:
            continue
        for table in tables:
            data=table.extract()
            for h,row in enumerate(data[:4]):
                cells=[re.sub(r"\s+"," ",str(c or "").strip().lower()) for c in row]
                pn=[i for i,c in enumerate(cells) if re.fullmatch(r"(?:spare )?part\s*(?:no\.?|number|#|nr\.?)|(?:article|art\.?)\s*(?:no\.?|number|nr\.?)|artikelnummer|ersatzteilnummer",c)]
                ds=[i for i,c in enumerate(cells) if re.fullmatch(r"(?:part )?description|designation|bezeichnung|benennung|omschrijving|désignation",c)]
                if len(pn)!=1 or len(ds)!=1 or pn[0]==ds[0]:
                    continue
                if any(re.search(r"manufacturer|supplier|vendor|brand|hersteller",c) for c in cells):
                    continue
                for ri,row2 in enumerate(data[h+1:],h+1):
                    if max(pn[0],ds[0])>=len(row2):
                        continue
                    num=str(row2[pn[0]] or "").strip()
                    desc=" ".join(str(row2[ds[0]] or "").split())
                    if not re.fullmatch(r"[A-Z0-9][A-Z0-9.-]{3,24}",num) or not re.search(r"\d",num) or re.fullmatch(r"\d{4}",num) or not re.search(r"[A-Za-z]{3}",desc):
                        continue
                    if re.search(r"^(?:model|serial|price|dimension|qty|quantity|voltage|page)\b",desc,re.I):
                        continue
                    if re.fullmatch(r"\d+[.]\d{1,2}",num) or len(desc)>240:
                        continue
                    box=table.rows[ri].cells[pn[0]]
                    if not box:
                        continue
                    results.append({"page":p,"number":num,"position":f"x{round(box[0])} y{round(box[1])} col{pn[0]}","description":desc,"method":"labelled-column-v1"})
                break
        if results:
            break
    return list({(r["number"],r["position"]):r for r in results}.values()) or positioned_rows(page,p)


def suburban_kit_rows(page,p):
    # Suburban master list uses a right-aligned KIT NO. column.
    # Require the actual printed column heading and six-digit kit identifiers.
    words=page.get_text("words")
    lines=[]
    for w in sorted(words,key=lambda w:(w[1],w[0])):
        if not lines or abs(w[1]-lines[-1][0][1])>4: lines.append([w])
        else: lines[-1].append(w)
    lines=[sorted(line,key=lambda w:w[0]) for line in lines]
    out=[]
    for h,line in enumerate(lines):
        kits=[(a,b) for a,b in zip(line,line[1:]) if a[4].upper()=="KIT" and re.fullmatch(r"NO\.?",b[4],re.I)]
        if len(kits)!=1 or not any(w[4].upper()=="DESCRIPTION" for w in line): continue
        a,b=kits[0]; center=(a[0]+b[2])/2
        for row in lines[h+1:]:
            candidates=[w for w in row if re.fullmatch(r"\d{6}",w[4]) and abs((w[0]+w[2])/2-center)<=22]
            if len(candidates)!=1: continue
            w=candidates[0]
            desc=" ".join(v[4] for v in row if v[2]<w[0]-8)
            # A number printed in a labelled kit column is sufficient for identity.
            # Do not invent a description or infer fitment from adjacent rows.
            if not re.search(r"[A-Za-z]{3}",desc): desc="Manufacturer replacement kit"
            if len(desc)>240: desc="Manufacturer replacement kit"
            out.append({"page":p,"number":w[4],"position":f"x{round(w[0])} y{round(w[1])} col{round(center)}","description":desc,"method":"labelled-column-v1"})
    return out

def coleman_stock_rows(page,p):
    # Stocking lists use quantity - exact part number - description.
    text=page.get_text()
    if not re.search(r"suggested stocking repair parts list",text,re.I): return []
    out=[]; active=False
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines",[]):
            t=" ".join(span["text"] for span in line["spans"]).strip()
            if re.search(r"^repair parts for",t,re.I): active=True; continue
            if re.search(r"^products that are involved",t,re.I): active=False; continue
            if not active: continue
            m=re.match(r"^\d{1,2}\s*[-–]\s*(\d{4}[A-Z]?[-]\d{4}|\d{4}[A-Z]\d{4})\s*([A-Za-z].{2,180})$",t)
            if m:
                x,y,*_=line["bbox"]
                out.append({"page":p,"number":m[1],"description":m[2],"position":f"x{round(x)} y{round(y)} col{round(x)}","method":"labelled-column-v1"})
    return out

def page_rows(page, p, adapter):
    # The master observations queue is candidate-only, including on parser agreement.
    words = page.get_text("words")
    rows = []
    if adapter == "fiamma-code-v1":
        if p <= 2:
            return rows
        for x0, y0, x1, y1, word, *_ in words:
            if CODE.fullmatch(word):
                rows.append({"page": p, "number": word, "position": f"x{round(x0)} y{round(y0)}"})
    elif adapter == "generic-table-v1":
        return generic_table_rows(page,p)
    elif adapter == "suburban-kit-v2":
        return suburban_kit_rows(page,p) or generic_table_rows(page,p)
    elif adapter == "coleman-stock-v2":
        return coleman_stock_rows(page,p) or generic_table_rows(page,p)
    elif adapter == "frankana-columns-v1":
        headers = [w for w in words if re.fullmatch(r"Hersteller-Nr\.?|Herst\.-Nr\.?", w[4], re.I)]
        dealers = [w for w in words if re.fullmatch(r"Art-Nr\.?", w[4], re.I)]
        for d in dealers:
            hs = [h for h in headers if abs(h[1]-d[1]) < 4 and h[0] < d[0]]
            if not hs:
                continue
            h = max(hs, key=lambda w: w[0])
            for s in words:
                if not SKU.fullmatch(s[4]) or abs(s[0]-d[0]) > 35 or s[1] <= d[1]:
                    continue
                candidates = [w for w in words if abs(w[1]-s[1]) < 3 and abs(w[0]-h[0]) < 35 and w[0] < s[0] and NUMBER.fullmatch(w[4]) and re.search(r"\d", w[4]) and not SKU.fullmatch(w[4])]
                if len(candidates) == 1:
                    w = candidates[0]
                    rows.append({"page": p,"number": w[4],"sku": s[4],"position": f"x{round(w[0])} y{round(w[1])}"})
    else:
        raise Held("unsupported adapter")
    return rows



# Adaptive extraction: learn column alignment on each page, not a manufacturer regex.
ADAPT_HEADER = re.compile(r"(?:spare\s+|replacement\s+|service\s+)?(?:part|kit|article|catalog(?:ue)?|item code|order)\s*(?:no\.?|number|#|nr\.?|code)|p\s*/\s*n|artikel(?:nummer|[- ]?nr\.?)|ersatzteil(?:nummer|[- ]?nr\.?)|référence(?: pièce)?|onderdeelnummer",re.I)
ADAPT_DESC = re.compile(r"(?:part\s+)?description|designation|désignation|bezeichnung|benennung|omschrijving|description of part|part name|nomenclature",re.I)
ADAPT_OTHER = re.compile(r"qty\.?|quantity|item|ref\.?|pos\.?|price|model|serial|voltage|weight|size|supplier|vendor|manufacturer|brand|hersteller",re.I)

def adaptive_rows(page,p):
    words=page.get_text("words")
    lines=[]
    for w in sorted(words,key=lambda w:(w[1],w[0])):
        if not lines or abs(w[1]-lines[-1][0][1])>3.5: lines.append([w])
        else: lines[-1].append(w)
    lines=[sorted(line,key=lambda w:w[0]) for line in lines]
    out=[]
    for h,line in enumerate(lines):
        headers=[]
        for i in range(len(line)):
            for count in range(1,5):
                ws=line[i:i+count]
                if len(ws)!=count or any(b[0]-a[2]>14 for a,b in zip(ws,ws[1:])): continue
                t=" ".join(w[4] for w in ws)
                typ="id" if ADAPT_HEADER.fullmatch(t) else "desc" if ADAPT_DESC.fullmatch(t) else "other" if ADAPT_OTHER.fullmatch(t) else None
                if typ: headers.append((typ,ws[0][0],ws[-1][2],t))
        # Remove shorter headers contained within a longer header (e.g. "part description").
        headers=[a for a in headers if not any(b[0]==a[0] and b[1]<=a[1] and b[2]>=a[2] and (b[2]-b[1]>a[2]-a[1]+1) for b in headers)]
        ids=[a for a in headers if a[0]=="id"]
        ds=[a for a in headers if a[0]=="desc"]
        if len(ids)!=1 or len(ds)!=1: continue
        if any(re.search(r"supplier|vendor|manufacturer|brand|hersteller",a[3],re.I) for a in headers): continue
        ident,desc=ids[0],ds[0]
        if abs(ident[1]-desc[1])<25: continue
        bounds=sorted([a for a in headers if a[0]!="other" or not (ident[1]<=a[1]<=ident[2] or desc[1]<=a[1]<=desc[2])],key=lambda a:a[1])
        def window(hdr):
            j=bounds.index(hdr)
            left=(bounds[j-1][2]+hdr[1])/2 if j else max(0,hdr[1]-32)
            right=(hdr[2]+bounds[j+1][1])/2 if j+1<len(bounds) else page.rect.width
            return left,right
        il,ir=window(ident); dl,dr=window(desc)
        candidates=[]
        prev=line[0][1]
        for row in lines[h+1:]:
            y=row[0][1]
            if y-prev>45: break
            prev=y
            txt=" ".join(w[4] for w in row)
            if re.search(r"(?:part|kit)\s*(?:number|no\.|#).*description|description.*(?:part|kit)\s*(?:number|no\.|#)",txt,re.I): break
            if re.search(r"^(?:notes?|warning|caution|installation instructions|specifications)\b",txt,re.I): break
            nums=[w for w in row if il<=(w[0]+w[2])/2<ir and re.fullmatch(r"[A-Z0-9][A-Z0-9.-]{3,24}",w[4]) and re.search(r"\d",w[4]) and not re.fullmatch(r"\d{4}|\d+\.\d{1,2}",w[4])]
            if len(nums)!=1: continue
            w=nums[0]
            d=" ".join(v[4] for v in row if dl<=(v[0]+v[2])/2<dr)
            if not re.search(r"[A-Za-z]{3}",d) or len(d)>240 or re.match(r"^(?:model|serial|price|dimension|qty|quantity|voltage|page)\b",d,re.I): continue
            candidates.append((w,d))
        # Infer left/right/center alignment from repeated actual rows. A lone
        # number needs the existing strict extractor or a local explicit label.
        for w,d in candidates:
            anchors=(w[0],w[2],(w[0]+w[2])/2)
            support=max(sum(abs((v[0],v[2],(v[0]+v[2])/2)[i]-anchors[i])<=6 for v,_ in candidates) for i in range(3))
            if support<2: continue
            out.append({"page":p,"number":w[4],"position":f"x{round(w[0])} y{round(w[1])} col{round(ident[1])}","description":d,"method":"labelled-column-v1"})
    return out


def family_templates(page,p):
    # Learn only from explicit manufacturer number and description headings.
    # Store normalized column geometry, not source text or credentials.
    words=page.get_text("words")
    lines=[]
    for w in sorted(words,key=lambda w:(w[1],w[0])):
        if not lines or abs(w[1]-lines[-1][0][1])>3.5: lines.append([w])
        else: lines[-1].append(w)
    shapes=[]
    for row in lines:
        row.sort(key=lambda w:w[0])
        headers=[]
        for i in range(len(row)):
            for count in range(1,5):
                ws=row[i:i+count]
                if len(ws)!=count or any(b[0]-a[2]>14 for a,b in zip(ws,ws[1:])): continue
                t=" ".join(w[4] for w in ws)
                typ="id" if ADAPT_HEADER.fullmatch(t) else "desc" if ADAPT_DESC.fullmatch(t) else None
                if typ: headers.append((typ,ws[0][0],ws[-1][2],t))
        headers=[a for a in headers if not any(b[0]==a[0] and b[1]<=a[1] and b[2]>=a[2] and b[2]-b[1]>a[2]-a[1]+1 for b in headers)]
        ids=[x for x in headers if x[0]=="id"];ds=[x for x in headers if x[0]=="desc"]
        if len(ids)!=1 or len(ds)!=1:continue
        if re.search(r"\b(?:manufacturer|supplier|vendor|brand|hersteller)\b"," ".join(w[4] for w in row),re.I):continue
        a,b=ids[0],ds[0]
        if abs(a[1]-b[1])<25:continue
        shapes.append({"id_x":round(a[1]/page.rect.width,2),"desc_x":round(b[1]/page.rect.width,2),"id_header":a[3].lower(),"desc_header":b[3].lower()})
    return shapes[:8]

def learned_rows(page,p,profiles):
    # Transfer layout geometry only where the current page explicitly confirms
    # the same headings; never infer an identity from a bare numeric token.
    if not profiles:return []
    current=family_templates(page,p)
    if not current:return []
    matches=[]
    for shape in current:
        if any(abs(shape["id_x"]-float(x.get("id_x",-1)))<=.025 and abs(shape["desc_x"]-float(x.get("desc_x",-1)))<=.025 and shape["id_header"]==x.get("id_header") and shape["desc_header"]==x.get("desc_header") and x.get("samples",0)>=2 for x in profiles):matches.append(shape)
    if not matches:return []
    out=[]
    words=page.get_text("words")
    for shape in matches:
        ix=shape["id_x"]*page.rect.width;dx=shape["desc_x"]*page.rect.width
        # Re-use a learned heading alignment for right-aligned IDs and gaps
        # but retain the strict local description/published identity gates.
        for w in words:
            if abs(w[0]-ix)>max(16,page.rect.width*.025) and abs(w[2]-ix)>max(16,page.rect.width*.025):continue
            num=w[4]
            if not re.fullmatch(r"[A-Z0-9][A-Z0-9.-]{3,24}",num) or not re.search(r"\d",num) or re.fullmatch(r"\d{4}|\d+\.\d{1,2}",num):continue
            row=sorted([v for v in words if abs(v[1]-w[1])<=3.5],key=lambda v:v[0])
            if not row:continue
            # Require a locally matching heading above the row, no intervening
            # section boundary, and plausible description aligned with template.
            head=[v for v in words if v[1]<w[1] and abs(v[0]-ix)<20 and v[4].lower()==shape["id_header"].split()[0]]
            if not head:continue
            hy=max(v[1] for v in head)
            if w[1]-hy>350:continue
            if any(re.match(r"^(?:warning|caution|notes?|specifications)$",v[4],re.I) for v in words if hy<v[1]<w[1] and v[0]<page.rect.width*.2):continue
            desc=[v for v in row if v[0]>=dx-12 and (dx>ix or v[2]<ix-8)]
            if not desc or abs(desc[0][0]-dx)>20:continue
            d=" ".join(v[4] for v in desc)
            if len(d)>240 or not re.search(r"[A-Za-z]{3}",d) or re.match(r"^(?:model|serial|price|dimension|qty|quantity|voltage|page)\b",d,re.I):continue
            out.append({"page":p,"number":num,"position":f"x{round(w[0])} y{round(w[1])} col{round(ix)}","description":d,"method":"labelled-column-v1"})
    return list({(r["number"],r["position"]):r for r in out}.values())

def explicit_inline_rows(page,p):
    """Recover locally labelled part identifiers, never bare numeric tokens."""
    out=[]
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines",[]):
            t=" ".join(span["text"] for span in line["spans"]).strip()
            m=re.fullmatch(r"(?:replacement |spare |service )?part\s*(?:number|no\.?|#)\s*[:=]\s*([A-Z0-9][A-Z0-9.-]{3,24})\s+[–—-]\s+([A-Za-z].{2,180})",t,re.I)
            if not m or not re.search(r"\d",m[1]) or re.fullmatch(r"\d{4}|\d+\.\d{1,2}",m[1]):continue
            x,y,*_=line["bbox"]
            out.append({"page":p,"number":m[1],"description":m[2],"position":f"x{round(x)} y{round(y)}","method":"labelled-column-v1"})
    return out


def reconcile_ocr(first,second):
    """Require exact token agreement and overlapping pixel positions."""
    def overlap(a,b):
        x,y,w,h=a; X,Y,W,H=b
        area=max(0,min(x+w,X+W)-max(x,X))*max(0,min(y+h,Y+H)-max(y,Y))
        return area/max(1,min(w*h,W*H))
    for row in first:
        matches=[v for v in second if v["number"]==row["number"] and overlap(row["bbox_px"],v["bbox_px"])>=0.7]
        row["second_pass_agrees"]=len(matches)==1
        row["recognition_status"]="two_pass_agreement" if len(matches)==1 else "held_disagreement"
    return first


def independent_ocr(image, candidates):
    """GOCR crop recognition, with no changes to publication eligibility."""
    if not shutil.which("gocr"):
        return "engine_unavailable"
    from PIL import Image
    with Image.open(image) as original:
        for idx,row in enumerate(candidates[:100]):
            x,y,w,h=row["bbox_px"]
            crop=original.crop((max(0,x-8),max(0,y-8),min(original.width,x+w+8),min(original.height,y+h+8)))
            path=image.parent/"candidate.pgm"
            crop.convert("L").save(path)
            try:
                run=subprocess.run(["gocr","-i",str(path)],capture_output=True,check=True,timeout=3)
                token=run.stdout.decode("utf-8","replace").strip()
                row["independent_engine"]="gocr"
                row["independent_text"]=token[:80]
                row["independent_agreement"]=token==row["number"]
            except (subprocess.SubprocessError,OSError):
                row["independent_agreement"]=False
                row["independent_error"]="recognition_failed"
    return "completed"


def ocr_preview(page,p):
    """Unverified OCR evidence only; never return publication observations."""
    if max(page.rect.width,page.rect.height)*300/72>12000:
        return {"status":"held_oversize"}
    if not shutil.which("tesseract"):
        return {"status":"ocr_unavailable"}
    import csv
    import io
    with tempfile.TemporaryDirectory(prefix="rv-ocr-") as tmp:
        image=Path(tmp)/"page.png"
        page.get_pixmap(dpi=300,colorspace=pymupdf.csGRAY,alpha=False).save(image)
        runs=[subprocess.run(["tesseract",str(image),"stdout","--psm",mode,"tsv"],capture_output=True,check=True,timeout=45) for mode in ("6","11")]
    def parse(run):
        lines={}
        for w in csv.DictReader(io.StringIO(run.stdout.decode("utf-8","replace")),delimiter="\t"):
            if w["level"]!="5" or not w["text"].strip():continue
            key=tuple(w[k] for k in ("block_num","par_num","line_num"))
            lines.setdefault(key,[]).append(w)
        candidates=[]
        for words in lines.values():
            for i,w in enumerate(words):
                num=w["text"].strip()
                if not re.fullmatch(r"[A-Z0-9][A-Z0-9.-]{3,24}",num) or not re.search(r"\d",num) or float(w["conf"])<85:continue
                candidates.append({"page":p,"number":num,"bbox_px":[int(w[k]) for k in ("left","top","width","height")],"confidence":float(w["conf"]),"line":" ".join(v["text"] for v in words)[:240],"dpi":300})
        return candidates
    candidates=reconcile_ocr(parse(runs[0]),parse(runs[1]))
    with tempfile.TemporaryDirectory(prefix="rv-ocr-check-") as tmp:
        image=Path(tmp)/"page.png"
        page.get_pixmap(dpi=300,colorspace=pymupdf.csGRAY,alpha=False).save(image)
        try:
            independent_status=independent_ocr(image,[r for r in candidates if r["second_pass_agrees"]])
        except ImportError:
            independent_status="image_dependency_unavailable"
    return {"status":"unverified","engine":"tesseract","passes":["psm6","psm11"],"independent_engine":"gocr","independent_status":independent_status,"candidates":candidates[:100],"candidate_count":len(candidates)}


# High-specificity manufacturer's numbering scheme supplement.
# Exact code tokens only; preserve the source coordinates and do not infer fitment.
def hwh_rows(page,p):
    rows=[]
    for x0,y0,x1,y1,word,*_ in page.get_text("words"):
        if not re.fullmatch(r"(?:RAP|AP|RP)[0-9]{3,7}",word):
            continue
        # Preserve the identity even on diagrams, but do not fabricate a description.
        rows.append({"page":p,"number":word,"description":"HWH catalogue part "+word,
                     "position":f"x{round(x0)} y{round(y0)}","method":"hwh-exact-code-v1"})
    return rows

def numbering_shape(token):
    # Keep punctuation and run lengths; never use a bare shape as identity evidence.
    return re.sub(r"[0-9]", "9", re.sub(r"[A-Z]", "A", token))

def pattern_guided_rows(page,p,patterns):
    """Recover aligned rows under locally explicit part and description headings."""
    shapes={v["shape"] for v in patterns if v.get("samples",0)>=20}
    if not shapes:return []
    words=page.get_text("words")
    lines=[]
    for w in sorted(words,key=lambda w:(w[1],w[0])):
        if not lines or abs(w[1]-lines[-1][0][1])>3.5:lines.append([w])
        else:lines[-1].append(w)
    out=[]
    for i,line in enumerate(lines):
        line=sorted(line,key=lambda w:w[0])
        heads=[]
        for j in range(len(line)):
            for k in range(1,4):
                ws=line[j:j+k]
                if len(ws)!=k or any(b[0]-a[2]>18 for a,b in zip(ws,ws[1:])):continue
                t=" ".join(w[4] for w in ws)
                if re.fullmatch(r"(?:spare |replacement )?part\s*(?:no\.?|number|#|nr\.?)|p\s*/\s*n|artikelnummer|ersatzteilnummer",t,re.I):
                    heads.append(("id",ws[0][0],ws[-1][2]))
                if re.fullmatch(r"(?:part )?description|designation|bezeichnung|benennung|omschrijving",t,re.I):
                    heads.append(("desc",ws[0][0],ws[-1][2]))
        ids=[x for x in heads if x[0]=="id"];ds=[x for x in heads if x[0]=="desc"]
        if len(ids)!=1 or len(ds)!=1 or re.search(r"\b(?:brand|supplier|vendor|manufacturer|hersteller)\b"," ".join(w[4] for w in line),re.I):continue
        ix,dx=ids[0][1],ds[0][1]
        if abs(ix-dx)<25:continue
        prev=line[0][1];candidates=[]
        for row in lines[i+1:]:
            y=row[0][1]
            if y-prev>42 or re.search(r"\b(?:warning|caution|specifications|part number|part no\.|description)\b"," ".join(w[4] for w in row),re.I):break
            prev=y
            nums=[w for w in row if numbering_shape(w[4]) in shapes and re.fullmatch(r"[A-Z0-9][A-Z0-9.-]{4,24}",w[4]) and (abs(w[0]-ix)<=25 or abs(w[2]-ids[0][2])<=25)]
            if len(nums)!=1:continue
            w=nums[0]
            desc=sorted([v for v in row if v[0]>=dx-12 and (dx>ix or v[2]<ix-5)],key=lambda v:v[0])
            if not desc or abs(desc[0][0]-dx)>20:continue
            d=" ".join(v[4] for v in desc)
            if not re.search(r"[A-Za-z]{3}",d) or len(d)>240 or re.match(r"^(?:model|serial|price|qty|quantity|voltage|page)\b",d,re.I):continue
            candidates.append({"page":p,"number":w[4],"description":d,"position":f"x{round(w[0])} y{round(w[1])} col{round(ix)}","method":"labelled-column-v1"})
        if len({r["number"] for r in candidates})>=2:out.extend(candidates)
    return out

def adaptive_page(page,p,adapter,family_profile=None):
    # Union independent layout strategies; prefer existing exact table cells
    # for matching identities. No second parser is required for publication.
    methods={}
    errors={}
    for name,fn in (("table",generic_table_rows),("position",positioned_rows),("adaptive",adaptive_rows),("inline",explicit_inline_rows)):
        try: methods[name]=fn(page,p)
        except Exception as exc:
            methods[name]=[]
            errors[name]=type(exc).__name__

    if adapter=="suburban-kit-v2": methods["kit"]=suburban_kit_rows(page,p)
    if adapter=="coleman-stock-v2": methods["stock"]=coleman_stock_rows(page,p)
    if adapter=="hwh-code-v1": methods["hwh_exact"]=hwh_rows(page,p)
    methods["learned"]=learned_rows(page,p,(family_profile or {}).get("profiles",[]))
    methods["pattern_guided"]=pattern_guided_rows(page,p,(family_profile or {}).get("number_patterns",[]))
    chosen={}
    for name,rows in methods.items():
        for row in rows: chosen.setdefault(row["number"],row)
    return list(chosen.values()),{"page":p,"words":len(page.get_text("words")),"methods":{k:len(v) for k,v in methods.items()},"errors":errors,"failure_class":("parser_error" if errors else "image_only" if not page.get_text("words") else "unrecognised_layout") if not chosen else None,"unique":len(chosen),"profiles":family_templates(page,p) if chosen else [],"layout":"parts" if chosen else "unresolved" if re.search(r"part\s*(?:no\.?|number|#)|spare parts|repair parts|kit no\.",page.get_text(),re.I) else "other"}


def finish_with_recovery(action, args, call=rpc, sleep=time.sleep):
    """Only retry lease-bound completion; never retry a claim after an ambiguous response."""
    uncertain = False
    for attempt in range(3):
        try:
            saved = call(action, args)
            if uncertain and (saved is False or saved == -1):
                return None  # Lease may already have been consumed; audit, do not reclaim.
            return saved
        except urllib.error.HTTPError as exc:
            if exc.code not in (502, 503, 504):
                raise
        except (TimeoutError, urllib.error.URLError):
            pass
        uncertain = True
        if attempt < 2:
            sleep(2 ** (attempt + 1))
    return None  # Existing lease expiry provides bounded recovery.


# Catalogue attribution is based on explicit document mastheads/copyright, never URL or host.
BRAND_MASTHEADS = {
    "HWH": r"HWH\s+(?:CORPORATION|CORP\.?)",
    "Dometic": r"DOMETIC(?:\s+(?:CORPORATION|GROUP|LLC|AB|USA|INC\.?))?",
    "Norcold": r"NORCOLD(?:\s*,?\s*(?:INC\.?|LLC))?",
    "Suburban": r"SUBURBAN(?:\s+(?:MANUFACTURING|DIVISION|RV|AIRXCEL))?",
    "Aqua-Hot": r"AQUA[- ]HOT(?:\s+HEATING\s+SYSTEMS(?:\s*,?\s*INC\.?)?)?",
    "Splendide": r"SPLENDIDE(?:\s+(?:LAUNDRY|APPLIANCES))?",
    "Cummins Onan": r"(?:CUMMINS\s+ONAN|ONAN\s+CORPORATION|ONAN)",
    "Winnebago": r"WINNEBAGO(?:\s+INDUSTRIES(?:\s*,?\s*INC\.?)?)?",
    "MaxxAir": r"MAXX[- ]?AIR(?:\s+(?:VENTILATION|AIRXCEL))?",
    "Coleman-Mach": r"COLEMAN[- ]MACH",
    "Carefree of Colorado": r"CAREFREE\s+OF\s+COLORADO",
    "Fiamma": r"FIAMMA(?:\s+S\.?P\.?A\.?)?",
    "Thetford": r"THETFORD(?:\s+(?:CORPORATION|LLC|BV))?",
    "Truma": r"TRUMA(?:\s+GERAETETECHNIK|\s+GERÄTETECHNIK)?",
    "Dexter": r"DEXTER(?:\s+(?:AXLE|GROUP))?",
    "Lippert": r"LIPPERT(?:\s+COMPONENTS(?:\s*,?\s*INC\.?)?)?",
    "AL-KO": r"AL[- ]KO(?:\s+VEHICLE\s+TECHNOLOGY)?",
}
def catalogue_attribution(doc):
    hits = {}
    # First pages only: require document identity in its own title/copyright area.
    for i in range(min(4, len(doc))):
        lines = doc[i].get_text("text").splitlines()
        for line in lines[:100]:
            line = " ".join(line.split()).strip()
            if not line or len(line) > 180:
                continue
            for maker, pattern in BRAND_MASTHEADS.items():
                masthead = re.fullmatch(pattern, line, re.I)
                copyright = re.fullmatch(r"(?:©|copyright)\s*(?:\d{4}(?:[-–]\d{4})?\s*)?" + pattern + r"(?:\s+\d{4})?[. ]*", line, re.I)
                if masthead or copyright:
                    hits.setdefault(maker, {"manufacturer":maker,"page":i+1,"statement":line,"method":"document-masthead-v1"})
    # Never resolve competing brand mastheads by guessing.
    return {"status":"attributed","evidence":next(iter(hits.values()))} if len(hits)==1 else {"status":"ambiguous" if hits else "unresolved","candidates":sorted(hits)}

def explicit_replacement_rows(page,p):
    """Capture only directional statements; never infer from adjacent numbers."""
    out=[]
    code=r"[A-Z0-9][A-Z0-9.-]{3,24}"
    pat=re.compile(r"("+code+r")\s+(superseded by|replaced by)\s+("+code+r")",re.I)
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines",[]):
            t=" ".join(" ".join(span["text"] for span in line["spans"]).split())
            m=pat.fullmatch(t)
            if not m or m[1]==m[3] or not all(re.search(r"\d",x) for x in (m[1],m[3])):continue
            x,y,*_=line["bbox"]
            out.append({"page":p,"original":m[1],"replacement":m[3],"statement":t,"position":f"x{round(x)} y{round(y)}","method":"explicit-directional-line-v1","kind":"supersession" if m[2].lower()=="superseded by" else "replacement"})
    return out

def main(work_mode='any'):
    claim_action = {'any':'claim','manifest':'claim_manifest','batch':'claim_batch'}[work_mode]
    deadline = time.monotonic() + 20 * 60
    with tempfile.TemporaryDirectory(prefix="rv-master-") as tmp:
        cache = {}
        replenishment_attempted = False
        for _ in range(400):
            if time.monotonic() > deadline:
                break
            job = rpc(claim_action)
            if not job:
                # A drained queue must trigger discovery rather than silently ending.
                # Bound replenishment to one attempt per run to avoid busy-looping.
                if work_mode == 'any' and not replenishment_attempted and time.monotonic() < deadline - 120:
                    replenishment_attempted = True
                    print(json.dumps({"event": "queue_empty", "action": "repository_replenishment"}), flush=True)
                    discover_repositories()
                    job = rpc("claim")
                if not job:
                    print(json.dumps({"event": "queue_empty_after_replenishment", "action": "needs_acquisition_or_promotion"}), flush=True)
                    if work_mode != "any" and time.monotonic() < deadline - 30:
                        time.sleep(20)
                        continue
                    break
            cid, token, mode = job["id"], job["lease"], job["mode"]
            args = {"cid": cid, "tok": token}
            if mode == "batch":
                args["first_page"] = job["page_start"]
            outcome, details = "retry", {}
            try:
                url = job["url"]
                if url not in cache:
                    # Retain only current document; sequential leased batches reuse it.
                    for old_dest, _, _ in cache.values():
                        old_dest.unlink(missing_ok=True)
                    cache.clear()
                    dest = Path(tmp) / (hashlib.sha256(url.encode()).hexdigest() + ".pdf")
                    fingerprint, size = download(url, dest)
                    cache[url] = (dest, fingerprint, size)
                dest, fingerprint, size = cache[url]
                with pymupdf.open(dest) as doc:
                    if mode == "manifest":
                        if len(doc) < 1:
                            raise Held("empty PDF")
                        outcome, details = "ready", {"hash": fingerprint, "pages": len(doc), "bytes": size, "engine": "pymupdf", "attribution": catalogue_attribution(doc)}
                    else:
                        if fingerprint != job["sha256"]:
                            raise Held("document version changed")
                        adapter = job["adapter"]
                        # Preview is an analysis phase, not a terminal extraction mode.
                        if adapter == "layout-preview-v1":
                            adapter = "adaptive-table-v3"
                        sample = []
                        if adapter in ("generic-table-v1","suburban-kit-v2","coleman-stock-v2","adaptive-table-v3","hwh-code-v1"):
                            rows = []
                            for p in range(job["page_start"],job["page_end"]+1):
                                found,metrics=adaptive_page(doc[p-1],p,adapter,job.get("family_profile"))
                                if not metrics["words"] and not found:
                                    try:
                                        metrics["ocr_preview"]=ocr_preview(doc[p-1],p)
                                    except Exception as exc:
                                        metrics["ocr_preview"]={"status":"ocr_error","error":type(exc).__name__}
                                rows.extend(found); sample.append(metrics)
                        else:
                            rows = [r for p in range(job["page_start"], job["page_end"]+1) for r in page_rows(doc[p-1], p, adapter)]
                        replacements = [r for p in range(job["page_start"],job["page_end"]+1) for r in explicit_replacement_rows(doc[p-1],p)]
                        if len(rows) > 2000:
                            raise Held("batch exceeds row limit")
                        outcome, details = "complete", {"hash": fingerprint, "rows": rows, "extracted": len(rows), "engine": "pymupdf", "layout_preview": sample, "extraction_version":"adaptive-yield-v2","pattern_version":"number-shape-v1","replacement_version":"explicit-directional-v1","replacements":replacements, "attribution": catalogue_attribution(doc) if job.get("authority") == "distributor" else {}}
            except Held as exc:
                outcome, details = "held", {"error": str(exc)}
            except urllib.error.HTTPError as exc:
                outcome = "held" if exc.code in (401, 403, 404, 429) else "retry"
                details = {"error": f"source HTTP {exc.code}"}
            except Exception as exc:
                details = {"error": type(exc).__name__}
            saved = finish_with_recovery("manifest" if mode == "manifest" else "finish", {**args, "outcome": outcome, "details": details})
            if saved is None:
                print(json.dumps({"catalogue":cid,"mode":mode,"outcome":"completion_uncertain","error":"gateway_transient","lease_recovery":True}),flush=True)
                continue
            if saved is False or saved == -1:
                raise RuntimeError("lease rejected")
            print(json.dumps({"catalogue": cid, "mode": mode, "outcome": outcome, "saved": saved, "extracted": details.get("extracted"), "error": details.get("error")}), flush=True)


def verify_master():
    # Run independent Poppler extraction, once per document, after SHA-256 validation.
    with tempfile.TemporaryDirectory(prefix="rv-verify-") as tmp:
        cache = {}
        for _ in range(120):
            job = rpc("verify_claim")
            if not job:
                return
            url = job["url"]
            if url not in cache:
                dest = Path(tmp) / "catalogue.pdf"
                fingerprint, _ = download(url, dest)
                if fingerprint != job["sha256"]:
                    raise Held("document version changed during independent verification")
                text = subprocess.run(["pdftotext","-layout",str(dest),"-"],check=True,capture_output=True,timeout=180).stdout.decode("utf-8","replace")
                cache[url] = (fingerprint, text.split("\f"))
            fingerprint, pages = cache[url]
            if fingerprint != job["sha256"] or len(pages) < job["page_end"]:
                raise Held("independent parser page count or fingerprint mismatch")
            matches = [{"page":p,"number":n} for p in range(job["page_start"],job["page_end"]+1) if p>2 for n in sorted(set(CODE.findall(pages[p-1])))]
            if len(matches)>2000:
                raise Held("independent batch exceeds row limit")
            result=rpc("verify_finish",{"cid":job["catalogue_id"],"first_page":job["page_start"],"document_hash":fingerprint,"details":{"method":"poppler-page-v1","matches":matches}})
            print(json.dumps({"verified_catalogue":job["catalogue_id"],"first_page":job["page_start"],"result":result}),flush=True)


def eligible_catalogue_link(url, title):
    # Exclude explicit operator/owner manual PDFs, not their library landing pages.
    # Explicit parts or supersession titles take precedence over generic manual labels.
    decoded = urllib.parse.unquote(url)
    if not re.search(r"\.pdf(?:$|[?&#])", decoded, re.I):
        return True
    if re.search(r"parts|spare|ersatz|supersession|cross.reference|replacement|catalog|katalog", title, re.I):
        return True
    return not bool(re.search(r"operator[ _/-]*manuals?|owners?[ _/-]*manuals?|bedienungsanleitung", decoded+" "+title, re.I))


class CatalogueLinks(HTMLParser):
    def __init__(self, base):
        super().__init__(convert_charrefs=True)
        self.base = base
        self.href = None
        self.title = []
        self.links = {}

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.href = dict(attrs).get("href")
            self.title = []

    def handle_data(self, data):
        if self.href:
            self.title.append(data)

    def handle_endtag(self, tag):
        if tag != "a" or not self.href:
            return
        url = urllib.parse.urldefrag(urllib.parse.urljoin(self.base, self.href))[0]
        title = " ".join(" ".join(self.title).split())[:300]
        u = urllib.parse.urlsplit(url)
        if u.scheme == "https" and u.hostname and not u.username and not u.password and len(url) <= 1800 and re.search(r"parts|manual|catalog|katalog|ersatz|spare|diagram|[.]pdf",url+" "+title,re.I):
            if eligible_catalogue_link(url, title):
                self.links[url] = {"url":url,"title":title}
        self.href = None
        self.title = []


def validate_catalogue_link(url):
    # A bounded GET verifies real PDF magic, not an HTML soft-404 or misleading suffix.
    try:
        with open_catalogue(url) as response:
            return response.read(5) == b"%PDF-"
    except (Held, OSError, urllib.error.URLError):
        return False


def discover_repositories():
    for _ in range(8):
        job = rpc("repository_claim")
        if not job:
            return
        details = {"links":[]}
        try:
            robots_check(job["url"])
            with open_catalogue(job["url"]) as resp:
                raw = resp.read(8*1024*1024+1)
            if len(raw)>8*1024*1024:
                raise Held("repository listing exceeds limit")
            parser = CatalogueLinks(job["url"])
            parser.feed(raw.decode("utf-8","replace"))
            links = sorted(parser.links.values(),key=lambda r: (not bool(re.search(r"master|complete|catalog|katalog",r["url"]+" "+r["title"],re.I)),not bool(re.search(r"[.]pdf($|[?])",r["url"],re.I)),r["url"]))
            # Validate manufacturer PDF candidates before promotion. Keep bounded
            # listing frontier and give remaining untested candidates a subsequent scan.
            if job.get("kind") == "manufacturer":
                links = [r for r in links if urllib.parse.urlsplit(r["url"]).hostname == job["host"]]
                pdfs = [r for r in links if re.search(r"\\.pdf(?:$|[?])",r["url"],re.I) and re.search(r"parts|spare|ersatz|catalog|katalog|supersession|cross.reference",r["url"]+" "+r["title"],re.I)]
                listings = [r for r in links if not re.search(r"\\.pdf(?:$|[?])",r["url"],re.I)]
                verified = [dict(r, validated_pdf=True) for r in pdfs[:40] if validate_catalogue_link(r["url"])]
                details = {"links":verified+listings[:100],"status":"complete","discovered_total":len(links),"validated_pdfs":len(verified),"pdf_candidates":len(pdfs)}
            else:
                details = {"links":links[:500],"status":"complete","discovered_total":len(links)}
        except Exception as exc:
            details = {"links":[],"status":"held","error":str(exc)[:180]}
        count = rpc("repository_finish",{"rid":job["id"],"details":details})
        print(json.dumps({"repository":job["id"],"links":count,"status":details["status"],"error":details.get("error")}),flush=True)


def self_test():
    assert not eligible_catalogue_link("https://www.winnebago.com/Admin/Public/Download.aspx?file=Files/OperatorManuals/08Vista.pdf", "Vista")
    assert eligible_catalogue_link("https://www.winnebago.com/OperatorManuals/", "Library")
    assert eligible_catalogue_link("https://www.winnebago.com/OperatorManuals/parts.pdf", "Replacement parts catalogue")

    with pymupdf.open() as doc:
        page=doc.new_page()
        page.insert_text((50,50),"AP12345 superseded by RAP12345")
        page.insert_text((50,75),"AP12346 RAP12346")
        assert len(explicit_replacement_rows(page,1))==1
    policy_url = "https://b2b.frankana.de/robots.txt"
    policy_target = "https://b2b.frankana.de/robots-public.txt"
    def policy_fixture(url):
        if url == policy_url:
            raise SourceRedirect(policy_target)
        return url
    assert open_catalogue(policy_url, policy=lambda url: None, opener=policy_fixture) == policy_target
    def foreign_policy(url):
        raise SourceRedirect("https://www.frankana.de/robots.txt")
    try:
        open_catalogue(policy_url, policy=lambda url: None, opener=foreign_policy)
        raise AssertionError("foreign robots policy accepted")
    except Held as exc:
        assert str(exc).startswith("cross-host redirect requires source review:")

    start = "https://b2b.frankana.de/old.pdf"
    target = "https://b2b.frankana.de/new.pdf"
    visited = []
    def redirect_fixture(url):
        if url == start:
            raise SourceRedirect(target)
        return "fixture"
    assert open_catalogue(start, visited.append, redirect_fixture) == "fixture"
    assert visited == [start, target]
    def denied(url):
        if url == target:
            raise Held("robots restriction")
    try:
        open_catalogue(start, denied, redirect_fixture)
        raise AssertionError("redirect bypassed robots")
    except Held as exc:
        assert str(exc) == "robots restriction"

    assert numbering_shape("RP12345")=="AA99999"
    with pymupdf.open() as doc:
        page=doc.new_page()
        page.insert_text((50,50),"123456 123457")
        assert not pattern_guided_rows(page,1,[{"shape":"999999","samples":30}])
    with pymupdf.open() as doc:
        page=doc.new_page()
        page.insert_text((50,50),"AP12345 RAP90594 RP6352 ML12345 AP123456789 ABC12345")
        assert {r["number"] for r in hwh_rows(page,1)}=={"AP12345","RAP90594","RP6352"}
    with pymupdf.open() as doc:
        for _ in range(3):
            doc.new_page()
        doc[2].insert_text((50, 50), "98655-123 98655-12A 12345 123456789")
        rows = page_rows(doc[2], 3, "fiamma-code-v1")
        assert {r["number"] for r in rows} == {"98655-123", "98655-12A"}, rows
        assert not page_rows(doc[2], 2, "fiamma-code-v1")
    with pymupdf.open() as doc:
        page=doc.new_page()
        for x in (40,150,350): page.draw_line((x,40),(x,100))
        for y in (40,60,80,100): page.draw_line((40,y),(350,y))
        for x,y,t in [(45,53,"Part number"),(155,53,"Description"),(45,73,"123456"),(155,73,"Water valve"),(45,93,"12.50"),(155,93,"Price")]: page.insert_text((x,y),t,fontsize=9)
        rows=generic_table_rows(page,1)
        assert [r["number"] for r in rows]==["123456"],rows
    with pymupdf.open() as doc:
        page=doc.new_page()
        for x,y,t in [(45,53,"PART NO."),(155,53,"DESCRIPTION"),(45,73,"123456"),(155,73,"Water valve"),(45,93,"12.50"),(155,93,"Price")]: page.insert_text((x,y),t,fontsize=9)
        assert [r["number"] for r in positioned_rows(page,1)]==["123456"]
    with pymupdf.open() as doc:
        page=doc.new_page()
        page.insert_text((100,50),"DESCRIPTION")
        page.insert_text((450,50),"KIT NO.")
        page.insert_text((100,70),"Valve assembly")
        page.insert_text((450,70),"521099")
        page.insert_text((100,90),"Serial 123456")
        assert [r["number"] for r in suburban_kit_rows(page,1)]==["521099"]
    with pymupdf.open() as doc:
        page=doc.new_page()
        for x,y,t in [(40,50,"DESCRIPTION"),(330,50,"KIT NO."),(450,50,"QTY"),(40,70,"Water valve"),(335,70,"123456"),(450,70,"2"),(40,90,"Drain plug"),(335,90,"123457"),(450,90,"1")]: page.insert_text((x,y),t,fontsize=10)
        assert {r["number"] for r in adaptive_rows(page,1)}=={"123456","123457"}
    with pymupdf.open() as doc:
        page=doc.new_page()
        page.insert_text((50,50),"MODEL NUMBER 123456")
        assert not adaptive_rows(page,1)
    with pymupdf.open() as doc:
        page=doc.new_page()
        for x,y,t in [(40,50,"DESCRIPTION"),(330,50,"KIT NO."),(40,70,"Water valve"),(335,70,"123456"),(40,90,"Drain plug"),(335,90,"123457")]: page.insert_text((x,y),t,fontsize=10)
        profiles=[dict(s,samples=2) for s in family_templates(page,1)]
        assert profiles
        assert {r["number"] for r in learned_rows(page,1,profiles)}=={"123456","123457"}
        assert not learned_rows(page,1,[dict(profiles[0],id_x=.99)])
        empty=doc.new_page()
        empty.insert_text((335,70),"123456")
        assert not learned_rows(empty,2,profiles)
    with pymupdf.open() as doc:
        page=doc.new_page()
        rows,metrics=adaptive_page(page,1,"adaptive-table-v3")
        assert not rows and metrics["failure_class"]=="image_only",metrics
        page.insert_text((50,50),"MODEL NUMBER 123456")
        rows,metrics=adaptive_page(page,1,"adaptive-table-v3")
        assert not rows and metrics["failure_class"]=="unrecognised_layout",metrics
    with pymupdf.open() as doc:
        page=doc.new_page()
        page.insert_text((40,50),"Part number: AB12345 - Water valve")
        page.insert_text((40,70),"Model number: XY12345 - Water valve")
        assert {r["number"] for r in explicit_inline_rows(page,1)}=={"AB12345"}
    first=[{"number":"AB123","bbox_px":[10,10,40,20]},{"number":"CD456","bbox_px":[90,10,40,20]}]
    second=[{"number":"AB123","bbox_px":[11,10,40,20]},{"number":"CD458","bbox_px":[90,10,40,20]}]
    assert [r["second_pass_agrees"] for r in reconcile_ocr(first,second)]==[True,False]
    # End-to-end scanned-page smoke test: independent OCR may produce candidates,
    # but no OCR candidate is returned as a publishable structured row.
    if shutil.which("tesseract") and shutil.which("gocr"):
        from PIL import Image, ImageDraw, ImageFont
        with tempfile.TemporaryDirectory(prefix="rv-ocr-test-") as tmp:
            source=Path(tmp)/"scan.png"
            canvas=Image.new("RGB",(1600,500),"white")
            draw=ImageDraw.Draw(canvas)
            font=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",48)
            draw.text((60,70),"PART NUMBER     DESCRIPTION",fill="black",font=font)
            draw.text((60,160),"AB12345         Water valve",fill="black",font=font)
            canvas.save(source)
            with pymupdf.open() as scan:
                page=scan.new_page(width=800,height=250)
                page.insert_image(page.rect,filename=str(source))
                assert not page.get_text("words")
                rows,metrics=adaptive_page(page,1,"adaptive-table-v3")
                assert not rows and metrics["failure_class"]=="image_only"
                preview=ocr_preview(page,1)
                assert preview["status"]=="unverified",preview
                assert preview["independent_status"]=="completed",preview
                assert all("bbox_px" in row and row["page"]==1 for row in preview["candidates"])
                assert not rows  # Explicit non-publication invariant.
    # Cached host policy must still evaluate every URL independently.
    policy=urllib.robotparser.RobotFileParser()
    policy.parse(["User-agent: *","Disallow: /private"])
    ROBOTS_CACHE["www.winnebago.com"]=(time.monotonic(),policy,False)
    robots_check("https://www.winnebago.com/public.pdf")
    try:
        robots_check("https://www.winnebago.com/private/file.pdf")
        raise AssertionError("cached policy allowed disallowed path")
    except Held:
        pass
    ROBOTS_CACHE.clear()
    attempts=[]
    def transient(action,args):
        attempts.append(action)
        if len(attempts)==1:
            raise urllib.error.HTTPError("https://example.invalid",502,"gateway",{},None)
        return 3
    assert finish_with_recovery("finish",{},transient,lambda _:None)==3
    assert attempts==["finish","finish"]
    def unavailable(action,args):
        raise TimeoutError()
    assert finish_with_recovery("finish",{},unavailable,lambda _:None) is None
    print("self-test passed")


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        self_test()
    elif "--discovery-only" in sys.argv:
        discover_repositories()
    elif "--manifest-only" in sys.argv:
        main("manifest")
    elif "--batch-only" in sys.argv:
        main("batch")
    else:
        discover_repositories()
        main()
        # Secondary parser is optional diagnostics, not a publication prerequisite.
