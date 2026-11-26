import json, hashlib, re, pymupdf
import sys; pdf=sys.argv[1]; sha=hashlib.sha256(open(pdf,'rb').read()).hexdigest()
P=[]  # (page, number, description)
def pump(pg, oem, aft, name):
    P.append((pg, oem, f"{name} (OEM)" if aft else name))
    if aft: P.append((pg, aft, f"{name} (aftermarket version of {oem})"))
pump(6,'4008-101-A65','4008-101-E65','Revolution 4008 fresh water pump, 12 VDC, 3 GPM, 55 PSI')
pump(6,'4008-131-A65','4008-131-E65','Revolution 4008 fresh water pump, 24 VDC, 3 GPM, 55 PSI')
pump(6,'4028-100-A54','4028-100-E54','Revolution 4028 fresh water pump, 12 VDC, 2.3 GPM, 50 PSI')
pump(6,'4008-171-A65','4008-171-E65','Revolution 4008 fresh water pump, 115 VAC, 3 GPM, 55 PSI')
pump(7,'4048-153-A75','4048-153-E75','4048 High Flow fresh water pump, 12 VDC, 4 GPM, 55 PSI')
pump(7,'105-003','105-013','SLV single fixture automatic demand pump, 12 VDC, 1 GPM, 30 PSI')
pump(8,'3200-200','3200-201','Macerator pump, 12 VDC, 10 GPM')
pump(8,'3200-001',None,'Macerator pump, 12 VDC, 13 GPM')
pump(8,'8050-305-526',None,'Standard general purpose pump, 12 VDC, 1.5 GPM')
pump(8,'8050-305-626',None,'Premium general purpose pump, 12 VDC, 1.5 GPM, 8 ft cable with battery clips')
pump(8,'8050-305-426',None,'Oil change / winterizing system, 12 VDC, 1.5 GPM')
pump(9,'255-213','255-313','Twist-on water strainer, 50 mesh, 1/2" pipe inlet')
pump(9,'255-223','255-323','Twist-on water strainer, 50 mesh, 1/2" barb inlet')
pump(9,'255-215','255-315','Swivel nut water strainer, 50 mesh, 1/2" pipe inlet')
pump(9,'255-225','255-325','Swivel nut water strainer, 50 mesh, 1/2" barb inlet')
P.append((9,'94-591-01','Pump silencing kit (includes 2 of 411-030-00 and 1/2" male pipe couplers) (aftermarket)'))
P.append((9,'411-010-00','Pump silencing riser, single 18" with 1/2" female swivel fittings'))
P.append((9,'411-020-00','Pump silencing riser, single 30" with 1/2" female swivel fittings'))
P.append((9,'411-030-00','Pump silencing riser, single 36" with 1/2" female swivel fittings'))
pump(9,'340-000','340-001','In-line check valve, 3/4" barb, to 100 PSI')
P.append((9,'94-010-00','Hose spray nozzle, 3/4" female garden hose thread (aftermarket)'))
pump(10,'182-100','182-200','Pre-pressurized accumulator tank, 24 oz nylon, 1/2" NPSM male, 125 PSI')
P.append((10,'3400-002','Pre-pressurized accumulator tank, 2 gallon stainless steel, 1/2" NPT female, 100 PSI'))
pump(10,'183-020-14','183-029-14','Pressure reducing city water entry, wall mount, 65 PSI, chrome')
pump(10,'183-020-16','183-029-16','Pressure reducing city water entry, wall mount, 65 PSI, black')
pump(10,'183-020-18','183-029-18','Pressure reducing city water entry, wall mount, 65 PSI, gel white')
P.append((10,'183-039-08','Pressure reducing city water entry, in-line, 50 PSI, gel white (aftermarket)'))
pump(10,'94-009-00','94-009-10','Electric faucet with switch, 12 VDC, 3/8" barb, white')
P.append((10,'94-009-01','Electric faucet with switch, 12 VDC, 3/8" barb, gray'))
P.append((10,'15-045-02','Single touch faucet, 1/4" port, chrome'))
pump(10,'94-009-32','94-009-12','Faucet without switch, 3/8" barb, white')
for n,d in [('155110-43','Pentair GAC 5" cartridge, granular activated carbon, 20 micron'),('155022-43','Pentair C-2 5" cartridge, carbon wrapped paper, 5 micron'),
            ('155014-43','Pentair P5 10" cartridge, spun polypropylene sediment, 5 micron'),('155002-43','Pentair C1 10" cartridge, carbon wrapped paper, 5 micron'),
            ('155155-43','Pentair CC-10 10" cartridge, granular activated carbon, 20 micron'),('255679-43','Pentair CFBC-10 10" cartridge, modified carbon block, 0.5 micron')]:
    P.append((11,n,d))
