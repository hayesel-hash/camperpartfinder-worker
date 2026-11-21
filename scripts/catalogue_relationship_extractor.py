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
    return True

if __name__=="__main__":
    self_test()
    print("catalogue relationship extractor: tests passed")
