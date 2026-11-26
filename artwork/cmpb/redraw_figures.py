"""Generate Figures 2–6 from numerical inputs and pad the unchanged vector Figure 1."""
import argparse
import json
from importlib.metadata import version
from pathlib import Path
import tempfile

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle
from matplotlib import font_manager
import numpy as np

from adjscope_tx.storage import separate_output, sha256
from .figure_data import Inputs, SPECS, MODELS, SCOPES, ARMS, SCENES
from .submission_pdf import SHEETS, export_plot, export_framework, combine_and_verify

INK='#193240'; SUB='#49616A'; MID='#667B83'; GRID='#DCE6E8'; RULE='#A6BAC1'
BLUE='#205B8D'; TEAL='#087E75'; COPPER='#A44922'; LBLUE='#EAF2F8'; LTEAL='#E4F2EF'
SAND='#FAEFE7'; FOG='#EFF3F4'; WHITE='#FFFFFF'; PAIR='#98ABB1'
W=526
STYLE={
    'font.family':'sans-serif','font.sans-serif':['Arial','Liberation Sans','DejaVu Sans'],
    'font.size':9,'text.color':INK,'axes.labelcolor':SUB,'axes.labelsize':8.3,
    'xtick.labelsize':7.7,'ytick.labelsize':7.7,'xtick.color':SUB,'ytick.color':SUB,
    'axes.edgecolor':RULE,'axes.linewidth':.61,'axes.axisbelow':True,
    'xtick.major.width':.65,'ytick.major.width':.65,'xtick.major.size':2.5,'ytick.major.size':2.5,
    'pdf.fonttype':42,'ps.fonttype':42,'svg.fonttype':'none','figure.facecolor':WHITE,
    'axes.facecolor':WHITE,'savefig.facecolor':WHITE,'axes.unicode_minus':True,
}

class Plate:
    def __init__(self,number,height):
        self.h=height; self.n=number; self.panels=[]; self.fig=plt.figure(figsize=(W/72,height/72),dpi=135)
    def text(self,x,t,s,size=9,color=INK,weight='normal',ha='left',va='baseline',**kw):
        return self.fig.text(x/W,1-t/self.h,str(s),fontsize=size,color=color,fontweight=weight,
                             ha=ha,va=va,**kw)
    def line(self,x,t,xx,tt,c=RULE,lw=.7,z=0,**kw):
        ln=Line2D([x/W,xx/W],[1-t/self.h,1-tt/self.h],transform=self.fig.transFigure,
                  color=c,linewidth=lw,zorder=z,solid_capstyle='butt',**kw)
        self.fig.add_artist(ln)
    def rect(self,x,t,w,h,fill,edge='none',lw=0,z=-1):
        r=Rectangle((x/W,1-(t+h)/self.h),w/W,h/self.h,transform=self.fig.transFigure,
                    facecolor=fill,edgecolor=edge,linewidth=lw,zorder=z)
        self.fig.add_artist(r)
    def section(self,x,t,letter,title):
        self.panels.append((letter,title))
        self.text(x,t,letter,11.2,TEAL,'bold')
        self.text(x+13,t,title,10.5,INK,'bold')
    def axes(self,x,t,w,h,grid='x'):
        ax=self.fig.add_axes([x/W,1-(t+h)/self.h,w/W,h/self.h])
        ax.spines[['top','right']].set_visible(False)
        ax.tick_params(pad=2.5)
        if grid:ax.grid(axis=grid,color=GRID,lw=.55)
        ax.margins(0)
        return ax
    def key(self,x,t,label,marker,color,open_=False):
        a=Line2D([x/W],[1-(t-2.4)/self.h],transform=self.fig.transFigure,marker=marker,
                 linestyle='none',markersize=4.8,markerfacecolor=WHITE if open_ else color,
                 markeredgecolor=color,markeredgewidth=1.0,zorder=5)
        self.fig.add_artist(a);self.text(x+6,t,label,7.8,SUB)
    def foot(self,s):
        self.line(16,self.h-22,W-16,self.h-22,GRID,.65)
        self.text(16,self.h-8,s,7.55,SUB)
    def ypt(self,ax,y):
        left,bot,w,h=ax.get_position().bounds;lo,hi=ax.get_ylim()
        return self.h*(1-bot-h*(y-lo)/(hi-lo))

