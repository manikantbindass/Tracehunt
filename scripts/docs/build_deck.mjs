// Run a copy from .tmp/project-docs with @oai/artifact-tool available there.
import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import {Presentation,PresentationFile} from '@oai/artifact-tool';
const root=process.cwd();
process.env.RUNTIME_NODE_MODULES ||= 'C:/Users/manik/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules';
const skill=process.env.TRACEHUNT_PRESENTATION_SKILL || 'C:/Users/manik/.codex/plugins/cache/openai-primary-runtime/presentations/26.1020.11127/skills/presentations';
const python=process.env.TRACEHUNT_DOCS_PYTHON || 'C:/Users/manik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe';
const {finalizePresentation,applyPresentationChartFont}=await import(pathToFileURL(path.join(skill,'container_tools/artifact_tool_utils.mjs')).href);
const data=JSON.parse(await fs.readFile(path.join(root,'.tmp/project-docs/content.json'),'utf8'));
const p=Presentation.create({slideSize:{width:1280,height:720}});
const ink='#122B3C',teal='#087F80',muted='#536471',paper='#F6F8FA';
function box(s,text,x,y,w,h,size=28,color=ink,fill='none',bold=false){
 const q=s.shapes.add({geometry:fill==='none'?'textbox':'rect',position:{left:x,top:y,width:w,height:h},fill,line:{fill:'none',width:0}});
 q.text=text;q.text.style={typeface:'Arial',fontSize:size,color,bold,verticalAlignment:'middle',insets:fill==='none'?0:14,wrap:'square',autoFit:'none'};return q;
}
function connect(s,a,b){s.shapes.connect(a,b,{kind:'straight',fromSide:'right',toSide:'left',line:{fill:teal,width:2},tail:{type:'arrow',width:'med',length:'med'}});}
function flow(s,labels){const w=(1152-(labels.length-1)*30)/labels.length;let prev;
 labels.forEach((t,i)=>{let a=box(s,t,64+i*(w+30),260,w,112,24,ink,'#E2F0EF',true);if(prev)connect(s,prev,a);prev=a;});}