for n,d in [('255800-43','Pentair UDS-10EX1 10" cartridge, KDF/carbon, 5 micron'),('255521-43','10" in-line filter, GAC, 1/4" NPT female ports'),
            ('255525-43','10" in-line filter, GAC, 1/4" quick connect ports'),('RV-210GH-A','City water entry in-line filter, activated carbon, 3/4" garden hose ports'),
            ('RV-210GH-KDF-A','City water entry in-line filter, KDF/carbon, 3/4" garden hose ports'),('94-009-50','10" in-line interior filter, KDF/carbon, 1/4" NPT female, fittings included'),
            ('255681-43','Pentair CFB-PB10 10" cartridge, modified carbon block, 0.5 micron')]:
    P.append((12,n,d))
for n,d in [('EV959206','Everpure Full-Timer filter, Micro-Pure pleated, 0.5 micron'),('EV959207','Everpure Part-Timer filter, carbon block, 0.5 micron, twin pack'),
            ('244454','In-line filter bracket for 10" in-line filter housings'),('94-178-09','O-ring kit, 10-pack, for 10" Waterguard filter housing (RV-10UC-A)'),
            ('158196','Slim-line filter housing, 10", 1/2" female ports'),('158195','Slim-line filter housing, 10", 1/2" female ports, with pressure relief'),
            ('150539','SW-1A slim-line filter housing wrench'),('244047','Slim-line filter housing mounting bracket kit with screws'),
            ('151121','O-ring kit, single pack, for 10" slim-line filter housing'),('RV-10UC-A','Complete 10" filter housing with C1 filter, wrench, bracket kit, garden hose fittings'),
            ('EV925200','Everpure filtration system with POP display carton (2 complete EV925205 systems)'),('EV925205','Everpure complete kit: EV959206 filter, housing, by-pass, installation kit')]:
    P.append((13,n,d))
for n,d in [('244-2916','Straight fitting, wingnut swivel, nylon, 1/2"-14 NPT (F) x 3/8" barb'),('244-2926','Straight fitting, wingnut swivel, nylon, 1/2"-14 NPT (F) x 1/2" barb'),
            ('244-2936','Straight fitting, wingnut swivel, nylon, 1/2"-14 NPT (F) x 5/8" barb'),('244-2946','Straight fitting, wingnut swivel, nylon, 1/2"-14 NPT (F) x 3/4" barb'),
            ('244-5146','Straight fitting adapter, nylon, 1/2" NPT (M) x 3/4" barb'),('244-3366','Elbow fitting, wingnut swivel, nylon, 1/2"-14 NPT (F) x 1/2"-14 NPT (M)'),
            ('244-3916','Elbow fitting, wingnut swivel, nylon, 1/2"-14 NPT (F) x 3/8" barb'),('244-3926','Elbow fitting, wingnut swivel, nylon, 1/2"-14 NPT (F) x 1/2" barb'),
            ('244-3936','Elbow fitting, wingnut swivel, nylon, 1/2"-14 NPT (F) x 5/8" barb'),('244-3946','Elbow fitting, wingnut swivel, nylon, 1/2"-14 NPT (F) x 3/4" barb'),
            ('244-2356','Garden hose wingnut fitting, nylon, 3/4" GHT (M) x 1/2" NPT (F)'),('244-2866','Swivel straight fitting adapter (pump/accumulator), nylon, 1/2" NPT (F) x 1/2" NPT (F)'),
            ('244-4522','Barb tee, polypropylene, 1/2" barb x 1/2" barb x 1/2" barb')]:
    P.append((14,n,d))
# repair kits (pages 15-18): column order as printed
kits={}
def kitrow(pg, series, pumps, cols, nums):
    for c,n in zip(cols,nums):
        if n=='N/A': continue
        kits.setdefault(n,{'page':pg,'types':[], 'pumps':[]})
        if c not in kits[n]['types']: kits[n]['types'].append(c)
        kits[n]['pumps'] += [p for p in pumps if p not in kits[n]['pumps']]
