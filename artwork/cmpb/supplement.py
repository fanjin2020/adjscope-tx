"""Draw the 20 CMPB supplementary plates from a verified manuscript CSV bundle."""
from pathlib import Path
import argparse
import gc
import json
import tempfile
from importlib.metadata import version

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import colors, font_manager
from matplotlib.lines import Line2D
from matplotlib.transforms import Bbox
import numpy as np
import pypdfium2 as pdfium
from pypdf import PdfReader

from adjscope_tx.publication import Bundle
from adjscope_tx.storage import separate_output, sha256
from .redraw_figures import INK, SUB, MID, GRID, RULE, BLUE, TEAL, COPPER, WHITE, STYLE
from .figure_data import SPECS
from .submission_pdf import edge_pixels, render
from . import supplement_benchmarks as bm

VIOLET = "#827094"
T = ["Whole section / continuous age", "Whole section / grouped age", "Whole section / grouped age + slide",
     "Cortex / continuous age", "Cortex / grouped age", "Cortex / grouped age + slide"]
SHORT = ["Continuous age", "Grouped age", "Grouped age + slide"]
PAIRS = {"model_based": ("Model-based", BLUE, "o", True), "HC3": ("HC3", COPPER, "s", False)}
MOUSE = {"baseline": ("No cage", MID, "^", False), "cage_correlation": ("Common correlation", VIOLET, "v", False),
         "dream": ("Random intercept (dream)", COPPER, "D", False),
         "cage_fixed": ("Cage fixed effects", BLUE, "o", False), "mundlak_dream": ("Mundlak", TEAL, "s", False)}
TITLES = ["Donor-level tissue quality", "Astrocyte coefficients in three selected genes",
          "Mouse panel consistency across 18 specifications", "Cage correlation and genotype precision",
          "Cage allocation and genotype testing", "Coefficient and precision changes across cell contexts",
          "Predicted and observed precision costs", "Joint quality tests and paired target tests",
          "Paired inference with and without covariance", "Sources of change among baseline discoveries",
          "Calibration on donor-conditioned designs", "Cancellation and power in fixed designs",
          "Analytical and simulated cage-mean bias", "Paired-null calibration in count data",
          "Six controls for the extreme tail", "Cage means and residual correlation",
          "Genotype overlap at fixed sample size", "Paired-test calibration across error laws",
          "Seven fits on the same mouse transcriptomes", "Held-out screening on cage allocations"]
SOURCES = ["S5.5","S8.2","S12, S13","S15","S17.1","S4","S16","S7, S20.1","S20.5",
           "S4.4","S7, S20.1","S20.5","S21.1, S21.3, S21.8","S22.1","S23.1","S17.1",
           "S17.1","S20.5","S12.7, S12.8","S21.1, S21.2, S21.4, S21.7"]


def key(label, color, marker, hollow=False):
    return Line2D([], [], linestyle="none", marker=marker, markersize=5.5,
                  markerfacecolor=WHITE if hollow else color, markeredgecolor=color, label=label)


def make(n, rows, cols, h, keys=(), ncol=4, **opts):
    fig = plt.figure(figsize=(7.30, h), dpi=130)
    top = .45
    fig.text(.028, 1-.23/h, "S"+str(n), fontsize=11, fontweight="bold", color=TEAL, va="center")
    fig.text(.108, 1-.23/h, TITLES[n-1], fontsize=12, fontweight="bold", color=INK, va="center")
    fig.add_artist(Line2D([.028,.974],[1-.41/h]*2,transform=fig.transFigure,color=RULE,lw=.65))
    if keys:
        handles=[key(*v) for v in keys]
        fig.legend(handles=handles, loc="upper left", bbox_to_anchor=(.025,1-.45/h),
                   ncol=min(len(handles),ncol), borderaxespad=0, frameon=False, handlelength=1.1,
                   handletextpad=.4, columnspacing=1.45, fontsize=8, labelspacing=.45)
        top += .26*np.ceil(len(handles)/ncol)+.05
    fig.set_layout_engine("constrained",rect=(.017,.025,.966,1-top/h-.045),
                          h_pad=.10,w_pad=.09,hspace=.05,wspace=.045)
    axes=fig.subplots(rows,cols,squeeze=False,**opts)
    for ax in axes.flat:
        ax.spines[["right","top"]].set_visible(False)
        ax.grid(axis="y",color=GRID,lw=.6)
        ax.tick_params(pad=3)
    return fig,axes


