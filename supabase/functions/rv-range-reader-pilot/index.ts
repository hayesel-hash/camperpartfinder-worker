// CamperMatch controlled independent HTTP Range pilot. Raw pages only.
// Do not automatically publish from a byte-range document; its original
// document SHA256 is NOT independently verified.
import {getResolvedPDFJS} from "https://esm.sh/unpdf@0.12.1";
import {allows,rulesFor} from "./robots.ts";
const base=Deno.env.get("SUPABASE_URL")||"";
const service=Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")||"";
const agent="CamperPartMatchBot/1.0";
const json=(o:unknown,status=200)=>new Response(JSON.stringify(o),{status,headers:{"content-type":"application/json","cache-control":"no-store"}});
async function rpc(name:string,args:unknown){
 const r=await fetch(base+"/rest/v1/rpc/"+name,{method:"POST",headers:{apikey:service,authorization:"Bearer "+service,"content-type":"application/json"},
 body:JSON.stringify(args),signal:AbortSignal.timeout(24000)});
 if(!r.ok)throw Error("database "+name+" HTTP "+r.status);
 return r.json();
}
function urlCheck(value:string){
 const u=new URL(value);
 if(u.protocol!=="https:"||u.username||u.password||u.port||u.hash||
   !/^[a-z0-9.-]+\.[a-z]{2,}$/i.test(u.hostname)||/^[0-9.]+$/.test(u.hostname))
  throw Error("unapproved origin");
 return u;
}
async function checkRobots(u:URL){
 const r=await fetch(u.origin+"/robots.txt",{redirect:"manual",headers:{"user-agent":agent},signal:AbortSignal.timeout(17000)});
 if(r.status===404||r.status===410)return 1500;
 if(!r.ok)throw Error("robots HTTP "+r.status);
 if(Number(r.headers.get("content-length")||0)>512000)throw Error("robots oversized");
 const txt=(await r.text()).slice(0,512000);
 if(/^\s*<!doctype|^\s*<html/i.test(txt))throw Error("robots returned HTML");
 if(!allows(rulesFor(txt,["camperpartmatchbot","*"]),u.pathname+u.search))throw Error("robots disallows file");
 const delays=[...txt.matchAll(/^\s*crawl-delay\s*:\s*([0-9.]+)\s*$/gim)].map(x=>Number(x[1]));
 if(delays.some(x=>x>30))throw Error("robots slow-host disallowed in pilot");
 return Math.max(1500,...delays.map(x=>Math.ceil(x*1000)));
}
async function process(job:any){
 const started=Date.now(),u=urlCheck(job.url);
 const minGap=await checkRobots(u);
 let count=0,received=0,prior=0;
 let serial=Promise.resolve();
 function getRange(start:number,end:number):Promise<{data:Uint8Array,header:string}>{
  const pending=serial.then(async()=>{
   const delay=prior+minGap-Date.now();
   if(delay>0)await new Promise(resolve=>setTimeout(resolve,delay));
   prior=Date.now();
   if(Date.now()-started>245000)throw Error("reader deadline");
   const r=await fetch(u.href,{redirect:"manual",headers:{"user-agent":agent,range:"bytes="+start+"-"+end},
     signal:AbortSignal.timeout(28000)});
   if(r.status!==206)throw Error("HTTP Range unavailable: "+r.status);
   const header=r.headers.get("content-range")||"";
   if(!header.startsWith("bytes "+start+"-"))throw Error("Content-Range mismatch");
   const data=new Uint8Array(await r.arrayBuffer());
   if(data.byteLength!==end-start+1)throw Error("short range response");
   count++;received+=data.length;
   return {data,header};
  });
  serial=pending.then(()=>undefined,()=>undefined);
  return pending;
 }
 const first=await getRange(0,1023);
 if(new TextDecoder().decode(first.data.slice(0,5))!=="%PDF-")throw Error("invalid PDF signature");
 const total=Number(first.header.match(/\/(\d+)$/)?.[1]);
 if(!Number.isSafeInteger(total)||total<1024||total>650000000)throw Error("invalid PDF size");
 if(job.expected_bytes!=null&&Number(job.expected_bytes)!==total)throw Error("catalogue byte count changed");
 const pdfjs:any=await getResolvedPDFJS();
 const transport=new pdfjs.PDFDataRangeTransport(total,new Uint8Array(0));
 let rangeFailure:unknown=null;
 transport.requestDataRange=(start:number,end:number)=>{
  getRange(start,end-1).then(x=>transport.onDataRange(start,x.data))
  .catch(e=>{rangeFailure=e;transport.abort?.(e);});
 };
 const doc=await pdfjs.getDocument({range:transport,length:total,
    rangeChunkSize:256*1024,disableAutoFetch:true,disableStream:true,
    isEvalSupported:false,useSystemFonts:false}).promise;
 if(doc.numPages!==job.total_pages)throw Error("catalogue page count changed");
 const rows=[];
 for(let p=job.from;p<=job.to;p++){
  if(Date.now()-started>205000||rangeFailure)throw Error("page reader deadline/range failure");
  const pg=await doc.getPage(p),txt=await pg.getTextContent();
  const items:any[]=[],lines:any[]=[];
  for(const z of txt.items as any[]){
   if(typeof z.str!=="string"||!z.str.trim()||!z.transform)continue;
   const str=z.str.replace(/\0/g,"").slice(0,800);
   const x=Number(z.transform[4]),y=Number(z.transform[5]);
   items.push([str,Number(x.toFixed(1)),Number(y.toFixed(1)),
                Number((z.width||0).toFixed(1))]);
   let line=lines.find(r=>Math.abs(r.y-y)<2);
   if(!line){line={y,words:[]};lines.push(line);}
   line.words.push({str,x});
  }
  const text=lines.sort((a,b)=>b.y-a.y)
    .map(z=>z.words.sort((a:any,b:any)=>a.x-b.x).map((x:any)=>x.str).join("  ")).join("\n");
  if(items.length>20000||text.length>750000)throw Error("source page exceeds bounds");
  rows.push({page:p,text,items});
  pg.cleanup();
 }
 await doc.destroy();
 const saved=await rpc("rv_range_pilot_stage_v1",{p_catalogue_id:job.catalogue_id,
   p_lease:job.lease,p_rows:rows,p_elapsed_ms:Date.now()-started});
 return {saved,pages:rows.length,remote_requests:count,
    fetched_bytes:received,pdf_bytes:total,elapsed_ms:Date.now()-started};
}
Deno.serve(async req=>{
 if(req.method!=="POST")return json({error:"POST required"},405);
 const token=req.headers.get("x-rv-runner")||"";
 if(token.length!==64)return json({error:"unauthorized"},401);
 try{if(await rpc("rv_factory_auth",{t:token})!==true)return json({error:"unauthorized"},401);}
 catch{return json({error:"authentication unavailable"},503);}
 let job:any=null;
 try{
  job=await rpc("rv_range_pilot_claim_v1",{});
  if(!job)return json({status:"idle"});
  const result=await process(job);
  return json({status:"complete",catalogue:job.catalogue_id,...result});
 }catch(e){
  const error=e instanceof Error?e.message:String(e);
  if(job)await rpc("rv_range_pilot_release_v1",{p_catalogue_id:job.catalogue_id,
    p_lease:job.lease,p_error:error.slice(0,500),p_elapsed_ms:0}).catch(()=>{});
  return json({status:"failed",catalogue:job?.catalogue_id,error:error.slice(0,160)},502);
 }
});