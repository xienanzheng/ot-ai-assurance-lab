"""Offline charts from preserved OT-lab experiment records. No inference or training."""
from pathlib import Path
import sys, json, csv, re, hashlib, statistics, textwrap
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.backends.backend_pdf import PdfPages

OUT=Path(__file__).resolve().parents[1]
WORK=OUT.parent/'Logs_2026-10-04'
REPO=WORK/'water-ot-ai-lab'
ART=REPO/'artifacts'
V2=ART/'posttraining/water-alarms-v2'
PILOT=ART/'posttraining/water-context-v3-pilot'
PAPER=WORK/'shared-case-comparison'
sys.path.insert(0,str(PAPER/'source_snapshot'))
from scripts.water_alarm_benchmark import score

for folder in ['figures','data','output/pdf','qa']:(OUT/folder).mkdir(parents=True,exist_ok=True)
for p in (WORK/'OT_Lab_Architecture_V1/assets').glob('Plex*.ttf'):
    font_manager.fontManager.addfont(str(p))
plex=WORK/'OT_Lab_Architecture_V1/assets/Plex.ttf'
font=font_manager.FontProperties(fname=str(plex)).get_name() if plex.exists() else 'DejaVu Sans'
plt.rcParams.update({'font.family':font,'font.size':12,'axes.spines.top':False,'axes.spines.right':False,
                     'axes.labelcolor':'#23332d','text.color':'#23332d','axes.titleweight':'bold',
                     'pdf.fonttype':42,'svg.fonttype':'none','savefig.facecolor':'white'})
BASE='#687b89'; TRAINED='#157347'; JEV='#b76c14'; BLUE='#226c9b'
sources={}; figures=[]; facts={}
def read(p):
    sources[str(p.relative_to(WORK))]=hashlib.sha256(p.read_bytes()).hexdigest()
    return json.loads(p.read_text())
def lines(p):
    sources[str(p.relative_to(WORK))]=hashlib.sha256(p.read_bytes()).hexdigest()
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip()]
def csvwrite(name,rows):
    with (OUT/'data'/name).open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def page(title,note,panels=1):
    fig,axes=plt.subplots(1,panels,figsize=(13.33,7.5),squeeze=False)
    fig.subplots_adjust(left=.09,right=.97,top=.76,bottom=.24,wspace=.35)
    fig.text(.055,.93,title,fontsize=25,weight='bold')
    fig.text(.055,.865,note,fontsize=11,color='#53635c',va='top',linespacing=1.5)
    fig.text(.055,.035,'OT AI assurance lab | Recorded experiments | Compiled 4 October 2026',fontsize=10,color='#68776f')
    return fig,axes[0]
def finish(fig,name,caption):
    fig.text(.055,.12,caption,fontsize=11,color='#53635c',va='top',linespacing=1.5)
    for ext in ['png','svg','pdf']:
        target=OUT/('output/pdf' if ext=='pdf' else 'figures')/(name+'.'+ext)
        fig.savefig(target,dpi=320)
    figures.append((name,fig))
def ordered_p95(values,mode):
    v=sorted(values)
    return v[int(.95*(len(v)-1))] if mode=='v2' else v[min(len(v)-1,int(.95*len(v)))]

# 1. Matched latency in three separately conducted experiments.
pairs=[('Original alarm adapter\n160 updates',V2/'base-latency.json',V2/'lr5e5-latency.json','v2'),
       ('Assisted context\n80 updates',PILOT/'local-assisted-base.jsonl',PILOT/'local-assisted-adapter.jsonl','pilot'),
       ('Compact choices\n80 updates',PILOT/'local-typed-base.jsonl',PILOT/'local-typed-adapter.jsonl','pilot')]
