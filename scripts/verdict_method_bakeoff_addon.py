import sys; import os; sys.path.insert(0, os.path.dirname(__file__))
import verdict_method_bakeoff as b, statistics as st
j=2026*4+1
keys,tiers,out=b.run([j])
A,B_,D=tiers["A v2 (live)"],tiers["B v3.1 absolute"],tiers["D vs expectation"]
ks=[k for k in keys if k in out["react"]]
def rc(f,w="react"):
    kk=[k for k in keys if k in out[w]]
    return b.spearman([f(k) for k in kk],[out[w][k] for k in kk])
print("rank corr react  A %.3f  B %.3f  D %.3f"%(rc(lambda k:A[k]),rc(lambda k:B_[k]),rc(lambda k:D[k])))
for w in (0.15,0.3,0.5):
    print("blend A+D w=%.2f  react %.3f  run-up %.3f  drift %.3f"%(w,rc(lambda k:(1-w)*A[k]+w*D[k]),rc(lambda k:(1-w)*A[k]+w*D[k],"pre"),rc(lambda k:(1-w)*A[k]+w*D[k],"post")))
    print("blend A+B w=%.2f  react %.3f"%(w,rc(lambda k:(1-w)*A[k]+w*B_[k])))
print("-- A tier groups split by D (vs expectation)")
for lab,c in (("A Excellent+ & D>=Strong",lambda a,d:a>=4 and d>=3),("A Excellent+ & D<=Steady",lambda a,d:a>=4 and d<=2),("A Steady/Strong & D>=Strong",lambda a,d:2<=a<=3 and d>=3),("A Steady/Strong & D<=Weak",lambda a,d:2<=a<=3 and d<=1),("A Poor/Weak & D>=Steady",lambda a,d:a<=1 and d>=2),("A Poor/Weak & D<=Weak",lambda a,d:a<=1 and d<=1)):
    s=[k for k in ks if c(A[k],D[k])]
    if s: print("%-30s n=%4d react %+.2f%% run-up %+.2f%%"%(lab,len(s),st.mean(out["react"][k] for k in s),st.mean(out["pre"][k] for k in s if k in out["pre"])))
# bootstrap: is A better than B?
import random; random.seed(1); kk=ks; diffs=[]
for _ in range(300):
    smp=[random.choice(kk) for _ in kk]
    diffs.append(b.spearman([A[k] for k in smp],[out["react"][k] for k in smp])-b.spearman([B_[k] for k in smp],[out["react"][k] for k in smp]))
diffs.sort(); print("A minus B rank corr, 90pct interval: %.3f to %.3f"%(diffs[15],diffs[285]))
# where do A and B disagree most (B two+ tiers higher than A)
hi=[k for k in ks if B_[k]-A[k]>=2]; lo=[k for k in ks if A[k]-B_[k]>=2]
print("B two+ tiers above A: n=%d react %+.2f%%; A two+ tiers above B: n=%d react %+.2f%%"%(len(hi),st.mean(out["react"][k] for k in hi),len(lo),st.mean(out["react"][k] for k in lo)))
