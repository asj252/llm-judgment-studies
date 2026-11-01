"""Ten joint cluster statistics and the unchanged PLAN percentile rules.

Arrays have strata AC/BD, cluster, paired role A/C or B/D, condition.
Condition order is the frozen prompts.COMBINATIONS order. No score midpoint is
used. AUC numerators use 2*K in {0,1,2}; differences precede division.
"""
import numpy as np
from fractions import Fraction

NAMES = ('H1','H2','H3','H4a','H4b','H5_DAP','H5_CoT','H5_CF','H6a','H6b')
ONE_SIDED = np.array([True,True,True,False,False,False,False,False,False,True])
DOMAINS = np.array([[-.5,.5],[-100,100],[-200,200]]+[[-1,1]]*7, dtype=float)
THRESHOLDS = {0:.10,1:10.,2:10.,9:.10}
EQUIVALENCE = (3,4,5,6,7,8)
AUC_CHANNELS = (0,4,5,6,7,8,9)


def endpoint_bounds(lower, upper):
    """Range of the nonmonotone endpoint indicator over a closed interval."""
    lower, upper = np.asarray(lower), np.asarray(upper)
    if np.any(lower>upper):
        raise ValueError('reversed interval')
    return ((upper<=5)|(lower>=95)).astype(float), ((lower<=5)|(upper>=95)).astype(float)


def checked_sample(lower, upper):
    lower, upper = np.asarray(lower,dtype=float), np.asarray(upper,dtype=float)
    if lower.shape!=upper.shape or lower.ndim!=4 or lower.shape[0]!=2 or lower.shape[2:]!=(2,13):
        raise ValueError('expected [2,n,2,13] interval arrays')
    if not np.isfinite(lower).all() or not np.isfinite(upper).all() or np.any(lower<0) or np.any(upper>100) or np.any(lower>upper):
        raise ValueError('invalid score bounds')
    return lower, upper


def _weighted_mean(weights, vector):
    # Exact constant preservation, rather than separate large nearly equal sums.
    reference=vector[0]
    return reference+(weights@(vector-reference))/weights.sum(axis=1)


def _paired_weighted_mean(weights,lower,upper):
    """One effective-support anchor per row for ordered interval means.

    Constants on either side remain exact. Zero-count supports cannot choose
    the anchor or enter arithmetic. No endpoint clipping, swapping or jitter.
    """
    weights=np.atleast_2d(np.asarray(weights,dtype=float))
    lower,upper=np.asarray(lower,dtype=float),np.asarray(upper,dtype=float)
    if lower.ndim!=1 or lower.shape!=upper.shape or weights.ndim!=2 or weights.shape[1]!=len(lower):
        raise ValueError('paired mean shape mismatch')
    total=weights.sum(axis=1)
    if not np.isfinite(weights).all() or np.any(weights<0) or not np.isfinite(total).all() or np.any(total<=0):
        raise ValueError('finite nonnegative weights with positive finite sums required')
    if not np.isfinite([lower,upper]).all() or np.any(lower>upper):raise ValueError('ordered finite bounds required')
    active=weights>0;first=active.argmax(axis=1)
    lr,ur=lower[first],upper[first]
    lc=np.all(~active|(lower==lr[:,None]),axis=1)
    uc=np.all(~active|(upper==ur[:,None]),axis=1)
    anchor=np.where(uc&~lc,ur,lr)
    def centered(vector):
        delta=np.zeros_like(weights)
        np.subtract(vector[None,:],anchor[:,None],out=delta,where=active)
        return anchor+np.sum(weights*delta,axis=1)/total
    if np.array_equal(lower,upper):
        value=centered(lower);value[lc]=lr[lc]
        return value,value.copy()
    low,high=centered(lower),centered(upper)
    low[lc]=lr[lc];high[uc]=ur[uc]
    return low,high