def nom(ax,x):
    return ax.axvline(x,ls=(0,(3.1,2.4)),lw=.9,color=MID,zorder=1.1)
def cleanrow(ax):
    ax.spines['left'].set_visible(False)
    ax.tick_params(axis='y',length=0)
    ax.set_yticks([])
def rows(ax,upper,n=-.6):
    ax.set_ylim(upper,n);cleanrow(ax)
def pt(ax,x,y,color,mark='o',hollow=False,sz=4.4,z=4):
    return ax.plot(x,y,marker=mark,markersize=sz,ls='none',mfc=WHITE if hollow else color,
                   mec=color,mew=1 if hollow else .6,color=color,zorder=z)[0]
def interval(ax,l,r,y,col,cap=.07,lw=.9):
    ax.hlines(y,l,r,color=col,lw=lw,zorder=2.4)
    if cap:ax.vlines([l,r],y-cap,y+cap,color=col,lw=lw,zorder=2.4)
def fig2(D):
    h,s=D.h,D.sel
    f=Plate(2,408)
    f.section(16,18,'a','Joint BH threshold crossings')
    f.section(279,18,'b','Paired dementia coefficients')
    f.key(20,37,'Base','o',BLUE,True);f.key(95,37,'Quality adjusted','D',TEAL)
    f.text(279,37,f'{len(h):,} testable gene–context records',8,SUB)
    qa=f.axes(25,65,213,171)
    qa.hlines(range(len(s)),s.q_joint_base,s.q_joint_quality,color=PAIR,lw=.8,zorder=2)
    sizes=[8.,5.5];strokes=[.65,.33]
    for field,mark,fill,col,size,lw in zip(['q_joint_base','q_joint_quality'],['o','D'],[WHITE,TEAL],[BLUE,TEAL],sizes,strokes):
        qa.scatter(s[field],range(len(s)),s=size,marker=mark,facecolors=fill,edgecolors=col,linewidths=lw,zorder=3.5)
    nom(qa,.05);qa.set_xlim(-.003,.205);qa.set_ylim(39.9,-.9);cleanrow(qa)
    qa.set_xticks([0,.05,.10,.15,.20],['0','0.05','0.10','0.15','0.20'])
    qa.set_xlabel('Joint BH q value')
    qa.text(.05,1.025,'5% threshold',transform=qa.get_xaxis_transform(),ha='center',color=SUB,fontsize=7.5)
    data=np.vstack([np.column_stack([s[c],np.arange(len(s))]) for c in ['q_joint_base','q_joint_quality']])
    xy=qa.transData.transform(data)*72/f.fig.dpi
    radii=np.repeat([np.sqrt(sizes[0])/2+strokes[0]/2,np.sqrt(sizes[1]/2)+strokes[1]/2],len(s))
    gaps=np.linalg.norm(xy[:,None,:]-xy[None,:,:],axis=-1)-radii[:,None]-radii[None,:]
    gap=float(gaps[np.triu_indices(len(xy),k=1)].min())
    if gap<.45:raise ValueError('Figure 2a: adjacent endpoint markers touch.')
    f.endpoint_check={'symbols':len(xy),'min_edge_gap_pt':round(gap,3)}
    ax=f.axes(310,59,187,177,grid='both');ax.set_aspect('equal','box')
    lim=np.ceil(np.max(np.abs(h[['beta_base','beta_quality']].to_numpy()))/.25)*.25+.04
    ax.set(xlim=(-lim,lim),ylim=(-lim,lim),xlabel=r'Base coefficient (log$_2$)',ylabel=r'Quality-adjusted coefficient (log$_2$)')
    ticks=[-1.5,-.75,0,.75,1.5]
    ax.set_xticks(ticks,[f'{v:g}' for v in ticks]);ax.set_yticks(ticks,[f'{v:g}' for v in ticks])
    ax.scatter(h.beta_base,h.beta_quality,s=4,c='#8A9FA8',alpha=.37,linewidths=0,zorder=1.5)
    ax.plot([-lim,lim],[-lim,lim],color=MID,lw=.8,ls=(0,(3,3)),zorder=2)
    ax.scatter(s.beta_base,s.beta_quality,s=15,facecolors='none',edgecolors=BLUE,linewidths=.8,zorder=3)
    wf=D.wfs
    ax.scatter([wf.beta_base],[wf.beta_quality],s=30,facecolors=WHITE,edgecolors=COPPER,linewidths=1.15,zorder=4)
    ax.annotate(r'$\mathit{WFS1}$, astrocytes'+'\n'+f'{wf.beta_base:.3f} → {wf.beta_quality:.3f}',
                (wf.beta_base,wf.beta_quality),xytext=(.055,.92),textcoords='axes fraction',
                color=COPPER,fontsize=7.8,va='top',arrowprops=dict(arrowstyle='-',color=COPPER,lw=.8,shrinkB=4))
    f.line(16,274,510,274,GRID,.7)
    f.section(16,290,'c','Joint q values among the original 40 records')
    for px,lab,edge,fill in [(350,'Base',BLUE,LBLUE),(400,'Quality adjusted',TEAL,TEAL)]:
        f.rect(px,284,7,6,fill,edge,.8);f.text(px+10,290,lab,7.8,SUB)
    bx=f.axes(51,301,449,61,grid='y'); x=np.arange(len(D.bins.loc[D.bins.arm=='base']))
    for arm,offset,col,fill in [('base',-.19,BLUE,LBLUE),('extended',.19,TEAL,TEAL)]:
        counts=D.bins.loc[D.bins.arm==arm].sort_values('lower').n.to_numpy(int)
        bx.bar(x+offset,counts,.34,color=fill,edgecolor=col,linewidth=.85,zorder=2)
        for xx,v in zip(x+offset,counts):
            if v:bx.text(xx,v+.7,str(v),color=col,ha='center',va='bottom',fontsize=7.8,fontweight='bold')
    bx.set(xlim=(-.55,len(x)-.45),ylim=(0,29),ylabel='Records');bx.set_yticks([0,10,20])
    bx.set_xticks(x,['<0.01','0.01–0.02','0.02–0.03','0.03–0.04','0.04–0.05','0.05–0.10','0.10–0.20'])
    f.foot('Joint BH correction across 17,064 planned positions per fit. Tables S3.2 and S3.5.')
    return f