function architecture(s){
 const ui=box(s,'Next.js\ndashboard',64,245,230,100,26,ink,'#E2F0EF',true);
 const api=box(s,'FastAPI\nvalidation + queries',390,245,260,100,25,ink,'#E2F0EF',true);
 const sql=box(s,'SQL database\nauthoritative records',760,245,360,100,25,ink,'#E2F0EF',true);
 connect(s,ui,api);connect(s,api,sql);
 const worker=box(s,'Worker\nchecks + events',390,400,260,100,25,ink,'#E2F0EF',true);
 const ext=box(s,'Targets / optional Redis\nAI provider / webhook',760,400,360,100,24,ink,'#EAE5F5',true);
 s.shapes.connect(worker,sql,{kind:'straight',fromSide:'top',toSide:'bottom',line:{fill:teal,width:2},tail:{type:'arrow'}});connect(s,worker,ext);
 box(s,'Shippers also POST directly to FastAPI. API and worker can both run analysis.',64,540,1152,50,22,muted);
}
const charts=[];
for(let i=0;i<data.sections.length;i++){
 const d=data.sections[i],s=p.slides.add();s.background.fill=i===0?ink:paper;
 if(i===0){
  box(s,'TRACEHUNT / PROJECT EXPLAINED',70,65,1100,40,22,'#62D6C5',undefined,true);
  box(s,'TraceHunt AI',70,185,1100,110,76,'#FFFFFF',undefined,true);
  box(s,d.subtitle,70,315,1040,110,36,'#E2F0EF');
  box(s,'Architecture, incident intelligence, and operations',70,485,1100,60,27,'#FFFFFF');
  box(s,'Source snapshot 0f148d6  /  23 October 2026',70,620,1100,40,20,'#AABDC6');
 } else {
  box(s,'TRACEHUNT AI  /  '+String(i+1).padStart(2,'0'),64,30,1152,32,18,teal,undefined,true);
  box(s,d.title,64,85,1152,74,44,ink,undefined,true);
  box(s,d.subtitle,64,165,1152,60,26,teal);
  if(d.visual==='architecture')architecture(s);
  else if(d.visual==='errors'||d.visual==='latency'){
   let series=d.visual==='errors'?[{name:'Errors / minute',values:data.errors,line:{fill:teal,width:3}},{name:'Rolling 5-minute count',values:data.errors.map((_,j)=>data.errors.slice(Math.max(0,j-4),j+1).reduce((a,b)=>a+b,0)),line:{fill:'#7356B8',width:3}},{name:'Threshold 5',values:data.minutes.map(()=>5),line:{fill:'#CC5D3B',width:2}}]:[{name:'Synthetic p95 (ms)',values:data.latency,line:{fill:teal,width:3}}];
   series.forEach(x=>x.smooth=false);
   const ch=s.charts.add('line',{position:{left:64,top:250,width:850,height:345},categories:data.minutes.map(String),series,lineOptions:{smooth:false},hasLegend:true,legend:{position:'bottom',textStyle:{fontSize:18}},xAxis:{title:'Minute',textStyle:{fontSize:18}},yAxis:{title:d.visual==='errors'?'Error count':'Latency (ms)',min:0,max:d.visual==='errors'?30:1000,textStyle:{fontSize:18},majorGridlines:{fill:'#DCE4E8',width:1}},chartFill:paper,plotAreaFill:paper});
   applyPresentationChartFont(ch,{fontFamily:'Arial'});charts.push(i+1);
   box(s,'ILLUSTRATIVE\nDATA ONLY',950,255,260,80,24,teal,undefined,true);
   box(s,d.visual==='errors'?'Minute 4: rolling count = 9.\n\nExisting incidents do not auto-upgrade.':'Fictional release: minute 3.\n\nFictional mitigation: minute 7.',950,365,260,215,24,ink);
  }else if(d.visual){
   const flows={loop:['Collect','Detect','Investigate','Act externally','Resolve'],ingest:['Validate + redact','Log + event in SQL','Worker evaluates','Incident + event','Analysis / alert'],lifecycle:['Open','Investigating','Resolved','May reopen'],analysis:['Incident evidence','Local heuristic','Optional provider','Labeled result'],data:['Telemetry','Service + time','Incidents / timeline','Outbox / rule state']};
   flow(s,flows[d.visual]);box(s,d.points.join('\n\n'),64,420,1152,185,25,ink);
  }else{
   d.points.forEach((t,j)=>{box(s,String(j+1).padStart(2,'0'),64,275+j*106,65,65,30,teal,undefined,true);box(s,t,155,270+j*106,1050,80,30,ink);});
  }
  box(s,'IMPLEMENTATION: 0f148d6  |  Detailed explanation and source links in speaker notes',64,662,1090,25,16,muted);
  box(s,String(i+1).padStart(2,'0'),1160,662,55,25,16,muted);
 }
 s.speakerNotes.text=d.detail.join('\n\n')+'\n\nImplementation source: '+d.source+'\nGraph data, where present: invented instructional scenario; not measured telemetry.';
}
const build=path.join(root,'.tmp/project-docs');await fs.mkdir(path.join(build,'slides'),{recursive:true});
for(let i=0;i<p.slides.items.length;i++){
 const blob=await p.export({slide:p.slides.items[i],format:'png',scale:1});await fs.writeFile(path.join(build,'slides',`${String(i+1).padStart(2,'0')}.png`),new Uint8Array(await blob.arrayBuffer()));
}
const candidate=path.join(build,'candidate.pptx');await(await PresentationFile.exportPptx(p)).save(candidate);
const final=path.join(root,'docs/project-overview/TraceHunt-AI-Project-Presentation.pptx');
const result=await finalizePresentation({workspaceDir:root,candidatePath:candidate,finalPath:final,pythonExecutable:python,integrityValidatorPath:path.join(skill,'container_tools/inspect_presentation_package_integrity.py'),layoutValidatorPath:path.join(skill,'container_tools/inspect_presentation_layout_geometry.py'),layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-bullet-geometry','--validate-heading-fit'],requiredNativeChartOwnerSlides:charts,requiredNativeTableOwnerSlides:[],materializeLiteralChartWorkbooks:true,fontPolicy:{basis:'design',families:['Arial']},verifyArtifactToolImport:true,receiptPath:path.join(build,'validation.json')});
console.log(JSON.stringify(result));
