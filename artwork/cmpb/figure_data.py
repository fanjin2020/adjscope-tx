"""Resolve the six CMPB plates against one verified publication bundle."""

import numpy as np
from adjscope_tx.publication import Bundle
from adjscope_tx.storage import sha256

SPECS = ['whole_linear', 'whole_age_factor', 'whole_age_factor_slide',
         'cortex_linear', 'cortex_age_factor', 'cortex_age_factor_slide']
SCOPES = ['original', 'by_contrast', 'by_context', 'by_context_contrast']
MODELS = ['dream_native','cage_fixed','mundlak_native','baseline','cage_correlation']
ARMS = ['estimated_shared','estimated_design','independent_shared','independent_design',
        'fixed_unit','gaussian_unit']
SCENES = ['s01','s09','s11','s12','s15','s23']

SECTIONS=('S3.2','S3.5','S3.6','S14.1','S16.4','S20.10','S23.1','S23.2')
PLOTS=('clinical_pairs','family_sizes','precision_components')

def check(ok, message):
    if not ok:
        raise ValueError('CMPB artwork: '+message)

class Inputs:
    def __init__(self,source):
        bundle=Bundle(source).verify(expected_stages={'study','design','counts','tails'})
        sec={key:bundle.read('table',key) for key in SECTIONS}
        def csv(name):
            return bundle.read('figure_data',name)
        h=csv('clinical_pairs').dropna(subset=['beta_base','beta_quality','q_joint_base','q_joint_quality'])
        self.h=h
        self.sel=h[h.q_joint_base.lt(.05)].sort_values(['q_joint_base','gene_symbol','context'])
        pair=self.sel.loc[(self.sel.gene_symbol=='WFS1')&(self.sel.context=='Astrocyte')]
        check(len(pair)==1,'missing or repeated WFS1/astrocyte example')
        self.wfs=pair.iloc[0]
        check(len(h)==3744 and len(self.sel)==len(self.sel.drop_duplicates(['gene_symbol','context']))==40,'clinical record counts differ')
        check((np.sign(self.sel.beta_base)==np.sign(self.sel.beta_quality)).all() and not self.sel.q_joint_quality.lt(.05).any(),'sign retention or joint BH result differs')
        check(set(zip(self.sel.gene_symbol,self.sel.context))==set(zip(sec['S3.2'].gene_symbol,sec['S3.2'].context)),'S3.2 disagrees with the selected clinical records')
        self.bins=sec['S3.5']
        for arm,field in [('base','q_joint_base'),('extended','q_joint_quality')]:
            z=self.bins.loc[self.bins.arm==arm].sort_values('lower')
            edges=np.r_[z.lower.values,z.upper.values[-1]]
            check(np.array_equal(np.histogram(self.sel[field],edges)[0],z.n.to_numpy()),'S3.5 disagrees with the q-value bins: '+arm)
        self.sizes=csv('family_sizes').query('collection=="human_17064" and denominator=="planned"').groupby('scope').planned.first()
        fam=sec['S3.6'].query('model=="clinical_status"')
        self.disc=fam.query('record_type=="discoveries" and denominator=="planned"').set_index(['scope','branch']).significant
        self.retain=fam.query('record_type=="retention"').set_index('correction')
        check(self.retain.original_base_discoveries.nunique()==1 and self.retain.original_base_discoveries.iloc[0]==40,'retention denominators differ')
        check(self.ret('by_contrast','planned')==29 and self.ret('original','planned')==0,'fixed-fit BH anchors differ')
        self.count=sec['S20.10'].query('de_fraction==0.1').set_index(['cage_log2_sd','cage_mean_amplitude','model'])
        check(self.count.index.is_unique and len(self.count)==20,'count benchmark keys differ')
        check((self.count.repetitions==200).all() and (self.count.genes==13312).all(),'count benchmark size differs')
        self.prec=csv('precision_components').set_index(['spec','metric'])
        self.des=sec['S16.4'].set_index('spec').loc[SPECS]
        self.geo=sec['S14.1'].set_index(['spec','branch'])
        for spec in SPECS:
            g=self.geo.loc[(spec,'baseline')];h=self.geo.loc[(spec,'cage_fixed')]
            check(np.isclose(np.sqrt(g.genotype_residual_SS/h.genotype_residual_SS),self.des.loc[spec,'predicted']),'design geometry disagrees with S16.4: '+spec)
            r=self.prec.loc[(spec,'SE_ratio')]
            check(r.n==13312 and np.allclose([r['median'],r.q25,r.q75],self.des.loc[spec,['observed_median','observed_q25','observed_q75']].to_numpy(float)),'SE-ratio distribution differs: '+spec)
        self.tail=sec['S23.1'].set_index(['arm','scenario','test'])
        self.extreme=sec['S23.2'].query('arm=="gaussian_unit" and label=="bh_first"').set_index(['scenario','test'])
        check(set(self.tail.index.get_level_values(0))==set(ARMS) and len(self.tail)==72 and (self.tail.datasets==500).all(),'tail arms or replicate counts differ')
        check(len(self.extreme)==12 and np.allclose(self.extreme.cutoff, .05/3000),'extreme-tail definition differs')
        check(self.tail.loc[('gaussian_unit','s09','HC3'),'n']==80,'s09 is not the 80-sample control')
        actual=[self.count.loc[(0,s,'dream_native'),'FDR_mean']*100 for s in [0,.5]]
        check([f'{v:.2f}' for v in actual]==['5.11','57.27'],'count FDR differs from the annotated plate')
        check([f'{self.des.loc["whole_linear",c]:.3f}' for c in ('predicted','observed_median')]==['1.490','1.498'],'precision differs from the fixed framework artwork')
        self.fingerprint={'manifest.csv':sha256(bundle.root/'manifest.csv')}
        for kind,keys in [('table',SECTIONS),('figure_data',PLOTS)]:
            for key in keys:
                entry=bundle.entry(kind,key)
                self.fingerprint[entry['file']]=entry['sha256']
    def ret(self,scope,den):
        return int(self.retain.loc['q__'+scope+'__'+den,'adjusted_significant'])
