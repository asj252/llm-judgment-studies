"""Reviewed candidate: paired cluster projection SE and percentile-t inversion.

This is not a claim that the cited asymptotic results guarantee this protocol's
missing/bounded ten-family protection. The frozen simulations decide that.
No CI clipping; nonfinite or inverted CIs become p=1 / full-domain intervals.
"""
import numpy as np
from . import core


def _linear_variance(weights,vector):
    n=weights.sum(axis=1)
    mean=core._weighted_mean(weights,vector)
    return np.sum(weights*(vector-mean[:,None])**2,axis=1)/(n*(n-1))


def statistics_and_se(kernel,weights_ac,weights_bd):
    wt,wa=np.atleast_2d(weights_ac).astype(float),np.atleast_2d(weights_bd).astype(float)
    nt,na=wt.sum(axis=1),wa.sum(axis=1)
    if np.any(nt<=1) or np.any(na<=1):raise ValueError('at least two actual clusters required')
    means=kernel.statistics(wt,wa);ses=[]
    projects=[((wa@lo)/na[:,None],(wt@lo.T)/nt[:,None],
               (wa@hi)/na[:,None],(wt@hi.T)/nt[:,None]) for lo,hi in kernel.kernels]
    for side in (0,1):
        variance=np.empty_like(means[side])
        for j,first,second in ((0,2,None),(3,1,0),(4,2,1),(5,3,2),(6,4,2),(7,5,2),(8,6,2)):
            pc,pd=projects[first][2*side:2*side+2]
            if second is not None:
                oc,od=projects[second][2*(1-side):2*(1-side)+2];pc,pd=pc-oc,pd-od
            pc,pd=pc/2,pd/2
            center=np.sum(pc*wt,axis=1)/nt
            variance[:,j]=np.sum(wt*(pc-center[:,None])**2,axis=1)/(nt*(nt-1))+np.sum(wa*(pd-center[:,None])**2,axis=1)/(na*(na-1))
        lo,hi=kernel.lower,kernel.upper
        ac=(lo[0,:,1,5]-hi[0,:,0,5]) if side==0 else (hi[0,:,1,5]-lo[0,:,0,5])
        bd=(hi[1,:,1,5]-lo[1,:,0,5]) if side==0 else (lo[1,:,1,5]-hi[1,:,0,5])
        variance[:,1]=_linear_variance(wt,ac)
        variance[:,2]=variance[:,1]+_linear_variance(wa,bd)
        p=core.endpoint_bounds(lo[0,:,1,5],hi[0,:,1,5]);m=core.endpoint_bounds(lo[0,:,1,9],hi[0,:,1,9])
        variance[:,9]=_linear_variance(wt,p[side]-m[1-side])
        ses.append(np.sqrt(variance))
    return means,tuple(ses)


def bootstrap(lower,upper,rng,*,b=5000,batch=256):
    kernel=core.JointKernel(lower,upper);n=kernel.lower.shape[1]
    means=[np.empty((b,10)),np.empty((b,10))];ses=[np.empty((b,10)),np.empty((b,10))]
    for start,wt,wa in core.weight_batches(rng,n,b=b,batch=batch):
        mean,se=statistics_and_se(kernel,wt,wa)
        for side in (0,1):means[side][start:start+len(wt)]=mean[side];ses[side][start:start+len(wt)]=se[side]
    return tuple(means),tuple(ses)


def infer(boot_lower,boot_upper,se_lower,se_upper,observed_lower,observed_upper,observed_se_lower,observed_se_upper):
    base=core.infer(boot_lower,boot_upper,observed_lower,observed_upper)
    boot=(np.asarray(boot_lower),np.asarray(boot_upper));ses=(np.asarray(se_lower),np.asarray(se_upper))
    observed=(np.asarray(observed_lower),np.asarray(observed_upper));observed_se=(np.asarray(observed_se_lower),np.asarray(observed_se_upper))
    if any(s.shape!=boot[0].shape for s in ses) or any(s.shape!=(10,) for s in observed_se):raise ValueError('SE shape mismatch')
    invalid_observed=np.any([~np.isfinite(s)|(s<=0) for s in observed_se],axis=0)
    invalid_boot=np.any([np.any(~np.isfinite(s)|(s<=0),axis=0) for s in ses],axis=0)
    ts=[np.divide(x-o,se,out=np.zeros_like(x),where=np.isfinite(se)&(se>0)) for x,o,se in zip(boot,observed,ses)]
    qt=[core.quantiles(t) for t in ts]
    distinct=[np.array([len(np.unique(t[:,j])) for j in range(10)]) for t in ts]
    invalid_t=(distinct[0]<20)|(distinct[1]<20)|(qt[0][0]==qt[0][1])|(qt[1][0]==qt[1][1])
    with np.errstate(over='ignore',invalid='ignore'):
        ci=np.stack((observed[0]-qt[0][1]*observed_se[0],observed[1]-qt[1][0]*observed_se[1]),axis=1)
    invalid_ci=~np.isfinite(ci).all(axis=1)|(ci[:,0]>ci[:,1])
    degenerate=base['degenerate']|invalid_observed|invalid_boot|invalid_t|invalid_ci
    observed_t=[np.divide(x,se,out=np.zeros_like(x),where=np.isfinite(se)&(se>0)) for x,se in zip(observed,observed_se)]
    b=len(boot[0]);pplus=(1+(ts[0]>=observed_t[0]).sum(axis=0))/(b+1);pminus=(1+(ts[1]<=observed_t[1]).sum(axis=0))/(b+1)
    return {**core.decisions(pplus,pminus,ci,degenerate,*observed),
            'unique_lower':base['unique_lower'],'unique_upper':base['unique_upper'],
            'unique_t_lower':distinct[0],'unique_t_upper':distinct[1],
            'failure_original_degeneracy':base['degenerate'],'failure_observed_se':invalid_observed,
            'failure_bootstrap_se':invalid_boot,'failure_studentized_distribution':invalid_t,'failure_ci':invalid_ci}
