"""Evidence-first relationship extraction from RV catalogues.

Runs in the SAME PyMuPDF page traversal as identity extraction. Only explicit
statements with a local, unambiguous subject become staged candidates. No
manufacturer-OEM verification or interchangeability is inferred from fitment.
"""
from __future__ import annotations
import hashlib
import re

CODE = r"[A-Z0-9][A-Z0-9./-]{3,24}"
SKU = re.compile(r"(?<!\w)(\d{5,7})(?!\w)")
MAKER = re.compile(r"\b(?:Dometic|Thetford|Truma|AL-KO|Lippert|Fiamma|Carbest|Reimo|Camp4|Alde|Thule|Jokon|REMIS|Knott|Hella)\b", re.I)
REPLACE = re.compile(
    r"\b("+CODE+r")\s+(?:wird\s+)?(?:ersetzt\s+durch|ersetzt\s+von|nachfolger(?:artikel)?\s*(?:ist|:)?|superseded\s+by|replaced\s+by)\s+("+CODE+r")\b", re.I)
REPLACE_PREFIX = re.compile(
    r"\b(?:alte?\s+(?:art(?:ikel)?[- .]?(?:nr|nummer)|teilenummer)|old\s+part\s+number)\s*[:#.]?\s*("+CODE+r")\s*(?:→|->)\s*(?:neue?\s+(?:art(?:ikel)?[- .]?(?:nr|nummer)|teilenummer)|new\s+part\s+number)?\s*("+CODE+r")\b", re.I)
SUITABLE = re.compile(
    r"\b(?:passend\s+für|geeignet\s+für|kompatibel\s+mit|fits?\s+(?:models?|for)|suitable\s+for)\s*[:\-]?\s*(.{4,150})",re.I)
OEM = re.compile(
    r"\b(?:hersteller\s*[- .]?\s*(?:nr|nummer)|oem\s*[- .]?\s*(?:nr|number|no)|original\s*[- .]?\s*(?:nr|nummer|number)|manufacturer\s*[- .]?\s*(?:number|no))\s*[:#.]?\s*("+CODE+r")\b",re.I)
REIMO = re.compile(r"\b(?:reimo\s+)?(?:art(?:ikel)?\s*[- .]?\s*(?:nr|nummer)|bestell\s*[- .]?\s*(?:nr|nummer)|item\s*(?:number|no))\s*[:#.]?\s*(\d{5,7})\b",re.I)
QUALIFIED = re.compile(r"\b(?:nicht|not|außer|except|nur\s+mit|only\s+with|keine\s+garantie|nicht\s+passend)\b",re.I)

def _blocks(page):
    for block in page.get_text("dict")["blocks"]:
        if "lines" not in block:continue
        for line in block["lines"]:
            t=" ".join(" ".join(span.get("text","") for span in line["spans"]).split())
            if t:
                yield t,line["bbox"]
def _candidate(page,p,kind,subject,obj,statement,bbox,maker=None,certainty="explicit",method=""):
    if not 3<=len(subject)<=100 or not 3<=len(obj)<=150 or subject.casefold()==obj.casefold():return None
    if not statement or len(statement)>250:return None
    return {"page":p,"kind":kind,"subject":subject,"object":obj,
            "statement":statement,"position":f"x{round(bbox[0])} y{round(bbox[1])}",
            "manufacturer":maker or "","certainty":certainty,"method":method,
            "page_text_sha256":hashlib.sha256(page.get_text("text").encode()).hexdigest()}


# Playbook WO-3: PDF x-position table evidence, kept as UNREVIEWED distributor
# assertions. A column association is a catalogue claim, NOT OEM verification.
LOCAL_HEADER = re.compile(r"^(?:reimo\s+)?(?:art(?:ikel)?[.\s-]?(?:nr|nummer)|bestell[.\s-]?(?:nr|nummer)|item[.\s-]?(?:no|number))\.?$", re.I)
CROSSREF_HEADER = re.compile(r"^(?:(?:hersteller|original|oem)[.\s-]?(?:nr|nummer|number|no|ref(?:erence)?)|oem|original)\.?$", re.I)
CROSSREF_CODE = re.compile(r"^[A-Z0-9][A-Z0-9./-]{3,24}$",re.I)