def fig3(D):
    f=Plate(3,237)
    f.section(16,18,'a','All clinical-status discoveries');f.section(323,18,'b','Original 40 retained')
    f.key(138,38,'Base','o',BLUE,True);f.key(188,38,'Quality adjusted','D',TEAL)
    f.key(328,38,'Planned tests','D',TEAL);f.key(418,38,'Available tests','s',MID,True)
    f.text(16,39,'BH scope',8.3,INK,'bold');f.text(16,50,'Planned tests per family',7.55,SUB)
    for px,lab,col in [(252,'Base',BLUE),(279,'Quality',TEAL),(444,'Planned',TEAL),(478,'Available',MID)]:
        f.text(px,54,lab,7.1,col)
    ax=f.axes(137,57,105,101);bx=f.axes(326,57,103,101)
    for sub,upper,ticks in [(ax,160,[0,50,100,150]),(bx,41,[0,10,20,30,40])]:
        rows(sub,3.55,-.55);sub.set_xlim(-.025*upper,upper*1.025);sub.set_xticks(ticks);sub.set_xlabel('Records')
    for i,(scope,name) in enumerate(zip(SCOPES,['Joint','By contrast','By cell context','Cell context × contrast'])):
        y=f.ypt(ax,i)
        f.text(16,y-1,name,8.8,INK,'bold' if i<2 else 'normal',va='center')
        f.text(16,y+9,f'{int(D.sizes[scope]):,}',7.5,SUB,va='center')
        l,m=[int(D.disc.loc[(scope,v)]) for v in ('base','extended')]
        p,a=[D.ret(scope,v) for v in ('planned','available_only')]
        for sub,v0,v1,c0,c1,m0,m1 in [(ax,l,m,BLUE,TEAL,'o','D'),(bx,p,a,TEAL,MID,'D','s')]:
            sub.plot([v0,v1],[i-.14,i+.14],color=PAIR,lw=.85,zorder=2)
            pt(sub,v0,i-.14,c0,m0,sub is ax,4.6);pt(sub,v1,i+.14,c1,m1,sub is bx,4.6)
        for px,num,col in [(252,l,BLUE),(279,m,TEAL),(444,p,TEAL),(478,a,MID)]:
            f.text(px,y,num,8.7,col,'bold',va='center')
    f.line(16,191,510,191,GRID,.7)
    f.text(16,207,f'Planned families: clinical status {D.ret("by_contrast","planned")} / 40 retained; three contrasts jointly {D.ret("original","planned")} / 40.',9.1,INK,'bold')
    f.foot('Counts in a sum discoveries across partitions; b follows the same baseline records. Table S3.6.')
    return f