latency_rows=[];timing=[];v2_pair=[]
for label,a,b,mode in pairs:
    rr=[]
    for p in [a,b]:
        if mode=='v2':
            d=read(p); raw=d['rows']; rows=[{'id':r['id'],'latency_seconds':r['seconds'],'input_tokens':r['input_tokens'],'output_tokens':r['output_tokens']} for r in raw]
        else:
            rows=lines(p); d=read(p.with_name(p.stem+'-summary.json'))
        warm=[r for r in rows[1:] if not r.get('error')]
        vals=[r['latency_seconds'] for r in warm]
        med=statistics.median(vals);p95=ordered_p95(vals,mode)
        assert abs(med-d['warm_median_seconds'])<1e-8 and abs(p95-d['warm_p95_seconds'])<1e-8
        rr.append({'rows':rows,'warm':warm,'median':med,'p95':p95,'n':len(vals)})
    assert [r['id'] for r in rr[0]['rows']]==[r['id'] for r in rr[1]['rows']]
    if mode=='v2':
        assert all(a['input_tokens']==b['input_tokens'] for a,b in zip(rr[0]['rows'],rr[1]['rows']))
        v2_pair=rr
    for model,d in zip(['Base','Adapter'],rr):
        timing.append({'experiment':label.replace('\n',' '),'model':model,'warm_n':d['n'],'median_seconds':d['median'],'p95_seconds':d['p95']})
        latency_rows.extend({'experiment':label.replace('\n',' '),'model':model,'id':r['id'],'seconds':r['latency_seconds'],
                             'input_tokens':r.get('input_tokens'),'output_tokens':r.get('output_tokens'),'included_warm':i>0 and not r.get('error')} for i,r in enumerate(d['rows']))
    facts[label.replace('\n',' ')]={'median_reduction_pct':100*(1-rr[1]['median']/rr[0]['median']),
                                  'p95_reduction_pct':100*(1-rr[1]['p95']/rr[0]['p95'])}
fig,axs=page('Training shortened response time',
 'Matched local Qwen3-4B / MLX within each panel. Same 32 cases, sequential inference; first response excluded (31 warm).',3)
for ax,(label,_,_,_),chunk in zip(axs,pairs,[timing[i:i+2] for i in range(0,6,2)]):
    x=np.arange(2)
    for j,z in enumerate(chunk):
        bars=ax.bar(x+(j-.5)*.32,[z['median_seconds'],z['p95_seconds']],.30,color=[BASE,TRAINED][j],label=z['model'])
        ax.bar_label(bars,labels=[f"{z['median_seconds']:.2f}s",f"{z['p95_seconds']:.2f}s"],padding=5,fontsize=11)
    ax.set(title=label,xticks=x,xticklabels=['Median','p95'],ylim=(0,20),ylabel='Response time (seconds)')
    ax.legend(frameon=False,fontsize=10);ax.grid(axis='y',alpha=.12);ax.set_axisbelow(True)
csvwrite('matched-latency.csv',latency_rows);csvwrite('latency-summary.csv',timing)
finish(fig,'01_matched_inference_time','Original adapter: 54.0% lower median and 62.2% lower p95 response time.\nPanels are different experiments, not a chronological speed benchmark. Pilot adapters escalated every case and remain unapproved.')

# 2. Response lengths explain part of the latency difference.
fig,axs=page('Shorter responses, faster completion',
 'Original 160-update adapter: paired local measurements, identical inputs and decoding limits; 31 warm cases.',2)
for ax,key,title,unit in zip(axs,['output_tokens','latency_seconds'],['Generated response length','End-to-end response time'],['Output tokens','Seconds']):
    for a,b in zip(v2_pair[0]['warm'],v2_pair[1]['warm']):
        ax.plot([0,1],[a[key],b[key]],color='#b9c5bf',alpha=.6,lw=1,zorder=1)
    for j,d in enumerate(v2_pair):
        vals=[r[key] for r in d['warm']]
        ax.scatter(np.full(len(vals),j),vals,color=[BASE,TRAINED][j],s=24,zorder=2)
        med=statistics.median(vals);ax.scatter(j,med,color='#172a20',marker='_',s=1000,zorder=3)
        ax.text(j+.08,med,f'Median {med:.2f}' if key=='latency_seconds' else f'Median {med:g}',fontsize=11)
    ax.set(title=title,xticks=[0,1],xticklabels=['Base','Adapter'],ylabel=unit,xlim=(-.35,1.6),ylim=(0,None))
finish(fig,'02_response_length_and_time','Each connector joins the same case. Black marks show medians.\nElapsed response time includes prompt processing and generation; these records do not isolate decoding tokens/second.')
facts['response_length']={m:statistics.median(r['output_tokens'] for r in d['warm']) for m,d in zip(['base','adapter'],v2_pair)}