def _column_crossrefs(page, page_number, authority):
    """Extract explicitly labelled SKU/OEM table rows by PDF column geometry.

    Constrain candidates to a labelled two-column table, a single exact
    subject and OEM target in the same y-band, and an unqualified statement.
    Reject ambiguous text, multiple numbers, multi-line pairings and jumps
    outside each table. No cross-reference is promoted by this function.
    """
    if authority != "distributor":
        return []
    words = sorted(page.get_text("words"), key=lambda w: (round(w[1] / 3), w[0]))
    rows = []
    for w in words:
        if not rows or abs(w[1] - rows[-1][0]) > 3:
            rows.append((w[1], [w]))
        else:
            rows[-1][1].append(w)
    lines = []
    for y, row in rows:
        ws = sorted(row, key=lambda w: w[0])
        cells = []
        for w in ws:
            if not cells or w[0] - cells[-1][-1][2] > 20:
                cells.append([w])
            else:
                cells[-1].append(w)
        lines.append((y, ws, [(" ".join(x[4] for x in cell), cell[0][0], cell[-1][2])
                              for cell in cells]))
    output = []
    for index, (hy, hw, hc) in enumerate(lines):
        local = [(text,x0,x1) for text,x0,x1 in hc if LOCAL_HEADER.fullmatch(text.strip())]
        target = [(text,x0,x1) for text,x0,x1 in hc if CROSSREF_HEADER.fullmatch(text.strip())]
        if len(local) != 1 or len(target) != 1:
            continue
        _, lx0, lx1 = local[0]
        _, rx0, rx1 = target[0]
        if rx0 - lx1 < 35 or rx0 - lx0 > 650:
            continue
        boundary = (lx1 + rx0) / 2
        previous_y = hy
        for y, ws, cells in lines[index+1:]:
            if y - hy > 370 or y - previous_y > 37:
                break
            previous_y = y
            # A new header or section terminates the table.
            if any(LOCAL_HEADER.fullmatch(c[0].strip()) or CROSSREF_HEADER.fullmatch(c[0].strip())
                   for c in cells):
                break
            left = [w[4].strip() for w in ws if w[0] < boundary and w[0] >= lx0 - 28]
            right = [w[4].strip() for w in ws if w[0] >= boundary and w[0] <= rx1 + 60]
            local_codes = list(dict.fromkeys(token for token in left if SKU.fullmatch(token)))
            oem_codes = list(dict.fromkeys(token for token in right
                               if CROSSREF_CODE.fullmatch(token)
                               and any(ch.isdigit() for ch in token)))
            row_text = " ".join(w[4] for w in ws)
            if len(local_codes) != 1 or len(oem_codes) != 1 or QUALIFIED.search(row_text):
                continue
            local_code, target_code = local_codes[0], oem_codes[0]
            if local_code == target_code or len(row_text) > 200:
                continue
            # Avoid interpreting a table of model numbers as OEM crossrefs:
            # both explicitly named columns are mandatory on the same header.
            makers = {m.group(0) for m in MAKER.finditer(" ".join(x[0] for x in hc))
                      if m.group(0).lower() != "reimo"}
            maker = next(iter(makers)) if len({m.lower() for m in makers}) == 1 else ""
            statement = f"{local[0][0]} | {target[0][0]} : {local_code} | {target_code}"
            bbox = (lx0, y, rx1, y + 10)
            c = _candidate(page, page_number, "distributor_manufacturer_crossref",
                           local_code, target_code, statement, bbox, maker=maker,
                           certainty="column_aligned_unreviewed",
                           method="explicit-sku-oem-columns-v1")
            if c: output.append(c)
    return output