MODEL_NAMES=['Random intercept (dream)','Cage fixed effects','Mundlak','No cage','Common correlation']
SPEC_NAMES=['Continuous age','Grouped age','Grouped age + slide']*2

def fig4(D):
    f=Plate(4,417);cases=[(0,0),(0,.5),(.3,0),(.3,.5)]
    xpos=[133,230,327,424];w=76
    f.text(16,15,'Latent cage SD',8.2,SUB);f.text(16,29,'Cage-mean amplitude',8.2,SUB)
    for x,(sd,shift) in zip(xpos,cases):
        f.text(x+w/2,15,f'{sd:g}',9.2,INK,'bold','center')
        f.text(x+w/2,29,f'{shift:g}',9.2,COPPER if shift else SUB,'bold','center')
    f.line(16,36,510,36,GRID,.7)
    styles=[(COPPER,'D'),(BLUE,'o'),(TEAL,'s'),(MID,'^'),('#827094','v')]
    bands=[('FDR','False discovery rate (%)',(-2.5,66),[0,30,60],5),
           ('power','Power (%)',(91.7,100),[92,96,100],None),
           ('coverage','95% interval coverage (%)',(74,99),[75,85,95],95)]
    for j,(metric,title,lim,ticks,target) in enumerate(bands):
        top=52+j*108
        f.section(16,top,'abc'[j],title)
        for i,(x,(sd,shift)) in enumerate(zip(xpos,cases)):
            ax=f.axes(x,top+9,w,68);rows(ax,4.55,-.55);ax.set_xlim(*lim);ax.set_xticks(ticks)
            if target is not None:nom(ax,target)
            for k,(model,(col,mk)) in enumerate(zip(MODELS,styles)):
                rr=D.count.loc[(sd,shift,model)]
                lo,val,hi=[100*rr[metric+'_'+e] for e in ('low','mean','high')]
                if not (lim[0]<lo<=val<=hi<lim[1]):raise ValueError(f'Figure 4: clipped {metric} interval.')
                interval(ax,lo,hi,k,col,.12,1.1);pt(ax,val,k,col,mk,False,3.9)
                if not i:f.text(16,f.ypt(ax,k),MODEL_NAMES[k],7.85,INK,'bold' if k==0 else 'normal',va='center')
        if j<2:f.line(16,top+94,510,top+94,GRID,.62)
    f.line(16,369,510,369,GRID,.7)
    def fdr(s,m):return 100*D.count.loc[(0,s,m),'FDR_mean']
    f.text(16,384,f'Cage SD = 0: dream FDR {fdr(0,MODELS[0]):.2f}% → {fdr(.5,MODELS[0]):.2f}%; at amplitude 0.5, cage fixed {fdr(.5,MODELS[1]):.2f}% and Mundlak {fdr(.5,MODELS[2]):.2f}%.',8.25,INK)
    f.foot('95% Monte Carlo intervals; dream and Mundlak use design-specific weights. 200 datasets × 13,312 genes per condition. S20.10.')
    return f

