"""Build the project guide with ReportLab. Run from the repository root."""
from pathlib import Path
from html import escape
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Flowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_LEFT
from content import SECTIONS, export

OUT=Path('docs/project-overview');OUT.mkdir(parents=True,exist_ok=True)
export('.tmp/project-docs/content.json')
styles=getSampleStyleSheet()
styles.add(ParagraphStyle(name='TitleTH',fontName='Helvetica-Bold',fontSize=26,leading=30,textColor=HexColor('#122B3C'),spaceAfter=14))
styles.add(ParagraphStyle(name='SubTH',fontName='Helvetica',fontSize=13,leading=18,textColor=HexColor('#087F80'),spaceAfter=18))
styles.add(ParagraphStyle(name='BodyTH',fontName='Helvetica',fontSize=10.5,leading=15,spaceAfter=13))
styles.add(ParagraphStyle(name='PointTH',fontName='Helvetica-Bold',fontSize=10.5,leading=15,spaceAfter=7,textColor=HexColor('#122B3C')))
styles.add(ParagraphStyle(name='SourceTH',fontName='Helvetica',fontSize=7.5,leading=10,textColor=HexColor('#536471'),spaceBefore=12))

class Visual(Flowable):
 def __init__(self,kind): super().__init__();self.kind=kind;self.width=475;self.height=160
 def draw(self):
  c=self.canv;c.setStrokeColor(HexColor('#087F80'));c.setFillColor(HexColor('#122B3C'))
  if self.kind=='architecture':
   def node(x,y,w,label):
    c.setFillColor(HexColor('#E8F3F2'));c.roundRect(x,y,w,43,4,fill=1);c.setFillColor(HexColor('#122B3C'));c.setFont('Helvetica-Bold',8)
    for j,t in enumerate(label.split('|')):c.drawCentredString(x+w/2,y+27-j*12,t)
   node(0,100,115,'Dashboard|and shippers');node(170,100,115,'FastAPI|validation + queries');node(340,100,130,'SQL|durable records')
   node(170,20,115,'Worker|checks + events');node(340,20,130,'Targets / optional|Redis, AI, webhook')
   def arrow(x,y,u,v):
    c.line(x,y,u,v);c.line(u,v,u-4,v+3);c.line(u,v,u-4,v-3)
   arrow(115,121,170,121);arrow(285,121,340,121);arrow(285,41,340,41);arrow(285,60,340,100)
   return
  if self.kind in ['errors','latency']:
   vals=[0,1,0,2,6,9,7,4,2,1,0,0] if self.kind=='errors' else [110,115,118,150,420,790,880,720,410,200,135,120]
   series=[vals];colors=['#087F80'];maximum=1000
   if self.kind=='errors': series += [[sum(vals[max(0,i-4):i+1]) for i in range(12)],[5]*12];colors+=['#7356B8','#CC5D3B'];maximum=30
   c.setFont('Helvetica',8);c.drawString(30,149,'ILLUSTRATIVE DATA - '+('error counts' if self.kind=='errors' else 'p95 latency (ms)'))
   for j in range(6):
    y=25+j*21;c.setStrokeColor(HexColor('#DCE4E8'));c.line(30,y,455,y);c.setFillColor(HexColor('#536471'));c.drawRightString(25,y-3,str(int(maximum*j/5)))
   for i in range(12): c.drawCentredString(30+i*38.5,12,str(i))
   for values,color in zip(series,colors):
    c.setStrokeColor(HexColor(color));c.setLineWidth(1.8)
    for i in range(11): c.line(30+i*38.5,25+105*values[i]/maximum,30+(i+1)*38.5,25+105*values[i+1]/maximum)
   c.setFillColor(HexColor('#536471'));c.drawRightString(455,0,'minute')
   return
  labels={'architecture':['Dashboard / shippers','FastAPI','SQL database','Worker','Targets / Redis / AI'], 'loop':['Collect','Detect','Investigate','Act externally','Resolve'], 'ingest':['Validate + redact','Log + event in SQL','Worker evaluates','Incident + event','Analysis / alert'], 'lifecycle':['Open','Investigating','Resolved','May reopen'], 'analysis':['Incident evidence','Local heuristic','Optional provider','Labeled result'], 'data':['Telemetry records','Service + time','Incidents / timeline','Events / rule state']}[self.kind]
  w=86 if len(labels)==5 else 105;gap=10;x=0
  for i,label in enumerate(labels):
   c.setFillColor(HexColor('#E8F3F2'));c.setStrokeColor(HexColor('#087F80'));c.roundRect(x,55,w,60,5,fill=1)
   words=label.split();lines=[];line=''
   for word in words:
    if len(line+' '+word)>16: lines.append(line);line=word
    else: line=(line+' '+word).strip()
   lines.append(line);c.setFillColor(HexColor('#122B3C'));c.setFont('Helvetica-Bold',8)
   for j,line in enumerate(lines): c.drawCentredString(x+w/2,90-j*12,line)
   if i<len(labels)-1:
    c.setStrokeColor(HexColor('#087F80'));c.line(x+w,85,x+w+gap,85);c.line(x+w+gap,85,x+w+gap-3,88);c.line(x+w+gap,85,x+w+gap-3,82)
   x+=w+gap
  c.setFillColor(HexColor('#536471'));c.setFont('Helvetica',8)
  c.drawString(0,30,'Conceptual flow; the accompanying text defines exact relationships and optional paths.')

def footer(c,doc):
 c.setStrokeColor(HexColor('#DCE4E8'));c.line(60,44,535,44);c.setFillColor(HexColor('#536471'));c.setFont('Helvetica',8)
 c.drawString(60,30,'TRACEHUNT AI  |  PROJECT GUIDE  |  SOURCE SNAPSHOT 0f148d6');c.drawRightString(535,30,str(doc.page))
story=[]
for i,s in enumerate(SECTIONS):
 if i:story.append(PageBreak())
 story += [Paragraph(f'{i+1:02d} / PROJECT EXPLAINED',styles['SourceTH']),Spacer(1,12),Paragraph(escape(s['title']),styles['TitleTH']),Paragraph(escape(s['subtitle']),styles['SubTH'])]
 if s['visual']:story.extend([Visual(s['visual']),Spacer(1,12)])
 for point in s['points']:story.append(Paragraph(escape(point),styles['PointTH']))
 story.append(Spacer(1,8))
 for p in s['detail']:story.append(Paragraph(escape(p),styles['BodyTH']))
 label=s['source'].split('/'+ '0f148d696d546a78c850bdffa3a55eb52c56ce6b'+'/')[-1]
 story.append(Paragraph('Implementation reference: <link href="'+s['source']+'" color="#087F80">'+escape(label)+'</link>',styles['SourceTH']))
 if s['visual']=='errors':story.append(Paragraph('Legend: teal = errors/minute; purple = rolling five-minute count; orange = threshold 5.',styles['SourceTH']))
 if i==0:story.append(Paragraph('24 topics / architecture and workflow diagrams / two illustrative graphs<br/>Prepared 23 October 2026. Read alongside the repository README and operator runbook.',styles['SubTH']))
doc=SimpleDocTemplate(str(OUT/'TraceHunt-AI-Project-Guide.pdf'),pagesize=(595.28,841.89),rightMargin=60,leftMargin=60,topMargin=48,bottomMargin=62,title='TraceHunt AI - Complete Project Guide',author='TraceHunt AI project',subject='Architecture, workflows, operations, and implementation boundaries')
doc.build(story,onFirstPage=footer,onLaterPages=footer)
print('PDF created:',OUT/'TraceHunt-AI-Project-Guide.pdf')