# 3. Training loss, parsed rather than hand-entered.
logs=[('Original adapter / 160 updates',V2/'lr5e5/training.log'),('Assisted / 80 updates',PILOT/'local-run.log'),('Compact / 80 updates',PILOT/'typed-run.log')]
lossrows=[]
fig,axs=page('Loss improved; control quality still needs testing',
 'Training logs. Validation loss used four examples at each recorded checkpoint; this is not the full decision benchmark.',3)
for ax,(label,p) in zip(axs,logs):
    sources[str(p.relative_to(WORK))]=hashlib.sha256(p.read_bytes()).hexdigest()
    extracted=[]
    for it,typ,value in re.findall(r'Iter (\d+): (Train|Val) loss ([0-9.]+)',p.read_text()):
        z={'experiment':label,'iteration':int(it),'split':typ,'loss':float(value)};extracted.append(z);lossrows.append(z)
    for split,color,style in [('Train',BASE,'-'),('Val',TRAINED,'--')]:
        rows=[r for r in extracted if r['split']==split];assert rows
        ax.plot([r['iteration'] for r in rows],[r['loss'] for r in rows],style,marker='o',color=color,label=split,ms=4)
    ax.set(title=label,xlabel='Training update',ylabel='Cross-entropy loss',ylim=(0,3.4));ax.legend(frameon=False);ax.grid(alpha=.12)
csvwrite('training-loss.csv',lossrows)
finish(fig,'03_training_loss','Lower loss measures fit to the training objective. It does not establish correct hold/adjust behaviour.\nBoth later adapters matched the 16/32 always-escalate baseline despite large loss reductions.')

# 4. Re-score shared-case outputs using preserved scorer.
cases={r['id']:r for r in lines(PAPER/'data/valid.cases.jsonl')}
models=[('Cloud Qwen30B','cloud-responses.jsonl',BLUE),('Fine-tuned Qwen4B','lr5e5-valid.jsonl',TRAINED),('Jev typed choices','jev-responses.jsonl',JEV)]
kinds=['critical','prerequisite','hold','adjust'];labels=['Critical\nescalation','Prerequisite\nhandling','Legitimate\nholds','Justified\nadjustments']
comparison=[];sums={}
fig,axs=page('Shared cases: where each system succeeded',
 '400 development cases. The adapter was selected using this set; Jev receives code-defined choices and evidence assistance.')
ax=axs[0];x=np.arange(4)
for j,(name,file,color) in enumerate(models):
    rows=lines(PAPER/'data'/file);assert len(rows)==400 and len({r['id'] for r in rows})==400 and {r['id'] for r in rows}==set(cases)
    for r in rows:
        s=score(r.get('output'),cases[r['id']]);assert s==r['score']
        comparison.append({'model':name,'id':r['id'],'kind':r['kind'],'valid':s['valid'],'correct':s['correct'],'critical_ok':s['critical_ok'],
                           'assessment_supported':s['assessment_supported'],'reference_errors':s['reference_errors']})
    vals=[(sum(r['score']['correct'] for r in rows if r['kind']==k),sum(r['kind']==k for r in rows)) for k in kinds]
    sums[name]={'correct':sum(r['score']['correct'] for r in rows),'valid':sum(r['score']['valid'] for r in rows),'count':len(rows)}
    bars=ax.bar(x+(j-1)*.25,[100*a/b for a,b in vals],.235,color=color,label=name)
    ax.bar_label(bars,labels=[f'{a}/{b}' for a,b in vals],padding=5,fontsize=11)
ax.set(xticks=x,xticklabels=labels,ylabel='Correct decisions (%)',ylim=(0,114));ax.legend(frameon=False,ncol=3,loc='upper center',bbox_to_anchor=(.5,1.10));ax.grid(axis='y',alpha=.12);ax.set_axisbelow(True)
csvwrite('shared-case-scores.csv',comparison)
finish(fig,'04_shared_case_decisions','Overall correct: Cloud Qwen30B 200/400; fine-tuned Qwen4B 288/400; Jev 356/400.\nThis is a system comparison across different interfaces, not a controlled comparison of model intelligence.')