def fig5(D):
    f=Plate(5,352)
    f.section(16,18,'a','Sources of the standard-error ratio');f.section(337,18,'b','Effect of refitting weights')
    factors=[('SE_ratio','SE ratio',COPPER,'o'),('unscaled_ratio','Weighted design',BLUE,'D'),
             ('posterior_SD_ratio','Residual scale',TEAL,'s')]
    for x,(_,lab,col,mk) in zip([20,94,199],factors):f.key(x,38,lab,mk,col,True if mk=='D' else False)
    f.text(337,38,'Design-specific / shared-weight SE',7.8,SUB)
    left=f.axes(149,54,164,111);right=f.axes(347,54,151,111)
    ys=[0,1,2,3.65,4.65,5.65]
    for ax in [left,right]:rows(ax,6.25,-.6);nom(ax,1)
    left.set_xlim(.87,1.94);left.set_xticks([1,1.2,1.4,1.6,1.8],['1.0','1.2','1.4','1.6','1.8'])
    right.set_xlim(.958,1.033);right.set_xticks([.97,.99,1.01,1.03],['0.97','0.99','1.01','1.03'])
    for j,(y,spec) in enumerate(zip(ys,SPECS)):
        yp=f.ypt(left,y)
        if j in (0,3):f.text(16,yp,'Whole section' if j==0 else 'Cortex',7.9,INK,'bold',va='center')
        f.text(71,yp,SPEC_NAMES[j],7.7,SUB,va='center')
        for k,(met,_,col,mk) in enumerate(factors):
            r=D.prec.loc[(spec,met)];dy=(k-1)*.26
            interval(left,r.q25,r.q75,y+dy,col,.075,1.05)
            pt(left,r['median'],y+dy,col,mk,mk=='D',3.35)
        r=D.prec.loc[(spec,'reweight_factor')]
        interval(right,r.whisker_low,r.whisker_high,y,MID,.18,.92)
        right.add_patch(Rectangle((r.q25,y-.19),r.q75-r.q25,.38,fc=LTEAL,ec=TEAL,lw=.9,zorder=3))
        right.vlines(r['median'],y-.20,y+.20,color=INK,lw=1.45,zorder=4)
    f.line(16,187,510,187,GRID,.7)
    f.section(16,206,'c','Residual genotype sum of squares');f.section(292,206,'d','Residual degrees of freedom')
    f.text(16,225,'Whole section',8,INK,'bold');f.key(128,225,'No cage','o',BLUE,True);f.key(202,225,'Cage fixed effects','s',TEAL)
    a=f.axes(125,236,118,56);b=f.axes(328,236,148,56)
    for ax,lim,ticks in [(a,(0,20),[0,5,10,15,20]),(b,(0,76),[0,20,40,60])]:
        rows(ax,2.55,-.55);ax.set_xlim(*lim);ax.set_xticks(ticks)
    for j,spec in enumerate(SPECS[:3]):
        f.text(16,f.ypt(a,j),SPEC_NAMES[j],7.9,SUB,va='center')
        for ax,metric in [(a,'genotype_residual_SS'),(b,'residual_df')]:
            vals=[D.geo.loc[(spec,branch),metric] for branch in ('baseline','cage_fixed')]
            ax.plot(vals,[j-.12,j+.12],color=PAIR,lw=1.05,zorder=2)
            pt(ax,vals[0],j-.12,BLUE,'o',True,4.6);pt(ax,vals[1],j+.12,TEAL,'s',False,4.1)
    ref=D.des.loc['whole_linear']
    f.text(16,322,f'Whole section, continuous age: SE ratio {ref.predicted:.3f} predicted; {ref.observed_median:.3f} observed (median).',8.6,INK,'bold')
    f.foot('Medians and interquartile ranges span 13,312 genes; whole-section geometry in c and d. Tables S14.1 and S16.4.')
    return f

METHODS=[('model_based','Model-based',BLUE,'o',True),('HC3','HC3',COPPER,'s',False)]

def draw_scenario_row(ax,values,y):
    """Pack symbols in the categorical direction only. Error rates retain their exact x values."""
    xy=ax.transData.transform
    unit_y=abs(xy((0,1))[1]-xy((0,0))[1])*72/ax.figure.dpi
    xs=np.array([xy((v,0))[0]*72/ax.figure.dpi for v,method in values])
    size=3.0
    radii=np.array([size/2+.5 if method==0 else size/np.sqrt(2)+.3 for v,method in values])
    margin=.60
    left=xs-radii-margin/2;right=xs+radii+margin/2
    groups=[];boundary=-np.inf
    for i in np.argsort(left,kind='stable'):
        if left[i]>boundary:groups.append([])
        groups[-1].append(i);boundary=max(boundary,right[i])
    placed={}
    for group in groups:
        ends=[];slots={};pitch=2*max(radii[i] for i in group)+margin+.10
        for i in group:
            lane=next((j for j,end in enumerate(ends) if end<=left[i]),len(ends))
            if lane==len(ends):ends.append(right[i])
            else:ends[lane]=right[i]
            slots[i]=lane
        for i,lane in slots.items():
            placed[i]=(lane-(len(ends)-1)/2)*pitch
            if abs(placed[i])+radii[i]+.35>=unit_y/2:raise ValueError('Scenario markers would join neighbouring rows.')
    gaps=[]
    for i,(value,j) in enumerate(values):
        _,_,col,mk,ho=METHODS[j]
        pt(ax,value,y+placed[i]/unit_y,col,mk,ho,size)
        gaps.extend(np.hypot(xs[i]-xs[k],placed[i]-placed[k])-radii[i]-radii[k] for k in range(i))
    if min(gaps)<margin-1e-6:
        raise ValueError('Figure 6: scenario markers would overlap.')
    return float(min(gaps))

