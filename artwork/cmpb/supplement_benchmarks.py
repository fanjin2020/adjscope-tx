"""Panels for the grouped-design, calibration and held-out benchmarks."""
from matplotlib import colors
import numpy as np


LAYOUTS=["n72_s6_m000_g36","n72_s6_m050_g36","n72_s6_m100_g36"]
CASES=["s01","s09","s11","s12","s15","s23"]
ARMS=["estimated_shared","estimated_design","independent_shared","independent_design","fixed_unit","gaussian_unit"]
ARM_LABELS=["Same counts / shared","Same counts / design-specific","Independent / shared",
            "Independent / design-specific","Count / unit","Gaussian / unit"]
LAWS=["matched_gaussian","heteroskedastic_gaussian","matched_student_t5"]


def cage_points(a,data,x,metric,sty,c):
    scale=100 if metric in ("rejection","coverage") else 1.
    v=data[metric].to_numpy(float);err=None
    if metric+"_low" in data:
        err=np.maximum(0,np.array([v-data[metric+"_low"],data[metric+"_high"]-v])*scale)
    elif metric=="bias":err=1.96*data.bias_MCSE.to_numpy(float)
    ok=np.isfinite(v)
    if not ok.any():return
    if err is not None:err=err[...,ok]
    c.interval(a,np.asarray(x)[ok],v[ok]*scale,sty,err,vertical=True)


