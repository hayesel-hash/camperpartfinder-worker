"""Dedicated Reimo Zubehoerprofi catalogue extractor (distributor identities only).

The upstream Reimo PDF is processed remotely by the existing leased GitHub disk
worker. No local catalogue mirror or unauthorised manufacturer OEM attribution.
Product descriptions are included only when spatially supported by page text.
"""
from __future__ import annotations
import re

ITEM = re.compile(r"(?<![A-Za-z0-9])([0-9]{5,7})(?![A-Za-z0-9])")
LABEL = re.compile(r"^(?:art\.?\s*-?\s*nr\.?|artikel(?:nr\.?|nummer)?|bestell(?:nr\.?|nummer)|item\s*(?:no\.?|number))$",re.I)
BAD = re.compile(r"^(?:preis|price|eur|euro|inkl|exkl|mwst|uvp|seite|page|abb\.?|bild|gewicht|länge|breite|höhe|maß|masse|maße|abmessung|größe|colour|farbe|variante|ausführung|nr\.?|art\.?\s*-?\s*nr\.?)\b",re.I)
DIM = re.compile(r"^(?:\d+(?:[.,]\d+)?\s*(?:mm|cm|m|kg|g|w|v|ah|l|ml)|\d+\s*[x×]\s*\d+|\d{4})$",re.I)
PRICE = re.compile(r"^(?:\d{1,4}[.,]\d{2}|\d{1,4},[-–]|€\s*\d+|\d+\s*€)$")
ALPHA = re.compile(r"[A-Za-zÄÖÜäöüß]{3}")
WORD = re.compile(r"\S+")


def _lines(page):
    """PyMuPDF words grouped by original block and visual baseline."""
    words=page.get_text("words")
    groups={}
    for w in words:
        groups.setdefault((w[5],w[6]),[]).append(w)
    lines=[]
    for (block,lineno),ws in groups.items():
        ws.sort(key=lambda w:w[0])
        lines.append({"block":block,"line":lineno,"words":ws,
                      "text":" ".join(w[4] for w in ws),
                      "x0":min(w[0] for w in ws),"x1":max(w[2] for w in ws),
                      "y0":min(w[1] for w in ws),"y1":max(w[3] for w in ws)})
    return sorted(lines,key=lambda x:(x["y0"],x["x0"]))


def _clean_description(text):
    text=" ".join(text.strip(" |:;-").split())
    if not 6<=len(text)<=160 or not ALPHA.search(text) or BAD.match(text):
        return ""
    if PRICE.fullmatch(text) or DIM.fullmatch(text) or re.fullmatch(r"[\d.,€\s\-–/]+",text):
        return ""
    # Reject prose that is more likely legal copy, marketing or a section title.
    if len(text.split())>17 or re.search(r"\b(?:www\.|https?://|copyright|telefon|telefonnummer|lieferbedingungen)\b",text,re.I):
        return ""
    return text


def _explicit_codes(lines,p):
    """Require an explicit item-number label in the same visual line/block."""
    out=[]
    for line in lines:
        ws=line["words"]
        for i,w in enumerate(ws):
            num=w[4].strip(".,:;")
            if not ITEM.fullmatch(num):continue
            prefix=" ".join(x[4] for x in ws[max(0,i-3):i]).rstrip(":")
            if not LABEL.fullmatch(prefix):continue
            suffix=" ".join(x[4] for x in ws[i+1:])
            desc=_clean_description(suffix)
            out.append({"page":p,"number":num,"position":f"x{round(w[0])} y{round(w[1])}",
                        "method":"reimo-explicit-article-v2",
                        **({"description":desc} if desc else {})})
    return out


