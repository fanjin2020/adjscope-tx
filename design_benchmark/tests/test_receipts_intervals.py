import contextlib
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from scipy.stats import beta

from design_benchmark import VERSION
from design_benchmark import driver, report
from design_benchmark.study import create_designs, scenarios, write_csv, gaussian_job


class IntervalTests(unittest.TestCase):
    def test_global_null_exact_for_every_event_count(self):
        uppers=[]
        for k in range(51):
            z=report.interval([{'FDP':1}]*k+[{'FDP':0}]*(50-k),'FDP',True)
            expected=beta.ppf(.95,k+1,50-k) if k<50 else 1.
            self.assertAlmostEqual(z['upper'],expected)
            self.assertEqual(z['method'],'exact_binomial_global_null')
            uppers.append(z['upper'])
        self.assertTrue(np.all(np.diff(uppers)>0))

    def test_one_event_bound(self):
        z=report.interval([{'FDP':0}]*49+[{'FDP':1}],'FDP',True)
        self.assertAlmostEqual(z['upper'],.09139813071969734)

    def test_fractional_fdp_does_not_use_binomial(self):
        z=report.interval([{'FDP':.1},{'FDP':.2},{'FDP':.15}],'FDP',False)
        self.assertEqual(z['method'],'approximate_t_monte_carlo')
        with self.assertRaisesRegex(ValueError,'binary'):
            report.interval([{'FDP':.1}],'FDP',True)

    def test_zero_event_bound_and_unavailable(self):
        self.assertEqual(report.interval([{'FDP':0}]*50,'FDP')['method'],'zero_event_conservative_bound')
        self.assertIsNone(report.interval([{'FDP':None}],'FDP',True)['upper'])

    def test_unknown_context_abstains(self):
        rule=dict(training_metrics=[dict(scenario=0)])
        self.assertEqual(report.choose(rule,{},None)['status'],'generating_context_required')
        self.assertEqual(report.choose(rule,{},99)['status'],'unsupported_generating_context')


class CheckpointTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.designs=create_designs(self.root/'designs',321)
        self.jobs=driver.make_jobs(self.designs,scenarios('full'),self.root,321,'all',500,50,0)

    def test_full_grid_has_one_count_dataset_per_receipt(self):
        counts=[j for j in self.jobs if j['phase']=='counts']
        gaussian=[j for j in self.jobs if j['phase']=='gaussian']
        self.assertEqual(len(counts),4800);self.assertEqual(len(gaussian),480)
        self.assertTrue(all(j['end']-j['start']==1 for j in counts))
        self.assertEqual(len({j['id'] for j in self.jobs}),5280)

    def test_nonobject_receipts_are_invalid_not_exceptions(self):
        job=self.jobs[0];folder=self.root/'tasks'/job['id'];folder.mkdir(parents=True)
        for value in (None,[],0,'broken',{'files':[]}):
            (folder/'receipt.json').write_text(json.dumps(value))
            self.assertFalse(driver.valid_receipt(self.root,job,'run'))
            self.assertIsInstance(driver.receipt_problem(self.root,job,'run'),str)

    def test_historical_progress_is_not_live_progress(self):
        job=next(j for j in self.jobs if j['phase']=='counts')
        folder=self.root/'tasks'/job['id'];folder.mkdir(parents=True)
        state={'attempt_id':'new'};protocol={'run_id':'run'}
        p=dict(done=1,attempt_id='old',run_id='run',job_hash=driver.identity(job))
        driver.atomic_json(folder/'progress.json',p)
        self.assertEqual(driver.current_partial(self.root,[job],set(),protocol,state),0)
        p['attempt_id']='new';driver.atomic_json(folder/'progress.json',p)
        self.assertEqual(driver.current_partial(self.root,[job],set(),protocol,state),1)
        self.assertEqual(driver.current_partial(self.root,[job],{job['id']},protocol,state),0)
        p['job_hash']='wrong';driver.atomic_json(folder/'progress.json',p)
        self.assertEqual(driver.current_partial(self.root,[job],set(),protocol,state),0)

    def test_legacy_status_rejected(self):
        driver.atomic_json(self.root/'protocol.json',dict(version='0.1.0'))
        with self.assertRaisesRegex(ValueError,'original code'):driver.status(self.root)

    def test_one_completed_count_rep_survives_next_rep_failure(self):
        jobs=[j for j in self.jobs if j['phase']=='counts' and j['design']=='k12_w1' and j['scenario']['scenario']==0][:2]
        protocol=dict(output=str(self.root),run_id='run',rscript='fake_R_NOT_A_STATISTICAL_TEST')
        def fake_command(cmd,env,log,cwd):
            j=driver.read_json(Path(cmd[-1]));folder=Path(j['output'])
            log.parent.mkdir(parents=True,exist_ok=True);log.write_text('Test double; no R analysis')
            self.assertEqual(env['PAPER1_JOB_HASH'],driver.identity(j))
            if j['start']==1:raise RuntimeError('simulated interruption')
            rows=[dict(design=j['design'],split=j['split'],scenario=0,replicate=0,model=m,
                       availability=1,FDP=0,coverage=.95,power=None,genes=100,available=100,
                       filtered=0,discoveries=0,false_discoveries=0,true_discoveries=0,
                       null_genes=100,alternative_genes=0) for m in report.COUNT_MODELS]
            write_csv(folder/'metrics.csv',rows)
            for name in driver.COUNT_FILES[1:]:write_csv(folder/name,[])
        with patch.object(driver,'command',side_effect=fake_command):
            driver.execute(jobs[0],protocol,{'PAPER1_ATTEMPT_ID':'attempt'})
            with self.assertRaisesRegex(RuntimeError,'interruption'):
                driver.execute(jobs[1],protocol,{'PAPER1_ATTEMPT_ID':'attempt'})
        self.assertTrue(driver.valid_receipt(self.root,jobs[0],'run'))
        self.assertFalse(driver.valid_receipt(self.root,jobs[1],'run'))
        (Path(jobs[0]['output'])/'diagnostics.csv').write_text('changed')
        self.assertFalse(driver.valid_receipt(self.root,jobs[0],'run'))




if __name__=='__main__':unittest.main()