def panel(ax,letter,title):
    ax.set_title("     "+title.replace("\n","\n     "),loc="left",y=1.0,pad=9,fontsize=9.4,fontweight="bold",color=INK)
    ax.annotate(letter,(0,1),xycoords="axes fraction",xytext=(-1,9+11*title.count("\n")),textcoords="offset points",
                ha="left",va="baseline",color=TEAL,fontweight="bold",fontsize=10.3,annotation_clip=False)


def gridx(ax):
    ax.grid(False)
    ax.grid(axis="x",color=GRID,lw=.6)


def ref(ax,value,vertical=False):
    call=ax.axvline if vertical else ax.axhline
    call(value,color=MID,lw=.85,ls=(0,(3.5,2.6)),zorder=1.4)


def dots(ax,x,y,sty,size=22,alpha=.90):
    _,col,mk,hollow=sty
    ax.scatter(x,y,s=size,marker=mk,edgecolors=col,facecolors=WHITE if hollow else col,
               linewidths=.72 if hollow else .35,alpha=alpha,zorder=3)


def interval(ax,x,y,sty,err=None,vertical=False):
    _,c,m,hollow=sty
    ax.errorbar(x,y,**({"yerr":err} if vertical else {"xerr":err}),fmt=m,
                color=c,mfc=WHITE if hollow else c,mec=c,mew=.78,ms=4.5,
                ls="none",elinewidth=.88,capsize=2,zorder=3)


def spec_ticks(ax):
    ax.set_yticks(np.arange(6),T,fontsize=7.7)
    ax.set_ylim(5.6,-.6)
    gridx(ax)


def s1(p):
    z=p("donors")
    styles=[("No dementia",BLUE,"o",True),("Dementia",TEAL,"D",False)]
    f,axs=make(1,1,3,3.6,styles)
    for a,k,col,lab in zip(axs.flat,"abc",["PMI","RIN","pH"],["Postmortem interval (h)","Frontal-pole RIN","CSF pH"]):
        panel(a,k,lab)
        groups=[]
        for j,(group,sty) in enumerate(zip(["No_dementia","Dementia"],styles)):
            v=z.loc[z.clinical_group==group,col].dropna().to_numpy()
            groups.append(len(v))
            a.boxplot(v,positions=[j],widths=.44,showfliers=False,patch_artist=True,manage_ticks=False,
                      boxprops=dict(facecolor=colors.to_rgba(sty[1],.15),edgecolor=sty[1]),
                      medianprops=dict(color=INK,lw=1.25),whiskerprops=dict(color=MID),capprops=dict(color=MID))
            jx=((np.arange(len(v))*.61803399)%1-.5)*.28
            dots(a,j+jx,v,sty,12,.74)
        a.set(xticks=[0,1],xticklabels=[f"No dementia\nn = {groups[0]}",f"Dementia\nn = {groups[1]}"],xlim=(-.55,1.55))
    return f


def s2(p):
    z=p("astrocyte")
    stages=["clinical_status","clinical_status_adjusted_for_braak","braak_same_clinical_population"]
    genes=["GFAP","GSDMD","IGFBP5"]
    styles=[("Base",BLUE,"o",True),("Quality adjusted",TEAL,"D",False)]
    f,axs=make(2,1,3,3.35,styles,sharex=True,sharey=True)
    for a,k,cl,title in zip(axs.flat,"abc",stages,["Clinical status","Status given Braak","Braak stage"]):
        panel(a,k,title)
        for j,(m,sty) in enumerate(zip(["base","quality"],styles)):
            t=z.loc[(z.contrast==cl)&(z.model==m)].set_index("gene_symbol").loc[genes]
            interval(a,t.beta,np.arange(3)+(j-.5)*.22,sty,[t.beta-t.low,t.high-t.beta])
        a.set_yticks(range(3),genes,fontstyle="italic")
        a.set_ylim(2.55,-.55);a.set_xlabel(r"Coefficient (log$_2$)")
        ref(a,0,True);gridx(a)
    return f


def s3(p):
    z=p("mouse_consistency");v=p("mouse_focal")
    f,(a,b)=one_row(3,3.55)
    n=z.significant.value_counts().reindex(range(19),fill_value=0)
    a.bar(n.index,n,color=BLUE,width=.75,zorder=2)
    a.set(xlabel="Significant specifications (of 18)",ylabel="Genes",xticks=np.arange(0,19,3))
    panel(a,"a","All testable panel genes")
    genes=["GFAP","GSDMD","IGFBP5","EMP3"]
    ns=v.assign(hit=v.q_three_model_joint.lt(.05)).groupby("gene_symbol").hit.sum().loc[genes]
    b.barh(range(4),ns,color=[TEAL]*3+[MID],height=.55,zorder=2)
    for i,value in enumerate(ns): b.text(value+.4,i,str(value),va="center",fontsize=8)
    b.set_yticks(range(4),["Gfap","Gsdmd","Igfbp5","Emp3"],fontstyle="italic")
    b.set(ylim=(3.6,-.6),xlim=(0,20),xticks=[0,6,12,18],xlabel="Significant specifications (of 18)")
    gridx(b);panel(b,"b","Examples from the same fits")
    return f