def fig6(D):
    f=Plate(6,423)
    f.section(16,18,'a','BH false discovery rate');f.section(320,18,'b','Bonferroni family-wise error')
    f.key(156,37,'Model-based','o',BLUE,True);f.key(255,37,'HC3','s',COPPER)
    f.text(16,37,'Weight / response control',8.0,SUB)
    ax=f.axes(167,49,115,124);bx=f.axes(342,49,132,124)
    for aa in [ax,bx]:
        rows(aa,5.65,-.65);aa.set_xlim(-.45,15.85);aa.set_xticks([0,5,10,15]);aa.set_xlabel('Error rate (%)');nom(aa,5)
    labs=['Same counts · shared weights','Same counts · design-specific',
          'Independent counts · shared','Independent counts · design-specific',
          'Count response · unit weights','Gaussian response · unit weights']
    gaps=[]
    for i,(arm,lab) in enumerate(zip(ARMS,labs)):
        f.text(16,f.ypt(ax,i),lab,7.75,INK,'bold' if i==5 else 'normal',va='center')
        for aa,metric in [(ax,'fdp_planned_050'),(bx,'bonferroni_fwer')]:
            vals=[(float(100*D.tail.loc[(arm,sc,k),metric]),j)
                  for j,(k,*_) in enumerate(METHODS) for sc in SCENES]
            gaps.append(draw_scenario_row(aa,vals,i))
    f.scenario_markers={'symbols':2*len(ARMS)*len(SCENES)*len(METHODS),'min_edge_gap_pt':round(min(gaps),3)}
    f.line(16,210,510,210,GRID,.7)
    f.section(16,228,'c','Gaussian controls: coverage and FDR')
    f.section(340,228,'d','Extreme-tail frequency')
    f.text(16,247,'Scenario / n',7.75,SUB)
    f.text(87,247,'Coverage (%)',7.75,SUB);f.text(218,247,'BH FDR (%)',7.75,SUB)
    f.text(340,247,'p ≤ 0.05 / 3,000',7.75,SUB)
    ca=f.axes(87,257,95,85);cb=f.axes(218,257,81,85);da=f.axes(353,257,141,85)
    ca.set_xlim(94.88,95.85);ca.set_xticks([95,95.4,95.8],['95.0','95.4','95.8'])
    cb.set_xlim(-.5,15.6);cb.set_xticks([0,5,10,15])
    da.set_xlim(0,4.05);da.set_xticks(range(5));da.set_xlabel('Observed / uniform-null rate')
    for aa,target in [(ca,95),(cb,5),(da,1)]:
        rows(aa,5.55,-.55);nom(aa,target)
    for i,sc in enumerate(SCENES):
        n=int(D.tail.loc[('gaussian_unit',sc,'model_based'),'n'])
        f.text(16,f.ypt(da,i),f'{sc} / {n}',8.0,INK,'bold' if sc=='s09' else 'normal',va='center')
        for aa,metric in [(ca,'coverage95'),(cb,'fdp_planned_050'),(da,'ratio_to_uniform')]:
            vv=[]
            for j,(k,_,col,mk,ho) in enumerate(METHODS):
                x=D.extreme.loc[(sc,k),metric] if aa is da else 100*D.tail.loc[('gaussian_unit',sc,k),metric]
                y=i+(j-.5)*.48;pt(aa,x,y,col,mk,ho,3.8);vv.append((x,y))
            aa.plot(*zip(*vv),color=PAIR,lw=.8,zorder=2)
    f.line(16,376,510,376,GRID,.7)
    def pair(field,n):
        return ' / '.join(format(100*D.tail.loc[('gaussian_unit','s09',k),field],f'.{n}f')+'%' for k,*_ in METHODS)
    f.text(16,390,f's09, model-based / HC3: coverage {pair("coverage95",2)}; BH FDR {pair("fdp_planned_050",1)}; Bonferroni {pair("bonferroni_fwer",1)}.',8.15,INK,'bold')
    f.foot('Six scenarios; 500 datasets and 3,000 planned tests per dataset. Scenario definitions and tail rates: Tables S23.1 and S23.2.')
    return f


