import json,sys,random,collections,datetime as dt
R='/home/claude/market-content-bot/store/'
mc=json.load(open(R+'mcap/mcap.json'))
MON={'JAN':1,'FEB':2,'MAR':3,'APR':4,'MAY':5,'JUN':6,'JUL':7,'AUG':8,'SEP':9,'OCT':10,'NOV':11,'DEC':12}
def per(s):
    d,m,y=s.split('-'); return int(y)*4+(MON[m]-1)//3   # quarter index
rows={}
for l in open(R+'results_if/numbers.jsonl'):
    r=json.loads(l); n=r.get('n') or {}
    if not r.get('isin') or not (80<=(n.get('ctx_days') or 0)<=100): continue
    if n.get('rev') in (None,0) or n.get('pat') is None or n.get('ebitda') is None: continue
    k=(r['isin'],per(r['to']))
    pr=rows.get(k)
    # prefer consolidated, then latest filed
    sc=(r['cons']=='Consolidated', (r.get('filed') or ''))
    if pr is None or sc>pr[0]: rows[k]=(sc,r)
D={k:v[1]['n'] for k,v in rows.items()}
def seg(i):
    m=(mc.get(i) or {}).get('m')
    if m is None: return None
    return 'large' if m>=20000 else 'mid' if m>=5000 else 'small' if m>=1000 else 'micro' if m>=300 else 'nano'
def feats(i,q):
    c=D.get((i,q)); y=D.get((i,q-4)); p=D.get((i,q-1))
    if not c or not y: return None
    g=lambda a,b:(a/b-1)*100 if b and b>0 else None
    f={'rev_y':g(c['rev'],y['rev']),'rev_q':g(c['rev'],p['rev']) if p else None,
       'mg':c['ebitda']/c['rev']*100,'mg_y':c['ebitda']/c['rev']*100-y['ebitda']/y['rev']*100,
       'mg_q':(c['ebitda']/c['rev']-p['ebitda']/p['rev'])*100 if p else None,
       'pat_y':g(c['pat'],y['pat']),'pat_pos':c['pat']>0,'pat_prev_pos':y['pat']>0,
       'eb_y':g(c['ebitda'],y['ebitda']),
       'oi_share':(c.get('oi') or 0)/c['pbt']*100 if c.get('pbt') and c['pbt']>0 else None,
       'conv':c['pat']/c['ebitda']*100 if c['ebitda']>0 else None,'pm_y':c['pat']/c['rev']*100-y['pat']/y['rev']*100 if y['rev'] else None,'rev':c['rev'],'pat':c['pat'],'ebitda':c['ebitda'],'y_pat':y['pat'],'y_rev':y['rev']}
    return f
def pct(vals):
    s=sorted(vals); n=len(s)
    return lambda x:(sum(1 for v in s if v<x)+0.5*sum(1 for v in s if v==x))/n*100
CUTS=[0,18,32,44,56,68]; BBW=55
TIERS=['Poor','Weak','Steady','Strong','Excellent','Blockbuster']
def build(q,noise=0.0,rng=None):
    F={}
    for (i,qq) in D:
        if qq==q:
            f=feats(i,q)
            if f: F[i]=f
    if noise:
        for f in F.values():
            for k in ('rev_y','mg_y','pat_y','eb_y'):
                if f[k] is not None: f[k]+=rng.uniform(-noise,noise)*max(1,abs(f[k]))*0.5 if k!='mg_y' else rng.uniform(-noise,noise)*2
    bys=collections.defaultdict(list)
    for i,f in F.items(): bys[seg(i) or 'nano'].append(i)
    P={}
    for s,ids in bys.items():
        P[s]={k:pct([F[i][k] for i in ids if F[i][k] is not None]) for k in ('rev_y','mg_y','eb_y','pat_y','mg','conv')}
    out={}
    for i,f in F.items():
        s=seg(i) or 'nano'; p=P[s]
        if len(bys[s])<40: out[i]=('Not rated',{});continue
        # thin data / noise guards
        if f['y_rev']<5 or abs(f['y_pat'])<0.3 and f['pat']<1: out[i]=('Provisional',{});continue
        g=[p['rev_y'](f['rev_y'])] if f['rev_y'] is not None else []
        if f['eb_y'] is not None: g.append(p['eb_y'](f['eb_y']))
        gro=sum(g)/len(g) if g else None
        pr=[p['mg_y'](f['mg_y'])*0.6+p['mg'](f['mg'])*0.4]
        prof=pr[0]
        ql=[]
        if f['pat_y'] is not None: ql.append(p['pat_y'](f['pat_y']))
        if f['conv'] is not None: ql.append(p['conv'](f['conv']))
        qual=sum(ql)/len(ql) if ql else None
        if gro is None or qual is None: out[i]=('Provisional',{});continue
        pil={'growth':gro,'profit':prof,'quality':qual}
        # absolute floors (grade ceilings)
        ceil=5
        if f['pat']<=0: ceil=min(ceil,0 if f['pat']<f['y_pat'] else 1)
        if f['pat_y'] is not None and f['pat_y']<0: ceil=min(ceil,2)
        if f['rev_y'] is not None and f['rev_y']<10: ceil=min(ceil,3)
        if f['rev_y'] is not None and f['rev_y']<0: ceil=min(ceil,2)
        if f['mg_y']<0: ceil=min(ceil,4)
        if f['mg_y']<-0.5: ceil=min(ceil,3)
        if f['mg_y']<-2: ceil=min(ceil,2)
        if f['mg_q'] is not None and f['mg_q']<-1: ceil=min(ceil,4)
        if f['pat_y'] is not None and f['pat_y']<25: ceil=min(ceil,3)
        if f['rev_y'] is not None and f['rev_y']<20: ceil=min(ceil,4)
        weak=min(pil.values()); avg=sum(pil.values())/3
        sc=0.5*weak+0.5*avg   # weakest-pillar anchored
        cuts=CUTS
        t=max(j for j,c in enumerate(cuts) if sc>=c)
        # blockbuster needs every pillar >=70
        if t==5 and weak<BBW: t=4
        t=min(t,ceil)
        out[i]=(TIERS[t],pil|{'score':sc,'ceil':ceil})
    return out,F
if __name__=='__main__':
    for q in [2026*4+1,2026*4,2025*4+3]:
        o,F=build(q)
        c=collections.Counter(v[0] for v in o.values()); n=sum(c.values())
        print('Q',q//4,'idx',q%4,n,{t:c.get(t,0) for t in TIERS+['Provisional','Not rated']})
        bad=0
        for i,(t,pl) in o.items():
            f=F[i]
            if t=='Blockbuster' and (f['mg_q'] is not None and f['mg_q']<-1 or f['pat_y'] is not None and f['pat_y']<25 or f['mg_y']<0): bad+=1
            if t in('Excellent','Blockbuster') and (f['pat']<=0 or (f['pat_y'] or 0)<0): bad+=1
            if t=='Strong' and f['pat']<=0: bad+=1
        print(' never-event violations:',bad)
        # stability
        rng=random.Random(1); o2,_=build(q,0.05,rng); jump=0;chg=0;tot=0
        for i,(t,_) in o.items():
            t2=o2.get(i,('x',))[0]
            if t in TIERS and t2 in TIERS:
                tot+=1;d=abs(TIERS.index(t)-TIERS.index(t2)); chg+=d>0; jump+=d>=2
        print(' stability (5pct noise): changed %.1f%%, two+ level jumps %.2f%%'%(chg/tot*100,jump/tot*100))