class JointKernel:
    def __init__(self, lower, upper):
        self.lower,self.upper=checked_sample(lower,upper)
        self.kernels=[]
        for channel in AUC_CHANNELS:
            c0,c1=self.lower[0,:,1,channel],self.upper[0,:,1,channel]
            d0,d1=self.lower[1,:,1,channel],self.upper[1,:,1,channel]
            self.kernels.append((2*(d0[:,None]>c1)+(d0[:,None]==c1),
                                 2*(d1[:,None]>c0)+(d1[:,None]==c0)))
        self.kernels=[(lo.astype(float),hi.astype(float)) for lo,hi in self.kernels]

    def statistics(self, weights_ac, weights_bd):
        wt,wa=np.atleast_2d(weights_ac).astype(float),np.atleast_2d(weights_bd).astype(float)
        if wt.shape!=wa.shape or wt.shape[1]!=self.lower.shape[1]:
            raise ValueError('weight/sample shape mismatch')
        if np.any(wt<0) or np.any(wa<0) or np.any(wt.sum(axis=1)<=0) or np.any(wa.sum(axis=1)<=0):
            raise ValueError('invalid resampling counts')
        denominator=2*wt.sum(axis=1)*wa.sum(axis=1)
        numerators=[(np.sum((wa@lo)*wt,axis=1),np.sum((wa@hi)*wt,axis=1)) for lo,hi in self.kernels]
        ac=_paired_weighted_mean(wt,self.lower[0,:,1,5]-self.upper[0,:,0,5],self.upper[0,:,1,5]-self.lower[0,:,0,5])
        bd=_paired_weighted_mean(wa,self.lower[1,:,1,5]-self.upper[1,:,0,5],self.upper[1,:,1,5]-self.lower[1,:,0,5])
        output=[]
        for side in (0,1):
            num=[x[side] for x in numerators]
            other=[x[1-side] for x in numerators]
            x=np.empty((len(wt),10),float)
            x[:,0]=num[2]/denominator-.5
            x[:,1]=ac[side]
            x[:,2]=ac[side]-bd[1-side]
            # Channel list: LqZ, PsZ, PZ, PDAP, PCoT, PCF, MZ.
            for index,first,second in ((3,1,0),(4,2,1),(5,3,2),(6,4,2),(7,5,2),(8,6,2)):
                x[:,index]=(num[first]-other[second])/denominator
            p=endpoint_bounds(self.lower[0,:,1,5],self.upper[0,:,1,5])
            m=endpoint_bounds(self.lower[0,:,1,9],self.upper[0,:,1,9])
            # Integer endpoint contrasts: combine the count numerator before
            # division, avoiding separate L/U reference add-back roundoff.
            x[:,9]=(wt@(p[side]-m[1-side]))/wt.sum(axis=1)
            output.append(x)
        return tuple(output)


def weight_batches(rng,n,*,b=5000,batch=256):
    """Fixed interleaving shared by percentile and studentized methods."""
    for start in range(0,b,batch):
        size=min(batch,b-start)
        yield start,rng.multinomial(n,np.full(n,1/n),size=size),rng.multinomial(n,np.full(n,1/n),size=size)


def bootstrap(lower, upper, rng, *, b=5000, batch=256):
    lower,upper=checked_sample(lower,upper)
    n=lower.shape[1]
    kernel=JointKernel(lower,upper)
    low,high=np.empty((b,10)),np.empty((b,10))
    for start,wt,wa in weight_batches(rng,n,b=b,batch=batch):
        low[start:start+len(wt)],high[start:start+len(wt)]=kernel.statistics(wt,wa)
    return low,high


def quantiles(values):
    values=np.asarray(values)
    b=len(values)
    ranks=np.ceil(np.array([.0025,.9975])*b).astype(int)-1
    return np.sort(values,axis=0)[ranks]


def holm(p, alpha=.05):
    p=np.asarray(p,dtype=float)
    if p.shape!=(10,) or np.any((p<0)|(p>1)) or not np.isfinite(p).all():
        raise ValueError('ten finite p-values required')
    reject=np.zeros(10,bool)
    for j,index in enumerate(np.argsort(p,kind='stable')):
        if p[index]<=alpha/(10-j):reject[index]=True
        else:break
    return reject