def extract_page(page,p,identity_rows=(),authority="distributor"):
    """Returns staged supersession, fitment and Reimo-SKU/OEM candidates.

    For fitment a unique catalogue article must occur in the same text block,
    or on an immediately adjacent text line (<=45 PDF units). This avoids
    attaching all model mentions on a catalogue page to an arbitrary SKU.
    """
    lines=list(_blocks(page));out=[]
    sku_rows={str(r.get("number")):r for r in identity_rows if SKU.fullmatch(str(r.get("number","")))}
    for i,(t,box) in enumerate(lines):
        if len(t)>250:continue
        for pattern in (REPLACE,REPLACE_PREFIX):
            for m in pattern.finditer(t):
                a,b=m.groups()
                if not any(c.isdigit() for c in a+b):continue
                if QUALIFIED.search(t):continue
                if authority=="distributor":
                    kind="stated_replacement_unverified"
                else:
                    kind="manufacturer_supersession_candidate"
                c=_candidate(page,p,kind,a,b,t,box,method="explicit-directional-de-en-v1")
                if c:out.append(c)
        # Manufacturer OEM reference requires BOTH an explicit Reimo local SKU
        # and a labelled OEM number on the SAME textual line. This can under-
        # extract, but cannot make distributor numbers into manufacturer OEMs.
        reimo=REIMO.search(t);oem=OEM.search(t)
        if authority=="distributor" and reimo and oem and reimo[1]!=oem[1]:
            # Search the OEM-labelled suffix first. 'Reimo Art.Nr.' is
            # distributor provenance, not the OEM maker.
            makers=[m[0] for m in MAKER.finditer(t) if m[0].lower()!="reimo"]
            maker=makers[0] if len({m.lower() for m in makers})==1 else ""
            c=_candidate(page,p,"distributor_manufacturer_crossref",reimo[1],oem[1],t,box,
                maker=maker,method="explicit-sku-oem-label-v1")
            if c:out.append(c)
        suitable=SUITABLE.search(t)
        if not suitable:continue
        models=suitable[1].strip(" .;,:")
        if QUALIFIED.search(t) or len(models)>130 or len(models.split())>18:continue
        # Explicit local item-number label in same line wins.
        same=REIMO.search(t)
        if same:sku=same[1]
        else:
            skus=[s for s in SKU.findall(t[:suitable.start()]) if s in sku_rows]
            if len(set(skus))==1:sku=skus[0]
            else:
                # A unique SKU in the immediately previous line only, with
                # bounded vertical proximity and column alignment.
                sku=None
                if i>0:
                    prev,prevbox=lines[i-1]
                    prev_matches=[s for s in SKU.findall(prev) if s in sku_rows]
                    if len(set(prev_matches))==1 and len(prev_matches)==1 and 0<=box[1]-prevbox[3]<=45 and abs(box[0]-prevbox[0])<=60:
                        sku=prev_matches[0]
        if not sku:continue
        # Model names are retained as a single claimed scope; never split by
        # commas into alleged interchangeable part-number pairs.
        c=_candidate(page,p,"fits_model",sku,models,t,box,
            method="explicit-fitment-de-en-v1")
        if c:out.append(c)
    # Many visual catalogue cards put a product code and "passend für"
    # text in different PDF blocks. The identity extractor may have already
    # associated that text with an article. Preserve this as an UNREVIEWED
    # observation rather than discarding it or calling it verified fitment.
    # Demand a named product ecosystem/model; generic "fits all" is not useful.
    model_marker = re.compile(
        r"\b(?:AL-KO|Truma|Thetford|Dometic|Trelino|Froli|Gardena|"
        r"Inprojal|Berker|UFS(?:connect)?|CAP\s*\d|A\d{6,}|"
        r"Fiamma|Fiat|Ducato|VW|Volkswagen|Renault|Ford|Mercedes|"
        r"Stabilform|Alde|Carbest|Thule|Jokon|REMIS)\b", re.I)
    for row in identity_rows:
        sku=str(row.get("number",""))
        desc=str(row.get("description") or "").strip()
        m=SUITABLE.search(desc)
        if not SKU.fullmatch(sku) or not m or not model_marker.search(m[1]):continue
        if QUALIFIED.search(desc):continue
        scope=m[1].strip(" .;,:")
        if not 4<=len(scope)<=130:continue
        source_pos=row.get("position","")
        position=re.fullmatch(r"x(\d+) y(\d+)",source_pos)
        if not position:continue
        box=(int(position[1]),int(position[2]),int(position[1])+20,int(position[2])+10)
        c=_candidate(page,p,"fits_model",sku,scope,desc,box,
            certainty="sku_description_alignment_unreviewed",
            method="identity-associated-fitment-v2")
        if c:out.append(c)
    out.extend(_column_crossrefs(page, p, authority))
    seen=set();unique=[]
    for r in out:
        k=(r["page"],r["kind"],r["subject"],r["object"],r["position"])
        if k not in seen:seen.add(k);unique.append(r)
    return unique