def _description_for(line,lines):
    """Strict local association: same block or nearby, aligned product heading.

    A number-only row remains number-only if the PDF does not justify a
    particular description. This is safer than inventing an association.
    """
    text=line["text"]
    # Same line: product text before SKU, without price, other SKUs or dimensions.
    for code in ITEM.finditer(text):
        prefix=text[:code.start()].strip()
        prefix=re.sub(r"^(?:art\.?\s*-?\s*nr\.?|artikelnummer|bestellnummer)\s*:?\s*","",prefix,flags=re.I)
        prefix=_clean_description(prefix)
        if prefix and not ITEM.search(prefix):
            return prefix
    candidates=[]
    for other in lines:
        if other is line:continue
        dy=line["y0"]-other["y1"]
        if not -4<=dy<=33:continue
        if other["block"]!=line["block"] and abs(other["x0"]-line["x0"])>45:continue
        if other["x0"]>line["x1"]+30 or other["x1"]<line["x0"]-80:continue
        if ITEM.search(other["text"]) or PRICE.search(other["text"]):continue
        desc=_clean_description(other["text"])
        if desc:
            candidates.append((abs(dy)+abs(other["x0"]-line["x0"])*0.1,desc))
    candidates.sort()
    # Require a unique, clearly closest heading.
    if candidates and (len(candidates)==1 or candidates[1][0]-candidates[0][0]>9):
        return candidates[0][1]
    return ""


def extract_page(page,p,baseline_rows=()):
    """Combine existing SKU candidates with explicitly labelled rows.

    Distinguish catalogue product identity from manufacturer OEM identity;
    return page, number, position, method and only evidenced description.
    """
    lines=_lines(page)
    explicit=_explicit_codes(lines,p)
    existing=list(baseline_rows)
    combined=explicit+existing
    out=[]
    seen=set()
    for row in combined:
        num=row.get("number","")
        if not ITEM.fullmatch(num):continue
        key=(num,row.get("position",""))
        if key in seen:continue
        seen.add(key)
        copy=dict(row)
        if not copy.get("description"):
            m=re.match(r"x(\d+) y(\d+)",row.get("position",""))
            if m:
                x,y=map(int,m.groups())
                nearest=sorted((l for l in lines if abs(l["y0"]-y)<6 and any(w[4].strip(".,:;")==num and abs(w[0]-x)<10 for w in l["words"])),
                               key=lambda l:abs(l["x0"]-x))
                if nearest:
                    desc=_description_for(nearest[0],lines)
                    if desc:copy["description"]=desc
        copy["catalogue_identity_authority"]="distributor"
        out.append(copy)
    return out


def self_test():
    import pymupdf
    with pymupdf.open() as doc:
        p=doc.new_page()
        p.insert_text((40,40),"REIMO Wohnmobil Fenster")
        p.insert_text((40,80),"Carbest Ausstellfenster 500x450")
        p.insert_text((40,98),"Art.-Nr. 318019")
        p.insert_text((40,130),"Art.-Nr. 318031")
        p.insert_text((40,170),"Maße 800x500 2025 498 Euro")
        rows=extract_page(p,1,[{"page":1,"number":"318019","position":"x85 y89","method":"reimo-catalogue-sku-v1"}])
        assert any(x["number"]=="318019" for x in rows),rows
        assert all(x["catalogue_identity_authority"]=="distributor" for x in rows)
        assert not any(x["number"]=="2025" for x in rows)
        assert not any(x["number"]=="800500" for x in rows)
        assert not any(x["description"]=="Maße 800x500 2025 498 Euro" for x in rows if "description" in x)
        assert not extract_page(doc.new_page(),2)
        p=doc[0]  # PyMuPDF invalidates prior page handles when pages are inserted.
        # Repeated SKUs in the same position should not be duplicated.
        r=extract_page(p,1,[{"page":1,"number":"318019","position":"x80 y89","method":"reimo-catalogue-sku-v1"}])
        assert sum(x["number"]=="318019" for x in r)>=1
    return True

if __name__=="__main__":
    self_test()
    print("Reimo dedicated extractor: synthetic tests passed")