def decisions(pplus,pminus,ci,degenerate,observed_lower,observed_upper):
    observed_lower,observed_upper=np.asarray(observed_lower),np.asarray(observed_upper)
    if observed_lower.shape!=(10,) or observed_upper.shape!=(10,) or not np.isfinite([observed_lower,observed_upper]).all() or np.any(observed_lower>observed_upper):
        raise ValueError('ten ordered finite observed bounds required')
    observed_direction=np.where(observed_lower>0,1,np.where(observed_upper<0,-1,0))
    ci=np.asarray(ci).copy()
    p=np.where(ONE_SIDED,pplus,np.minimum(1,2*np.minimum(pplus,pminus)))
    p[(ONE_SIDED & (observed_direction!=1)) | (~ONE_SIDED & (observed_direction==0))]=1
    p[degenerate]=1
    ci[degenerate]=DOMAINS[degenerate]
    reject=holm(p)
    direction=np.where(reject,observed_direction,0)
    above=np.zeros(10,bool);equivalent=np.zeros(10,bool)
    for j,threshold in THRESHOLDS.items():above[j]=not degenerate[j] and ci[j,0]>threshold
    for j in EQUIVALENCE:equivalent[j]=not degenerate[j] and ci[j,0]>-.05 and ci[j,1]<.05
    return {'p':p,'pplus':pplus,'pminus':pminus,'ci':ci,'degenerate':degenerate,
            'reject':reject,'direction':direction,
            'observed_direction':observed_direction,'above':above,'equivalent':equivalent}


def infer(boot_lower,boot_upper,observed_lower,observed_upper):
    low,high=np.asarray(boot_lower),np.asarray(boot_upper)
    if low.shape!=high.shape or low.ndim!=2 or low.shape[1]!=10 or np.any(low>high):
        raise ValueError('expected ordered [B,10] bootstrap bounds')
    if not np.isfinite(low).all() or not np.isfinite(high).all():
        raise ValueError('finite bootstrap values required')
    b=len(low);ql,qh=quantiles(low),quantiles(high)
    unique_low=np.array([len(np.unique(low[:,j])) for j in range(10)])
    unique_high=np.array([len(np.unique(high[:,j])) for j in range(10)])
    degenerate=(unique_low<20)|(unique_high<20)|(ql[0]==ql[1])|(qh[0]==qh[1])
    pplus=(1+(low<=0).sum(axis=0))/(b+1)
    pminus=(1+(high>=0).sum(axis=0))/(b+1)
    return {**decisions(pplus,pminus,np.stack((ql[0],qh[1]),axis=1),degenerate,observed_lower,observed_upper),
            'unique_lower':unique_low,'unique_upper':unique_high}


def assess(result, truth):
    certified=[Fraction(str(x)) for x in truth]
    # Classify nulls, direction, and claim boundaries by certified rationals.
    # Float conversion below is only for comparison with numeric CI endpoints.
    numeric=np.array(list(map(float,certified)))
    null=np.array([x<=0 if ONE_SIDED[j] else x==0 for j,x in enumerate(certified)])
    signs=np.array([(x>0)-(x<0) for x in certified])
    declared=result['reject'] & (result['direction']!=0)
    wrong_direction=declared & ~null & (result['direction']!=signs)
    false_above=np.array([result['above'][j] and certified[j]<=Fraction(str(THRESHOLDS[j])) for j in THRESHOLDS])
    false_equivalent=np.array([result['equivalent'][j] and abs(certified[j])>=Fraction(1,20) for j in EQUIVALENCE])
    coverage=(result['ci'][:,0]<=numeric)&(numeric<=result['ci'][:,1])
    correct_above=np.array([bool(result['above'][j] and certified[j]>Fraction(str(THRESHOLDS[j]))) if j in THRESHOLDS else False for j in range(10)])
    correct_equivalent=np.array([bool(result['equivalent'][j] and abs(certified[j])<Fraction(1,20)) if j in EQUIVALENCE else False for j in range(10)])
    return {'null':null,'false_reject':result['reject']&null,'fwer':bool((result['reject']&null).any()),
            'declared_direction':declared,'family_direction_error':bool((declared&null).any() or wrong_direction.any()),
            'coverage':coverage,'simultaneous_coverage':bool(coverage.all()),
            'false_threshold_or_equivalence':bool(false_above.any() or false_equivalent.any()),
            'correct_direction':declared&~null&~wrong_direction,
            'correct_above':correct_above,'correct_equivalent':correct_equivalent}