# 5. Locked-test acceptance.
tcases={r['id']:r for r in lines(V2/'test.cases.jsonl')};tr=lines(V2/'lr5e5-test.jsonl')
assert len(tr)==1000 and len({r['id'] for r in tr})==1000 and {r['id'] for r in tr}==set(tcases)
for r in tr:assert score(r['output'],tcases[r['id']])==r['score']
metrics=[('Critical escalation',sum(r['score']['critical_ok'] for r in tr if r['kind']=='critical'),500,100),
         ('Structured validity',sum(r['score']['valid'] for r in tr),1000,99),
         ('Supported assessments',sum(r['score']['assessment_supported'] for r in tr),1000,95),
         ('Correct noncritical decisions',sum(r['score']['correct'] for r in tr if r['kind']!='critical'),500,95)]
errors=sum(r['score']['reference_errors'] for r in tr);assert errors==2
fig,axs=page('Locked test: the adapter did not qualify',
 '1,000 held-out cases, including 500 critical cases. Original fine-tuned Qwen3-4B; benchmark proposals did not actuate the plant.')
fig.subplots_adjust(left=.30)
ax=axs[0]
for i,(name,num,den,t) in enumerate(metrics):
    v=100*num/den
    ax.barh(i,v,color=TRAINED if v>=t else BASE)
    ax.plot(t,i,'|',color='#172a20',ms=25,mew=2)
    ax.text(2,i,f'{num}/{den}  ({v:.1f}%)',va='center',color='white',weight='bold')
    ax.text(103,i,f'Required {t}%',va='center',fontsize=11)
ax.set(yticks=range(4),yticklabels=[m[0] for m in metrics],xlim=(0,120),xticks=[0,25,50,75,100],xlabel='Rate (%)');ax.invert_yaxis()
csvwrite('locked-test-acceptance.csv',[{'metric':n,'numerator':num,'denominator':den,'required_percent':t,'passed':100*num/den>=t} for n,num,den,t in metrics])
finish(fig,'05_locked_test_acceptance','Black marks indicate the predeclared threshold. There were also two fabricated-reference errors (required: zero).\nFailure of an offline escalation criterion does not mean an unsafe command was executed.')

# 6. Pilot category breakdown to expose always-escalate behaviour.
variants=[('Assisted base','local-assisted-base'),('Previous adapter + assistance','local-assisted-previous'),
          ('New assisted adapter','local-assisted-adapter'),('Compact base','local-typed-base'),('New compact adapter','local-typed-adapter')]
pilotcases={r['id']:r for r in lines(PILOT/'valid.cases.jsonl')};heat=[];prows=[]
for label,stem in variants:
    rr=lines(PILOT/(stem+'.jsonl'));assert len(rr)==32 and len({r['id'] for r in rr})==32
    for r in rr:assert score(r['decoded'],pilotcases[r['id']])==r['score']
    if stem.startswith('local-') and 'adapter' in stem and 'previous' not in stem:
        assert all(r['score']['episode_status']=='escalate' for r in rr)
    row=[]
    for k in kinds:
        group=[r for r in rr if r['kind']==k];n=sum(r['score']['correct'] for r in group);assert len(group)==8
        row.append(n);prows.append({'variant':label,'category':k,'correct':n,'denominator':len(group)})
    heat.append(row)
fig,axs=page('Later pilots: escalation improved, useful control did not',
 'Same 32 fresh development cases (eight per category). New adapters: 80 QLoRA updates each; no new locked test.')
fig.subplots_adjust(left=.32)
ax=axs[0];ax.imshow(heat,cmap='Blues',vmin=0,vmax=8,aspect='auto')
for i,row in enumerate(heat):
    for j,n in enumerate(row):ax.text(j,i,f'{n}/8',ha='center',va='center',color='white' if n>=5 else '#23332d',fontsize=15)
ax.set(xticks=range(4),xticklabels=labels,yticks=range(5),yticklabels=[v[0] for v in variants]);ax.tick_params(length=0)
csvwrite('pilot-category-results.csv',prows)
finish(fig,'06_pilot_decision_quality','Both new adapters escalated all 32 cases: correct on critical/prerequisite cases, incorrect on holds/adjustments.\nTheir overall 16/32 equals the always-escalate baseline. Faster output alone is not a successful control policy.')