def audit_frame(plate):
    from matplotlib.text import Text
    fig=plate.fig;fig.canvas.draw();render=fig.canvas.get_renderer()
    fw,fh=fig.get_size_inches()*fig.dpi
    invalid=[]
    for obj in fig.findobj(match=Text):
        if not obj.get_visible() or not obj.get_text().strip():continue
        bb=obj.get_window_extent(render)
        if bb.x0 < -1.5 or bb.x1 > fw+1.5 or bb.y0 < -1.5 or bb.y1>fh+1.5:
            invalid.append(obj.get_text())
    if invalid:raise ValueError(f'Figure {plate.n}: text outside page: {invalid}')
    labels=[(t.get_text(),t.get_window_extent(render)) for t in fig.texts if t.get_visible() and t.get_text().strip()]
    for i,(a,u) in enumerate(labels):
        for b,v in labels[i+1:]:
            width=min(u.x1,v.x1)-max(u.x0,v.x0);height=min(u.y1,v.y1)-max(u.y0,v.y0)
            if width>2 and height>2 and width*height>.12*min(u.width*u.height,v.width*v.height):
                raise ValueError(f'Figure {plate.n}: text collision: {a!r} / {b!r}')

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',required=True,type=Path)
    p.add_argument('--check-env',action='store_true')
    p.add_argument('--out',required=True,type=Path)
    args=p.parse_args()
    here=Path(__file__).resolve().parent
    versions={}
    for line in (here/'requirements.txt').read_text(encoding='utf-8').splitlines():
        name,pin=line.split('==')
        versions[name]=version(name)
        if versions[name]!=pin:
            p.error(f'{name}: expected {pin}, found {versions[name]}; use the separate CMPB plotting environment.')
    if args.check_env:
        print(json.dumps(versions,sort_keys=True))
        return
    out=separate_output(args.out,args.source)
    minimum=9.
    framework=here/'framework.pdf'
    if sha256(framework)!='60d49fcc3283ad61e91cdce61b14c3fe96fe447a3315c628cd29e2a6c4b9bc4c':
        p.error('The original Figure 1 artwork changed.')
    if out.exists():p.error('Use a new output directory. Existing figures are never overwritten.')
    out.parent.mkdir(parents=True,exist_ok=True)
    plt.rcParams.update(STYLE);d=Inputs(args.source)
    actual_font=font_manager.FontProperties(family=['sans-serif'])
    font=Path(font_manager.findfont(actual_font)).stem
    with tempfile.TemporaryDirectory(dir=out.parent,prefix='.adjscope-') as tmp:
        work=Path(tmp)/'verified';work.mkdir()
        (work/SHEETS).mkdir();(work/'Preview').mkdir();(work/'Checks').mkdir()
        audit=[export_framework(framework,work,minimum)]
        print('Figure 1: original vector artwork verified.',flush=True)
        for build in [fig2,fig3,fig4,fig5,fig6]:
            plate=build(d)
            try:
                letters=''.join(k for k,_ in plate.panels)
                if letters!={2:'abc',3:'ab',4:'abc',5:'abcd',6:'abcd'}[plate.n]:
                    raise ValueError(f'Figure {plate.n}: panel sequence differs from the manuscript caption.')
                audit_frame(plate)
                row=export_plot(plate,work,minimum)
                row['caption_panels']=dict(plate.panels)
                if hasattr(plate,'scenario_markers'):row['categorical_marker_check']=plate.scenario_markers
                if hasattr(plate,'endpoint_check'):row['q_value_endpoint_check']=plate.endpoint_check
                audit.append(row);print(f'Figure {plate.n}: vector PDF, margins and typography verified.',flush=True)
            finally:plt.close(plate.fig)
        combine_and_verify(work)
        receipt={'inputs_sha256':{'original_framework_pdf':sha256(framework),**d.fingerprint},'render_font':font,
                 'renderer_sha256':{n:sha256(here/n) for n in ('redraw_figures.py','figure_data.py','submission_pdf.py','requirements.txt')},
                 'render_packages':versions,'minimum_blank_band_mm':minimum,'artwork':audit,
                 'sources':{'2':['clinical_pairs','S3.2','S3.5'],'3':['family_sizes','S3.6'],'4':['S20.10'],
                            '5':['precision_components','S14.1','S16.4'],'6':['S23.1','S23.2']}}
        (work/'Checks'/'figure_audit.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
        work.rename(out)

if __name__=='__main__':main()