def s5(p,c):
    z=p("cage_summary");z=z.loc[z.rho_truth.eq(.2)]
    layouts=["actual_linear",*LAYOUTS]
    f,axes=c.make(5,2,2,5.6,c.MOUSE.values(),ncol=3,sharey="row")
    for i,ax in enumerate(axes.flat):
        truth=[0,.3][i//2];amp=[0,.5][i%2]
        for j,(name,sty) in enumerate(c.MOUSE.items()):
            t=z.loc[z.truth.eq(truth)&z["shift"].eq(amp)&z.model.eq(name)].set_index("layout").reindex(layouts)
            cage_points(ax,t,np.arange(4)+(j-2)*.088,"rejection",sty,c)
        ax.set(xticks=range(4),xticklabels=["Observed","Pure","Half mixed","All mixed"],xlim=(-.40,3.40),
               ylabel="Null rejection (%)" if truth==0 else "Power (%)")
        c.panel(ax,"abcd"[i],f"Cage-mean amplitude {amp:g}")
        if truth==0:c.ref(ax,5)
    return f


def s11(p,c):
    z=p("donor_calibration")
    f,axs=c.make(11,2,2,5.8,c.PAIRS.values())
    cfg=[("rejection","quality_zero","Null rejection (%)",5,100),("coverage","quality_zero","95% coverage (%)",95,100),
         ("ratio","quality_zero","RMS SE / empirical SD",1,1),("rejection","delta_two_reference_SD","Two-SD power (%)",None,100)]
    z["ratio"]=z.RMS_SE/z.empirical_SD
    for k,(a,(stat,case,title,r,scale)) in enumerate(zip(axs.flat,cfg)):
        for l,law in enumerate(["matched_gaussian","RIN_heteroskedastic_gaussian","matched_student_t5"]):
            for j,(m,sty) in enumerate(c.PAIRS.items()):
                v=z.loc[z.mean_case.eq(case)&z.error_law.eq(law)&z.method.eq(m),stat].dropna().to_numpy()*scale
                if len(v)!=144:raise ValueError("S11: missing design combinations")
                pos=l+(j-.5)*.36
                ix=((np.arange(len(v))*.61803399)%1-.5)*.18
                c.dots(a,pos+ix,v,sty,5,.27)
                a.boxplot(v,positions=[pos],widths=.25,whis=(0,100),manage_ticks=False,showfliers=False,
                          medianprops={"color":c.INK,"linewidth":1.2},boxprops={"color":sty[1]},
                          whiskerprops={"color":sty[1]},capprops={"color":sty[1]})
        if r is not None:c.ref(a,r)
        a.set(xticks=range(3),xticklabels=["Matched\nGaussian","RIN-dependent\nGaussian","Matched\nStudent t5"],xlim=(-.55,2.55))
        c.panel(a,"abcd"[k],title)
    return f


def s12(p,c):
    z=p("general_calibration");z=z.loc[(z.status=="regular")&(z.error_law=="matched_gaussian")]
    f,(a,b)=c.one_row(12,4.1)
    t=z.loc[z.mean_case=="quality_nonzero_delta_zero"].pivot(index="design",columns="method",values="rejection")
    fs=z.loc[(z.mean_case=="quality_nonzero_delta_zero")&(z.method=="model_based")].set_index("design").loc[t.index,"joint_F_rejection"]
    v=np.column_stack([fs,t.model_based,t.HC3])*100
    a.plot(range(3),v.T,color=c.RULE,alpha=.48,lw=.7,zorder=1)
    for j,sty in enumerate([("Joint F",c.VIOLET,"^",False),*c.PAIRS.values()]):c.dots(a,np.full(len(v),j),v[:,j],sty,14,.65)
    a.set(xticks=[0,1,2],xticklabels=["Joint F","Paired\nmodel-based","Paired\nHC3"],ylabel="Rejection (%)",xlim=(-.3,2.3))
    c.ref(a,5);c.panel(a,"a","Nonzero effects, zero target change")
    for i,case in enumerate(["delta_one_reference_SD","delta_two_reference_SD"]):
        for j,(m,sty) in enumerate(c.PAIRS.items()):
            v=100*z.loc[z.mean_case.eq(case)&z.method.eq(m),"rejection"].to_numpy()
            pos=i*2.6+j
            c.dots(b,pos+np.linspace(-.13,.13,len(v)),v,sty,18,.75)
            b.hlines(np.median(v),pos-.23,pos+.23,color=c.INK,lw=1.6,zorder=4)
    b.set(xticks=[0,1,2.6,3.6],xticklabels=["1 SD\nModel","1 SD\nHC3","2 SD\nModel","2 SD\nHC3"],ylabel="Pointwise power (%)")
    c.panel(b,"b","Known differences")
    return f


def s13(p,c):
    z=p("design_gaussian_summary").merge(p("design_design_diagnostics")[["design","ewi"]],on="design",validate="many_to_one")
    styles={"baseline":c.MOUSE["baseline"],"fixed":c.MOUSE["cage_fixed"],
            "re_known_covariance":("Random intercept / known covariance",c.COPPER,"D",False),
            "mundlak_known_covariance":("Mundlak / known covariance",c.TEAL,"s",False)}
    f,axs=c.make(13,1,2,4.1,styles.values(),ncol=2);a,b=axs.flat
    for m,sty in styles.items():
        t=z.loc[z.model.eq(m)].dropna(subset=["empirical_positive_gamma_bias","analytic_positive_gamma_bias"])
        c.dots(a,t.analytic_positive_gamma_bias,t.empirical_positive_gamma_bias,sty,19,.68)
        u=t.loc[t.scenario.eq(5)]
        c.dots(b,u.ewi,u.empirical_positive_gamma_bias,sty,20,.76)
    lo,hi=a.get_xlim();a.plot([lo,hi],[lo,hi],ls=":",color=c.MID)
    a.set(xlabel="Analytical coefficient bias",ylabel="Mean simulated coefficient bias")
    b.set(xlabel="Within-group information ratio",ylabel="Mean simulated coefficient bias");c.ref(b,0)
    c.panel(a,"a","Eligible shifted conditions");c.panel(b,"b","Fixed generating condition")
    return f


def s14(p,c):
    z=p("paired_count_summary")
    f,axs=c.make(14,2,2,5.55,c.PAIRS.values(),sharey=True)
    for j,mode in enumerate(["shared","design_specific"]):
        for m,sty in c.PAIRS.items():
            t=z.loc[z.weight_mode.eq(mode)&z.test.eq(m)]
            if len(t)!=24:raise ValueError("S14 needs all 24 scenarios")
            c.dots(axs[0,j],t.coverage95*100,t.fdp_planned_050*100,sty,25,.82)
            c.dots(axs[1,j],t.fdp_planned_050*100,t.fdp_retained_050*100,sty,25,.82)
        for i in [0,1]:
            a=axs[i,j];c.ref(a,5);c.ref(a,95 if i==0 else 5,True)
            c.panel(a,"abcd"[2*i+j],["Shared weights","Design-specific weights"][j])
            a.set_xlabel("Pointwise interval coverage (%)" if i==0 else "Planned-family FDR (%)")
            if j==0:a.set_ylabel("Planned-family FDR (%)" if i==0 else "Retained-family FDR (%)")
        axs[1,j].plot([0,16],[0,16],color=c.MID,ls=":",lw=.85)
        axs[0,j].set_xlim(94.2,96);axs[1,j].set_xlim(-.5,16.5)
    return f


def s15(p,c):
    z=p("paired_tail_summary")
    f,axs=c.make(15,2,3,6.25,c.PAIRS.values(),sharey=True,sharex=True)
    for j,(a,sc) in enumerate(zip(axs.flat,CASES)):
        t=z.loc[z.scenario.eq(sc)]
        for k,(m,sty) in enumerate(c.PAIRS.items()):
            u=t.loc[t.test.eq(m)].set_index("arm").loc[ARMS]
            c.interval(a,u.fdp_planned_050*100,np.arange(6)+(k-.5)*.25,sty,
                       [(u.fdp_planned_050-u.fdp_planned_050_ci_low)*100,(u.fdp_planned_050_ci_high-u.fdp_planned_050)*100])
        c.ref(a,5,True);c.gridx(a);a.set(ylim=(5.58,-.58),xlim=(-.5,max(20,100*z.fdp_planned_050_ci_high.max()+.5)),
                                          xticks=[0,5,10,15,20])
        a.set_yticks(range(6),ARM_LABELS,fontsize=7.6)
        if j>=3:a.set_xlabel("BH FDR (%)")
        c.panel(a,"abcdef"[j],f"{sc}  /  n = {int(t.n.iloc[0])}")
    return f


def s16(p,c):
    z=p("cage_summary");z=z.loc[z.layout.eq("actual_linear")&z.truth.eq(0)]
    f,axs=c.make(16,2,3,5.6,c.MOUSE.values(),ncol=3,sharey="col")
    for k,a in enumerate(axs.flat):
        row,j=divmod(k,3);amp=[0,.5][row]
        metric=["bias","rejection","mean_width"][j]
        for i,(m,sty) in enumerate(c.MOUSE.items()):
            v=z.loc[z["shift"].eq(amp)&z.model.eq(m)].sort_values("rho_truth")
            cage_points(a,v,v.rho_truth.to_numpy()+(i-2)*.009,metric,sty,c)
        c.panel(a,"abcdef"[k],["Genotype bias","Null rejection (%)","Mean interval width"][j])
        a.set(xlim=(-.045,.245),xticks=[0,.2],xticklabels=["0","0.20"],xlabel="Residual correlation")
        if j==0:a.set_ylabel(f"Cage-mean amplitude {amp:g}")
        if j<2:c.ref(a,[0,5][j])
    return f


def s17(p,c):
    z=p("cage_summary");z=z.loc[z.layout.isin(LAYOUTS)&z.rho_truth.eq(.2)&z["shift"].eq(0)]
    f,axs=c.make(17,2,2,5.45,c.MOUSE.values(),ncol=3)
    for k,(a,metric,truth,title) in enumerate(zip(axs.flat,["rejection","coverage","rejection","mean_width"],[0,0,.3,.3],
                                                   ["Null rejection (%)","95% coverage under the null (%)","Power at a genotype effect of 0.3 (%)","Mean interval width at effect 0.3"])):
        for i,(m,sty) in enumerate(c.MOUSE.items()):
            t=z.loc[z.model.eq(m)&z.truth.eq(truth)].set_index("layout").loc[LAYOUTS]
            cage_points(a,t,np.arange(3)+(i-2)*.078,metric,sty,c)
        a.set(xticks=range(3),xticklabels=["Pure","Half mixed","All mixed"],xlim=(-.35,2.35))
        if truth==0:c.ref(a,5 if metric=="rejection" else 95)
        c.panel(a,"abcd"[k],title)
    return f


def s18(p,c):
    z=p("general_calibration");z=z.loc[z.status.eq("regular")&z.mean_case.eq("quality_zero")]
    f,axs=c.make(18,2,3,5.2,c.PAIRS.values(),sharex=True,sharey="row")
    for j,law in enumerate(LAWS):
        for k,(metric,target) in enumerate([("rejection",5),("coverage",95)]):
            a=axs[k,j]
            for m,sty in c.PAIRS.items():
                t=z.loc[z.error_law.eq(law)&z.method.eq(m)]
                c.dots(a,t.max_leverage,t[metric]*100,sty,20,.80)
                if j==1:
                    r=t.loc[t.n.eq(80)&t.leverage.eq("ordinary")&t.weights.eq("uniform")&np.isclose(t.partial_correlation,.3)]
                    if len(r)!=1:raise ValueError("Missing highlighted design")
                    a.scatter(r.max_leverage,r[metric]*100,s=68,facecolor="none",edgecolor=c.INK,linewidths=.8,zorder=4)
            c.ref(a,target);a.set(xlim=(.03,1.02),xticks=[.1,.5,.9])
            if k==1:a.set_xlabel("Maximum leverage")
            if j==0:a.set_ylabel(["Null rejection (%)","95% coverage (%)"][k])
            c.panel(a,"abcdef"[3*k+j],["Matched Gaussian","Heteroskedastic Gaussian","Matched Student t5"][j] if k==0 else "")
    return f


def s19(p,c):
    z=p("mouse_summary");rat=p("mouse_se_ratios");comp=p("mouse_comparisons")
    arms=["baseline","cage_correlation","dream_shared","dream_native","cage_fixed","mundlak_shared","mundlak_native"]
    labels=["No cage","Common correlation","dream / shared","dream / design-specific","Cage fixed effects",
            "Mundlak / shared","Mundlak / design-specific"]
    t=z.pivot(index="model",columns="spec",values="significant_background").loc[arms,c.SPECS]
    f,axs=c.make(19,2,2,7.0,gridspec_kw={"width_ratios":[1.15,1]})
    a,b,d,e=axs.flat
    cmap=colors.LinearSegmentedColormap.from_list("counts",["#F0F5F5","#BBD9D7","#4D9698","#174A65"])
    a.pcolormesh(np.arange(7)-.5,np.arange(8)-.5,t.to_numpy(),cmap=cmap,shading="flat")
    a.set_ylim(6.5,-.5);a.grid(False)
    for i in range(7):
        for j in range(6):
            v=int(t.iloc[i,j]);base=(v-t.min().min())/(t.max().max()-t.min().min())
            a.text(j,i,str(v),ha="center",va="center",fontsize=7.1,color=c.WHITE if base>.66 else c.INK)
    a.set_yticks(range(7),labels,fontsize=7.3)
    a.set_xticks(range(6),["W1","W2","W3","C1","C2","C3"],fontsize=7.4)
    a.axvline(2.5,color="white",lw=1.6);c.panel(a,"a","Discoveries per 13,312 genes")
    for i,m in enumerate(arms[1:]):
        v=rat.loc[rat.model.eq(m)].set_index("spec").loc[c.SPECS,"SE_ratio"]
        for j,(col,mk) in enumerate([(c.BLUE,"o"),(c.TEAL,"s")]):
            c.dots(b,v.iloc[3*j:3*j+3],i+np.linspace(-.125,.125,3)+(.075 if j else -.075),("",col,mk,j==0),15)
    b.set_yticks(range(6),labels[1:],fontsize=7.3);b.set_ylim(5.55,-.55);c.gridx(b);c.ref(b,1,True)
    c.panel(b,"b","SE relative to no cage");b.set_xlabel("Median paired SE ratio")
    sty=[("Whole section",c.BLUE,"o",True),("Cortex",c.TEAL,"s",False)]
    for j,k in enumerate(c.SPECS):
        c.dots(d,[t.loc["cage_fixed",k]],[t.loc["mundlak_native",k]],sty[j//3],30)
    xx=np.r_[t.loc["cage_fixed"],t.loc["mundlak_native"]];lims=[xx.min()*.9,xx.max()*1.08]
    d.plot(lims,lims,ls=":",color=c.MID);d.set(xlabel="Cage-fixed discoveries",ylabel="Mundlak discoveries")
    c.panel(d,"c","Design-specific Mundlak fit")
    for i,m in enumerate(["cage_fixed","dream_native"]):
        v=comp.loc[comp.model.eq("mundlak_native")&comp.reference.eq(m)].set_index("spec").loc[c.SPECS,"median_SE_ratio"]
        for j in range(2):c.dots(e,v.iloc[3*j:3*j+3],i+np.linspace(-.10,.10,3)+(.075 if j else -.075),sty[j],21)
    e.set_yticks([0,1],["Cage fixed effects","dream / design-specific"],fontsize=7.3);e.set_ylim(1.48,-.48);c.gridx(e);c.ref(e,1,True)
    e.set_xlabel("Median Mundlak / comparator SE");c.panel(e,"d","Matched-gene SE ratios")
    d.legend(handles=[c.key(*v) for v in sty],loc="upper left",fontsize=7.3,frameon=False)
    return f


def s20(p,c):
    dg=p("design_design_diagnostics");emp=p("design_empirical_design_diagnostics").iloc[0]
    counts=p("design_counts_summary");hold=p("design_heldout_rule_evaluation")
    f,axs=c.make(20,2,2,7.4,gridspec_kw={"height_ratios":[.80,1.2]});a,b,d,e=axs.flat
    for size,sty in zip([12,18,36],[("12 cages",c.BLUE,"o",True),("18 cages",c.TEAL,"s",False),("36 cages",c.VIOLET,"^",False)]):
        z=dg.loc[dg.groups.eq(size)].sort_values("ewi")
        a.plot(z.ewi,z.conditional_ewi,color=sty[1],lw=.7);c.dots(a,z.ewi,z.conditional_ewi,sty,24)
    c.dots(a,[emp.ewi],[emp.conditional_ewi],("Observed",c.COPPER,"D",False),40)
    a.plot([0,1],[0,1],":",color=c.MID,lw=.8);a.set(xlabel="Unadjusted information ratio",ylabel="Conditional information ratio")
    a.legend(handles=[c.key(*v) for v in [("12 cages",c.BLUE,"o",True),("18 cages",c.TEAL,"s",False),
             ("36 cages",c.VIOLET,"^",False),("Observed",c.COPPER,"D",False)]],loc="upper left",frameon=False,fontsize=7,ncol=2,columnspacing=.6,handlelength=.65)
    c.panel(a,"a","Cage allocation")
    mlookup={"dream_native":"dream","mundlak_native":"mundlak_dream"}
    for j,m in enumerate(["baseline","cage_correlation","dream_native","cage_fixed","mundlak_native"]):
        sty=c.MOUSE[mlookup.get(m,m)]
        z=counts.loc[counts.design.eq("k18_w1")&counts.model.eq(m)].set_index("scenario").loc[[4,5]]
        xx=np.array([0,1])+(j-2)*.029
        b.plot(xx,z.empirical_fdr*100,color=sty[1],lw=1.1)
        c.dots(b,xx,z.empirical_fdr*100,sty,29)
    c.ref(b,5);b.set(xticks=[0,1],xticklabels=["0","0.5"],xlim=(-.2,1.2),xlabel="Cage-mean amplitude",ylabel="Empirical FDR (%)")
    c.panel(b,"b","Within-group information = 0.333")
    b.legend(handles=[c.key(*v) for v in c.MOUSE.values()],loc="upper left",fontsize=6.8,frameon=False,handlelength=.75,labelspacing=.15)
    order=[f"k18_w{i}" for i in range(4)];pos=hold.set_index(["design","scenario"])
    statuses={"within_effect_not_estimable":0,"no_supported_selection":1,"conditionally_eligible":2}
    grid=np.array([[statuses[pos.loc[(x,i),"status"]] for i in range(8)] for x in order])
    d.pcolormesh(np.arange(9)-.5,np.arange(5)-.5,grid,
                 cmap=colors.ListedColormap(["#E4E9EC","#F5E4D7","#BDDCD6"]),vmin=0,vmax=2,shading="flat")
    d.set_ylim(3.5,-.5);d.grid(False)
    short={"baseline":"B","cage_correlation":"C","dream_native":"D","cage_fixed":"F","mundlak_native":"M"}
    for i,design in enumerate(order):
        for j in range(8):
            r=pos.loc[(design,j)]
            txt=short[r.model] if grid[i,j]==2 else ("NE" if grid[i,j]==0 else "A")
            d.text(j,i,txt,ha="center",va="center",fontweight="bold",color=c.INK,fontsize=8)
    d.set(xticks=range(8),xticklabels=np.arange(1,9),yticks=range(4),yticklabels=["0","1/3","2/3","1"],
          xlabel="Generating scenario",ylabel="Unadjusted information ratio")
    c.panel(d,"c","Decisions in all 32 cases")
    selected=hold.loc[hold.status.eq("conditionally_eligible")].sort_values(["design","scenario"])
    if len(selected)!=16:raise ValueError("Unexpected number of held-out selections")
    labs=[]
    for i,r in enumerate(selected.itertuples()):
        sty=c.MOUSE[mlookup.get(r.model,r.model)]
        c.interval(e,[100*r.heldout_fdr],[i],sty,np.array([[r.heldout_fdr-r.heldout_fdr_ci_lower],[r.heldout_fdr_ci_upper-r.heldout_fdr]])*100)
        if r.heldout_fdr_mc_upper>r.screening_mc_upper_limit:
            e.plot(100*r.heldout_fdr_mc_upper,i,marker="|",ms=8,mew=1.35,color=c.COPPER,zorder=4)
        labs.append(f"{int(r.design[-1])}/3 : {int(r.scenario)+1}")
    e.set_yticks(range(len(labs)),labs,fontsize=7);e.set_ylim(len(labs)-.35,-.65)
    e.set_xlabel("Held-out FDR (%)");c.gridx(e);c.ref(e,5,True);e.axvline(7.5,color=c.COPPER,ls=":",lw=1)
    c.panel(e,"d","Selected models and uncertainty")
    return f