def one_row(n,h,keys=()):
    f,axs=make(n,1,2,h,keys)
    return f,list(axs.flat)


def s4(p):
    z=p("icc_density");q=p("icc_strata")
    bins=sorted(q.ICC_bin.unique(),key=lambda v:0 if v.startswith("<") else 1 if v.startswith("0.01") else 2 if v.startswith("0.10") else 3)
    styles=[("Shared weights",BLUE,"o",True),("Design-specific weights",TEAL,"s",False)]
    f,axs=make(4,4,3,8.05,styles,gridspec_kw={"height_ratios":[1,.71,1,.71]})
    hs=[];cmap=colors.LinearSegmentedColormap.from_list("density",["#E6F1F3","#86BEB9","#247C85","#163F65"])
    for i,spec in enumerate(SPECS):
        row,col=2*(i//3),i%3;a,b=axs[row,col],axs[row+1,col];x=z.loc[z.spec==spec]
        h=a.hexbin(x.ICC,x.SE_ratio,gridsize=26,mincnt=1,cmap=cmap,linewidths=0,zorder=2)
        hs.append(h);panel(a,"abcdef"[i],("Whole section" if i<3 else "Cortex")+":\n"+SHORT[col])
        a.set_xlabel("Conditional ICC");a.set_ylabel("SE ratio" if col==0 else "")
        for policy,sty in zip(["shared","native"],styles):
            t=q.loc[(q.spec==spec)&(q.weight_policy==policy)].set_index("ICC_bin").loc[bins]
            b.plot(range(4),t.median_SE_ratio,color=sty[1],lw=.9)
            dots(b,range(4),t.median_SE_ratio,sty,15)
        b.set_xticks(range(4),["<0.01","0.01–0.10","0.10–0.20","≥0.20"],rotation=27,ha="right",fontsize=7)
        b.set_ylabel("Median SE ratio" if col==0 else "");ref(a,1);ref(b,1)
    for axgroup in [axs[[0,2],:].flat, axs[[1,3],:].flat]:
        group=list(axgroup)
        lo=min(ax.get_ylim()[0] for ax in group);hi=max(ax.get_ylim()[1] for ax in group)
        for ax in group:ax.set_ylim(lo,hi)
    norm=colors.LogNorm(1,max(float(h.get_array().max()) for h in hs))
    for h in hs:h.set_norm(norm)
    cb=f.colorbar(hs[0],ax=axs.ravel().tolist(),location="bottom",aspect=55,shrink=.58,pad=.025)
    cb.solids.set_rasterized(False)
    cb.set_label("Genes per hexagon (logarithmic scale)")
    return f


def s6(p):
    z=p("human_contexts").sort_values("context");y=np.arange(len(z))
    f,axs=make(6,1,3,6.4,[("Available records","#A7BBC6","s",False),("Baseline discoveries",TEAL,"s",False)],
               sharey=True,gridspec_kw={"width_ratios":[1,1,.85]})
    for a,field,sty,title,k in zip(axs.flat[:2],["log_abs_beta_ratio","minus_log_SE_ratio"],
            [("Coefficient",BLUE,"o",True),("Precision",TEAL,"s",False)],["Coefficient change","Precision change"],"ab"):
        m=z[field+"_median"]
        interval(a,m,y,sty,[m-z[field+"_q25"],z[field+"_q75"]-m]);ref(a,0,True);gridx(a)
        a.set_xlabel("Log absolute ratio" if k=="a" else "Negative log SE ratio");panel(a,k,title)
    a=axs.flat[2];a.barh(y,z.available,color="#A7BBC6",height=.65);a.barh(y,z.selected,color=TEAL,height=.65)
    a.set_xlabel("Records");gridx(a);panel(a,"c","Test availability")
    axs.flat[0].set_yticks(y,z.context.str.replace("_"," ",regex=False),fontsize=7.8);axs.flat[0].set_ylim(len(z)-.4,-.6)
    return f


def s7(p):
    d=p("design_display").set_index("spec").loc[SPECS];z=p("design_errors").set_index("spec").loc[SPECS]
    styles=[("Design prediction",BLUE,"D",True),("Observed median and IQR",TEAL,"o",False)]
    f,axs=make(7,1,2,4.15,styles,sharey=True,gridspec_kw={"width_ratios":[1.08,1]})
    a,b=axs.flat;y=np.arange(6)
    for i,r in enumerate(d.itertuples()):
        a.plot([r.predicted,r.observed_median],[i,i],color=RULE,lw=1)
    interval(a,d.observed_median,y,styles[1],[d.observed_median-d.observed_q25,d.observed_q75-d.observed_median])
    dots(a,d.predicted,y,styles[0],28)
    for i,r in enumerate(z.itertuples()):
        b.hlines(i,r.p05,r.p95,color=MID,lw=.9)
        b.hlines(i,r.q25,r.q75,color=TEAL,lw=5)
        b.plot(r.median,i,"|",ms=8,color=INK,mew=1.4)
    spec_ticks(a);gridx(b);ref(b,0,True)
    panel(a,"a","Design and fitted ratios");panel(b,"b","Gene-wise deviations")
    a.set_xlabel("Genotype SE ratio");b.set_xlabel("Log(observed / predicted)")
    return f


def s8(p):
    z=p("donor_calibration");z=z.loc[z.error_law=="matched_gaussian"]
    f,(a,b)=one_row(8,3.95,PAIRS.values())
    for m,sty in PAIRS.items():
        t=z.loc[(z.mean_case=="quality_nonzero_delta_zero")&(z.method==m)]
        dots(a,t.joint_F_rejection*100,t.rejection*100,sty,17,.65)
    ref(a,5);a.set(xlabel="Joint quality F-test rejection (%)",ylabel="Paired-test rejection (%)");panel(a,"a","Cancellation of paired change")
    t=z.loc[(z.mean_case=="quality_zero")&(z.method=="HC3")]
    dots(b,t.max_leverage,t.RMS_SE/t.empirical_SD,PAIRS["HC3"],18,.65)
    b.set(xlabel="Maximum leverage",ylabel="HC3 RMS SE / empirical SD");ref(b,1);panel(b,"b","HC3 standard-error scale")
    return f


def s9(p):
    # Each line is one design; the three comparisons use the same response draws.
    z=p("general_calibration")
    z=z.loc[(z.status=="regular")&(z.error_law=="matched_gaussian")]
    methods=["model_based","HC3","independence_comparator"]
    comp=("Covariance omitted",MID,"^",True)
    f,(a,b)=one_row(9,4.05,[*PAIRS.values(),comp])
    for ax,case,k,title in [(a,"quality_zero","a","Zero coefficient difference"),(b,"delta_two_reference_SD","b","Two-reference-SD difference")]:
        t=z.loc[z.mean_case==case].pivot(index="design",columns="method",values="rejection")
        if t.shape!=(30,3) or t.isna().any().any():raise ValueError("S9 requires 30 complete matched designs.")
        rates=100*t.loc[:,methods].to_numpy()
        ax.plot(range(3),rates.T,color=RULE,lw=.55,alpha=.52,zorder=1)
        for j,sty in enumerate([*PAIRS.values(),comp]):
            dots(ax,np.full(len(rates),j),rates[:,j],sty,14,.55)
            med=float(np.median(rates[:,j]))
            ax.hlines(med,j-.18,j+.18,color=INK,lw=1.8,zorder=5)
        ax.set_xticks([0,1,2],[name+"\n"+f"{m:.2f}%" for name,m in zip(
            ["Model-based","HC3","Omitted"],np.median(rates,axis=0))])
        ax.set_xlim(-.38,2.38);ax.set_xlabel("Median across designs")
        ax.set_ylabel("Pointwise rejection (%)" if k=="a" else "Pointwise power (%)")
        if k=="a":ref(ax,5)
        ax.margins(y=.12);ax.set_ylim(bottom=-.32 if k=="a" else -2)
        panel(ax,k,title)
    return f


def s10(p):
    z=p("selected_components").sort_values("log_abs_t_ratio")
    f,(a,b)=one_row(10,3.9)
    dots(a,z.log_abs_beta_ratio,z.minus_log_SE_ratio,("Record",BLUE,"o",True),24)
    lim=1.06*np.abs(z[["log_abs_beta_ratio","minus_log_SE_ratio"]].to_numpy()).max()
    a.plot([-lim,lim],[-lim,lim],":",color=RULE);a.plot([-lim,lim],[lim,-lim],":",color=RULE)
    ref(a,0);ref(a,0,True);a.set(xlabel="Log absolute coefficient ratio",ylabel="Negative log SE ratio")
    panel(a,"a","Contributions for each record")
    x=np.arange(len(z));b.bar(x-.19,z.log_abs_beta_ratio,.37,color=BLUE);b.bar(x+.19,z.minus_log_SE_ratio,.37,color=TEAL)
    b.plot(x,z.log_abs_t_ratio,color=INK,lw=1.25);ref(b,0)
    b.set(xlabel="Record ordered by log |t| change",ylabel="Log contribution");panel(b,"b","Coefficient + precision")
    b.legend(handles=[Line2D([],[],lw=3,color=c,label=l) for l,c in [("Coefficient",BLUE),("Precision",TEAL),("Sum",INK)]],
             frameon=False,fontsize=7.2,loc="lower right")
    return f


BUILDERS={1:s1,2:s2,3:s3,4:s4,5:bm.s5,6:s6,7:s7,8:s8,9:s9,10:s10,11:bm.s11,12:bm.s12,
          13:bm.s13,14:bm.s14,15:bm.s15,16:bm.s16,17:bm.s17,18:bm.s18,19:bm.s19,20:bm.s20}


def check_plate(path):
    pdf=PdfReader(path)
    if len(pdf.pages)!=1:raise ValueError(f"{path.name}: expected one page")
    def check_resources(res):
        if "/XObject" not in res:return
        for ref_obj in res["/XObject"].values():
            obj=ref_obj.get_object()
            if obj["/Subtype"]=="/Image":raise ValueError(f"{path.name}: raster image found")
            if obj["/Subtype"]=="/Form" and "/Resources" in obj:check_resources(obj["/Resources"])
    check_resources(pdf.pages[0]["/Resources"])
    with pdfium.PdfDocument(path) as doc:
        edges=edge_pixels(render(doc,0,144))
    bands=[e/2 for e in edges[:2]]
    if min(bands)<9.5:raise ValueError(f"{path.name}: insufficient top or bottom margin")
    return bands


def build(source,out,check_env=False):
    versions={}
    for line in Path(__file__).with_name("requirements.txt").read_text().splitlines():
        name,pin=line.split("==");versions[name]=version(name)
        if versions[name]!=pin:raise ValueError(f"{name}: expected {pin}, found {versions[name]}")
    if check_env:
        print(json.dumps(versions,sort_keys=True));return
    bundle=Bundle(source).verify(expected_stages={"study","design","counts","tails"})
    out=separate_output(out,source)
    if out.exists():raise FileExistsError(f"Use a new output directory: {out}")
    out.parent.mkdir(parents=True,exist_ok=True)
    import sys
    ctx=sys.modules[__name__]
    plt.rcParams.update(STYLE)
    here=Path(__file__).resolve().parent
    audit={"manifest_sha256":sha256(bundle.root/"manifest.csv"),"versions":versions,
           "render_font":Path(font_manager.findfont(font_manager.FontProperties(family=["sans-serif"]))).stem,
           "renderer_sha256":{s:sha256(here/s) for s in ("supplement.py","supplement_benchmarks.py","redraw_figures.py",
                                                         "figure_data.py","submission_pdf.py","requirements.txt")},"figures":{}}
    with tempfile.TemporaryDirectory(dir=out.parent,prefix=".supp-") as temp:
        work=Path(temp)/"figures";work.mkdir()
        for n,builder in BUILDERS.items():
            sources={}
            def read(name):
                entry=bundle.entry("figure_data",name)
                sources[name]=entry["sha256"]
                return bundle.read("figure_data",name)
            f=builder(read,ctx) if builder.__module__==bm.__name__ else builder(read)
            try:
                f.canvas.draw()
                bb=f.get_tightbbox(f.canvas.get_renderer())
                box=Bbox.from_extents(min(0,bb.x0-.10),bb.y0-.145,max(f.get_figwidth(),bb.x1+.10),bb.y1+.145)
                path=work/f"Figure_S{n}.pdf"
                f.savefig(path,format="pdf",bbox_inches=box,dpi=400,
                          metadata={"Title":f"Fig. S{n}. {TITLES[n-1]}","Author":"","Creator":"AdjScope-Tx / Matplotlib",
                                    "CreationDate":None,"ModDate":None})
                audit["figures"][f"S{n}"]={"data":sources,"tables":SOURCES[n-1],"sha256":sha256(path),
                                           "top_bottom_blank_pt":check_plate(path)}
                print(f"Figure S{n}: {len(sources)} verified source(s)",flush=True)
            finally:plt.close(f)
            gc.collect()
        (work/"receipt.json").write_text(json.dumps(audit,indent=2),encoding="utf-8")
        work.rename(out)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source",type=Path,required=True);parser.add_argument("--out",type=Path,required=True)
    parser.add_argument("--check-env",action="store_true");args=parser.parse_args()
    build(args.source,args.out,args.check_env)