def self_test():
    import pymupdf
    def page(lines):
        doc=pymupdf.open();p=doc.new_page()
        for i,t in enumerate(lines):p.insert_text((40,55+i*23),t)
        return doc,p
    doc,p=page(["Art.Nr. 318019 passend fuer Truma S3004"])
    # PDF test uses ASCII transliteration; source grammar is Unicode "für".
    assert extract_page(p,1,[{"number":"318019"}])==[]
    doc.close()
    doc,p=page(["Art.Nr. 318019 passend für Truma S3004"])
    fit=extract_page(p,1,[{"number":"318019"}])
    assert len(fit)==1 and fit[0]["kind"]=="fits_model" and fit[0]["subject"]=="318019",fit
    doc.close()
    doc,p=page(["Artikel 318019 wird ersetzt durch 318020"])
    x=extract_page(p,1)
    assert len(x)==1 and x[0]["kind"]=="stated_replacement_unverified"
    assert x[0]["object"]=="318020"
    doc.close()
    doc,p=page(["Reimo Art.Nr. 318019 Hersteller-Nr. 270.99S Dometic"])
    x=extract_page(p,1)
    assert len(x)==1 and x[0]["kind"]=="distributor_manufacturer_crossref",x
    assert x[0]["manufacturer"].lower()=="dometic",x
    doc.close()
    doc,p=page(["318019 318020 318021 passend für Truma S3004"])
    assert not extract_page(p,1,[{"number":"318019"},{"number":"318020"},{"number":"318021"}])
    doc.close()
    doc,p=page(["Das ist nur mit Adapter passend für Truma S3004"])
    assert not extract_page(p,1,[{"number":"318019"}])
    doc.close()
    doc,p=page(["Adapter fuer AL-KO"])
    x=extract_page(p,1,[{"number":"91359","position":"x90 y50",
       "description":"Passend für AL-KO Steckstützen Stabilform und Premium."}])
    assert len(x)==1 and x[0]["kind"]=="fits_model" and x[0]["certainty"]=="sku_description_alignment_unreviewed",x
    assert not extract_page(p,1,[{"number":"930681","position":"x90 y50",
       "description":"Geeignet für Boote, Luftzelte und Möbel."}])
    doc.close()

    # Explicit header and x-aligned table rows qualify for STAGING only.
    doc=pymupdf.open();p=doc.new_page()
    p.insert_text((45,75),"Art.-Nr.")
    p.insert_text((270,75),"Hersteller-Nr.")
    p.insert_text((45,100),"318019")
    p.insert_text((270,100),"270.99S")
    p.insert_text((45,125),"318020")
    p.insert_text((270,125),"270.99T")
    rel=extract_page(p,1,[],authority="distributor")
    assert len(rel)==2 and all(r["kind"]=="distributor_manufacturer_crossref" and r["certainty"]=="column_aligned_unreviewed" for r in rel),rel
    assert {(x["subject"],x["object"]) for x in rel}=={("318019","270.99S"),("318020","270.99T")},rel
    assert not extract_page(p,1,[],authority="manufacturer")
    doc.close()
    # No column heading -> no inference from neighbouring numbers.
    doc=pymupdf.open();p=doc.new_page()
    p.insert_text((45,75),"Part Number")
    p.insert_text((270,75),"Description")
    p.insert_text((45,100),"318019")
    p.insert_text((270,100),"270.99S")
    assert not extract_page(p,1,[],authority="distributor")
    doc.close()
    return True

if __name__=="__main__":
    self_test()
    print("catalogue relationship extractor: tests passed")