C1=['upper housing','valve assembly','drive assembly','motor','pump head kit','check valve']
kitrow(15,'2088/2093',['2088-422-144','2088-422-444'],C1,['94-231-20','94-232-06','94-238-03','94-11-261-00','94-236-21','94-237-00'])
kitrow(15,'2088/2093',['2093-204-113','2093-204-413'],C1,['94-231-24','94-232-06','94-238-05','94-11-192-00','94-236-05','94-237-00'])
kitrow(15,'2088/2093',['2088-473-143','2088-473-443'],C1,['94-231-24','94-232-03','94-238-04','94-11-142-10','94-236-08','94-237-00'])
kitrow(15,'2088/2093',['2088-492-144','2088-492-444'],C1,['94-231-20','94-232-04','94-238-03','94-11-150-10','94-236-21','94-237-00'])
kitrow(15,'2088/2093',['2088-453-444'],C1,['94-231-20','94-232-06','94-238-04','94-11-173-01','94-236-08','94-237-00'])
C2=['upper housing','valve assembly','drive assembly','motor','pump head','pump head kit','switch']
kitrow(15,'4008/4028',['4008-101-A65','4008-101-E65'],C2,['94-800-00','94-800-01','94-800-02','94-11-302-00','94-800-04','94-800-03','94-800-05'])
kitrow(15,'4008/4028',['4008-131-A65','4008-131-E65'],C2,['94-800-00','94-800-01','94-800-02','94-11-303-00','94-800-04','94-800-03','94-800-05'])
kitrow(15,'4008/4028',['4028-100-A54','4028-100-E54'],C2,['94-802-00','94-800-01','94-802-02','94-11-302-00','94-800-14','94-800-03','94-802-06'])
kitrow(15,'4008/4028',['4008-171-A65','4008-171-E65'],C2,['94-800-00','94-800-01','94-800-02','94-11-306-00','94-800-04','94-800-03','94-800-05'])
kitrow(16,'4048',['4048-153-A75','4048-153-E75'],['switch','upper housing','valve assembly','drive assembly','motor','pump head kit','check valve'],
       ['94-801-05','94-801-01','94-800-01','94-801-02','94-71-001-07','94-801-04','94-800-03'])
kitrow(16,'8050',['8050-305-xxx utility pumps'],['pump head','switch','check valve','upper housing','valve assembly','drive assembly'],['N/A','N/A','N/A','N/A','94-391-12','94-385-42'])
kitrow(17,'4900',['4900-0201','4900-0211'],['switch','upper housing','valve assembly','drive assembly','motor'],['N/A','94-670-01','94-669-00','94-670-00','N/A'])
kitrow(17,'5900',['5900-0201','5900-0211'],['switch','upper housing','valve assembly','drive assembly','motor'],['N/A','94-670-02','94-030-01','94-030-02','N/A'])
kitrow(18,'3200',['3200-200','3200-201','3200-001'],['impeller kit','impeller housing kit','blade kit','lip seal kit'],['94-571-00','94-570-00','94-570-02','94-570-04'])
for n,k in kits.items():
    t='/'.join(k['types']); t=t[0].upper()+t[1:]
    P.append((k['page'], n, f"{t} repair kit for Shurflo pumps {', '.join(k['pumps'])}"))
# check every number against the PDF text layer
d=pymupdf.open(pdf); txt={i+1:d[i].get_text() for i in range(d.page_count)}
miss=[(p,n) for p,n,_ in P if n not in txt[p]]
seen=set(); lines=[]; cnt={}
for p,n,desc in P:
    if n in seen: continue
    seen.add(n); cnt[p]=cnt.get(p,0)+1; lines.append(f"{p}|{cnt[p]}|{n}|{desc.replace('|','/')}|0")
out={"doc":sha,"pages":d.page_count,"agree":not miss,"diffs":miss,"rows_total":len(P),"numbers":len(seen),"sections":{"0":"Shurflo RV product catalog"},"rows":"\n".join(lines)}
json.dump(out,open('shurflo_cat.json','w'),ensure_ascii=False)
# compare with automated layout pass numbers
import subprocess
auto=set(l.split("'")[1] for l in subprocess.run(['python3','shurflo_cat.py',pdf],capture_output=True,text=True).stdout.splitlines() if "'" in l)
auto|=set(re.findall(r"'([^']+)'\)", ''))
print('rows',len(lines),'missing in text layer:',miss)
print('auto pass numbers (pp6-14) not in transcription:', sorted(x for x in auto if x not in seen))