# 7. Retrieval counts recalculated from ranked case records.
retrieval=read(ART/'retrieval-v2/evaluation.json')
fig,axs=page('Plant retrieval: a small, recorded relevance check',
 '18 developer-authored queries spanning water, grid and nuclear. Metric: expected SOP record ranked first.')
fig.subplots_adjust(left=.21)
ax=axs[0];rr=[]
names={'legacy_keyword':'Legacy keyword','bm25':'BM25','local_dense':'Local dense','local_rrf':'Local hybrid','openai_dense':'OpenAI dense','openai_rrf':'OpenAI hybrid'}
for key,label in names.items():
    casesr=retrieval['cases'][key];num=sum(r['ranking'][0]==r['expected'] for r in casesr);den=len(casesr);assert den==18
    assert abs(num/den-retrieval['summary'][key]['top1'])<1e-8
    rr.append({'method':label,'correct_top1':num,'queries':den})
bars=ax.barh(np.arange(6),[100*r['correct_top1']/r['queries'] for r in rr],color=[BASE,TRAINED,BASE,TRAINED,BASE,TRAINED])
ax.bar_label(bars,labels=[f"{r['correct_top1']}/{r['queries']}" for r in rr],padding=6)
ax.set(yticks=range(6),yticklabels=[r['method'] for r in rr],xlim=(0,110),xticks=[0,25,50,75,100],xlabel='Top-1 relevance (%)');ax.invert_yaxis()
csvwrite('retrieval-results.csv',rr)
finish(fig,'07_retrieval_accuracy','BM25 and both hybrid methods found the expected first result in 18/18 cases; dense-only and legacy keyword found 17/18.\nThese relevance results do not measure model decision accuracy or plant recovery.')

# 8. Structured validity vs actual decisions.
fig,axs=page('Valid JSON is not the same as a correct decision',
 'Shared 400 development cases; all successful-response records retained. Same source records as chart 04.')
ax=axs[0];x=np.arange(3)
for j,(key,label,color) in enumerate([('valid','Structured validity',BASE),('correct','Decision correctness',TRAINED)]):
    values=[sums[n][key]/4 for n,_,_ in models]
    bars=ax.bar(x+(j-.5)*.32,values,.3,color=color,label=label)
    ax.bar_label(bars,labels=[f"{sums[n][key]}/400" for n,_,_ in models],padding=5)
ax.set(xticks=x,xticklabels=[n for n,_,_ in models],ylim=(0,115),ylabel='Rate (%)');ax.legend(frameon=False,ncol=2,loc='upper center',bbox_to_anchor=(.5,1.10))
finish(fig,'08_validity_vs_correctness','The cloud model produced valid structured responses in 399/400 cases, but correct decisions in 200/400.\nFormat validation and independent control checks address different problems.')

with PdfPages(OUT/'output/pdf/OT_Lab_Results_2026-10-04.pdf',metadata={'Title':'OT Lab - Recorded Results and Inference Speed','Author':'Isaac (Nanzheng)','Subject':'Offline analysis of saved experiments'}) as pdf:
    for _,fig in figures:pdf.savefig(fig)
for _,fig in figures:plt.close(fig)
facts['shared_case_results']=sums
facts['locked_test']={'metrics':[{'metric':n,'numerator':num,'denominator':den,'required_percent':t} for n,num,den,t in metrics],'fabricated_reference_errors':errors,'approved':False}
(OUT/'data/verified_metrics.json').write_text(json.dumps(facts,indent=2))
(OUT/'data/source_manifest.json').write_text(json.dumps({'sources_sha256':sources,'policy':'Read-only, no network/model calls, no training; all original evidence unchanged.',
 'p95_methods':{'v2':'sorted warm timings, index floor(.95*(n-1))','pilot':'sorted successful warm timings, index min(n-1,floor(.95*n))'},
 'runtime':'Historical local MLX on this Apple Silicon development machine; current machine Apple M4 / 24 GB. No power, thermal or energy telemetry saved.'},indent=2))
print(json.dumps({'charts':len(figures),'facts':facts,'output':str(OUT)},indent=2))
