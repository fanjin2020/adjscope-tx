"""Public API, unified execution and compact-output contracts."""
import contextlib
import csv
import gzip
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from numpy.testing import assert_allclose

from adjscope_tx import diagnose_design, compare_models
from adjscope_tx import cli, reports, workflow, plotting
from adjscope_tx.diagnostics import adjust_bh
from adjscope_tx.storage import ROOT, read_json, write_json, sha256, output_lock, separate_output
from evidence_helpers import stage_frame


class DiagnosticsTests(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(72)
        n = 40
        self.x = np.column_stack([np.ones(n), rng.normal(size=n)])
        self.z = np.column_stack([self.x, .4*self.x[:, 1] + rng.normal(size=n)])
        self.y = rng.normal(size=(n, 8)) + self.z[:, 2, None]*.8

    def test_paired_difference_and_covariance(self):
        result = compare_models(self.y, self.x, self.z)
        a0, a1 = np.linalg.pinv(self.x), np.linalg.pinv(self.z)
        d = a1[1] - a0[1]
        error = self.y - self.z @ a1 @ self.y
        se = np.sqrt((error**2).sum(axis=0)/(len(self.y)-3)*(d@d))
        assert_allclose([r['delta'] for r in result['genes']], d @ self.y)
        assert_allclose([r['paired_se'] for r in result['genes']], se)
        self.assertEqual(result['summary']['testing_family'], 8)

    def test_hc3_uses_shared_response_covariance(self):
        result = compare_models(self.y, self.x, self.z, variance='hc3')
        a0, a1 = np.linalg.pinv(self.x), np.linalg.pinv(self.z)
        d = a1[1]-a0[1]
        h = np.diag(self.z @ a1)
        e = self.y-self.z @ a1 @ self.y
        expected = np.sqrt((d*d/(1-h)**2) @ (e*e))
        assert_allclose([r['paired_se'] for r in result['genes']], expected)

    def test_row_order_invariance(self):
        a = compare_models(self.y, self.x, self.z)
        order = np.random.default_rng(6).permutation(len(self.y))
        b = compare_models(self.y[order], self.x[order], self.z[order])
        assert_allclose([r['delta'] for r in a['genes']], [r['delta'] for r in b['genes']])

    def test_rejects_malformed_inputs(self):
        for options in (dict(target=9), dict(weights=np.zeros(40)), dict(variance='auto'),
                        dict(gene_ids=['a']*8), dict(alpha=1), dict(weights=np.ones((40,8)))):
            with self.subTest(options=options), self.assertRaises(ValueError):
                compare_models(self.y, self.x, self.z, **options)
        z = self.z.copy();z[:, 1] += 1
        with self.assertRaises(ValueError):
            compare_models(self.y, self.x, z)
        bad = self.y.copy();bad[0, 0] = np.nan
        with self.assertRaises(ValueError):
            compare_models(bad, self.x, self.z)

    def test_rank_deficiency_rejected(self):
        with self.assertRaises(ValueError):
            compare_models(self.y, self.x, np.column_stack([self.z, self.z[:, 2]]))

    def test_zero_information_is_not_a_discovery(self):
        result = compare_models(np.zeros_like(self.y), self.x, self.z)
        self.assertEqual(result['summary']['available'], 0)
        self.assertTrue(all(r['q_value'] == 1 and r['p_value'] is None for r in result['genes']))

    def test_bh_and_design_geometry(self):
        assert_allclose(adjust_bh([.01,.03,.5,1]), [.04,.06,2/3,1])
        mixed = diagnose_design([0,1]*10, np.repeat(np.arange(10),2))
        pure = diagnose_design([0,0,1,1]*5, np.repeat(np.arange(10),2))
        self.assertAlmostEqual(mixed['ewi'], 1)
        self.assertEqual(pure['design_status'], 'within_effect_not_estimable')

    def test_same_operator_has_no_pairwise_test(self):
        residual = self.z[:, 2] - self.x @ np.linalg.lstsq(self.x, self.z[:, 2], rcond=None)[0]
        result = compare_models(self.y, self.x, np.column_stack([self.x,residual]))
        self.assertEqual(result['summary']['available'], 0)


class FrameworkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        publisher = patch.object(workflow, 'publish_results', side_effect=self.export_only)
        self.publisher = publisher.start()
        self.addCleanup(publisher.stop)

    def export_only(self, config, env):
        # Orchestration tests inspect CSVs; real rendering has its own smoke test.
        self.assertEqual(read_json(config.output/'workflow.json')['status'], 'FINALIZING')
        reports.index_workflow(config.output)

    def fake_stage(self, command, env, log):
        # Orchestration test double, not a research dataset.
        output = Path(command[command.index('--output')+1])
        output.mkdir(parents=True, exist_ok=True)
        write_json(output/'protocol.json', {'test_double': True})
        names = {'summary':'count_summary'} if output.name == 'counts' else {
            'summary':'tail_summary','tail_summary':'tail_rates','expression_strata':'expression_strata',
            'paired_comparisons':'paired_comparisons','gaussian_geometry':'gaussian_geometry'}
        for target, source in names.items():
            stage_frame(source).to_csv(output/(target+'.csv'),index=False)
        write_json(output/'review_manifest.json', {k+'.csv':sha256(output/(k+'.csv')) for k in names})
        self.assertEqual(env['OMP_NUM_THREADS'], '1')

    def config(self):
        return workflow.WorkflowConfig(self.root/'run', stages=('counts','tails'), profile='smoke',workers=2)

    def test_full_plan_links_design_to_new_study(self):
        config = workflow.WorkflowConfig(self.root/'full')
        graph = workflow.plan(config)
        self.assertEqual([s['stage'] for s in graph], ['study','design','counts','tails'])
        self.assertIn(str(config.output/'study/core'), graph[1]['command'])

    def test_smoke_cannot_silently_run_full_study(self):
        with self.assertRaisesRegex(ValueError,'no reduced'):
            workflow.plan(workflow.WorkflowConfig(self.root/'bad',profile='smoke'))

    def test_plan_and_environment_checks_do_not_create_output(self):
        output = self.root/'planned'
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(cli.main(['run','--output',str(output),'--plan']),0)
        self.assertFalse(output.exists())

    def test_only_job_file_does_not_trigger_resume_flag(self):
        config = self.config().validate()
        (config.output/'counts').mkdir(parents=True)
        write_json(config.output/'counts/job.json',{})
        self.assertNotIn('--resume',workflow.stage_command(config,'counts',resume=True))

    def test_success_and_compact_export(self):
        config = self.config()
        with contextlib.redirect_stdout(io.StringIO()):
            workflow.run_workflow(config,executor=self.fake_stage)
        self.assertEqual(read_json(config.output/'workflow.json')['status'],'COMPLETE')
        exported = reports.export_workflow(config.output,self.root/'result')
        self.assertTrue((exported/'tables/TableS22.csv').is_file())
        self.assertFalse((exported/'counts/protocol.json').exists())
        self.assertFalse((exported/'logs').exists())

    def test_publication_failure_never_reports_complete(self):
        config = self.config()
        self.publisher.side_effect = RuntimeError('render failed')
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaisesRegex(RuntimeError, 'render failed'):
            workflow.run_workflow(config, executor=self.fake_stage)
        record = read_json(config.output/'workflow.json')
        self.assertEqual(record['status'], 'FAILED')
        self.assertTrue(all(s['status'] == 'COMPLETE' for s in record['stages'].values()))
        self.publisher.side_effect = self.export_only
        with contextlib.redirect_stdout(io.StringIO()):
            workflow.run_workflow(config, resume=True, executor=self.fake_stage)
        self.assertNotIn('error', read_json(config.output/'workflow.json'))

    def test_output_cannot_overlap_download_cache(self):
        with self.assertRaisesRegex(ValueError, 'overlaps source'):
            workflow.WorkflowConfig(self.root/'cache/run', raw_cache=(self.root/'cache',)).validate()

    def test_incomplete_stage_cannot_be_exported_as_complete(self):
        config = self.config().validate()
        write_json(config.output/'workflow.json', dict(status='COMPLETE',
                   specification=config.specification(), stages={'counts': {'status': 'COMPLETE'}}))
        with self.assertRaisesRegex(ValueError, 'incomplete analysis'):
            reports.workflow_sources(config.output)

    def test_interruption_and_recorded_resume(self):
        config = self.config()
        calls = []
        def interrupted(command,env,log):
            calls.append(command)
            if len(calls)==2:
                raise KeyboardInterrupt
            self.fake_stage(command,env,log)
        with contextlib.redirect_stdout(io.StringIO()),self.assertRaises(KeyboardInterrupt):
            workflow.run_workflow(config,executor=interrupted)
        self.assertEqual(read_json(config.output/'workflow.json')['status'],'INTERRUPTED')
        args = cli.parser().parse_args(['run','--resume','--output',str(config.output),'--workers','1'])
        resumed = cli.configure(args)
        self.assertEqual(resumed.profile,'smoke')
        self.assertEqual(resumed.workers,1)
        with contextlib.redirect_stdout(io.StringIO()):
            workflow.run_workflow(resumed,resume=True,executor=self.fake_stage)
        self.assertEqual(read_json(config.output/'workflow.json')['status'],'COMPLETE')

    def test_mismatched_resume_rejected_before_execution(self):
        config = self.config()
        with contextlib.redirect_stdout(io.StringIO()):
            workflow.run_workflow(config,executor=self.fake_stage)
        config.profile='pilot'
        with self.assertRaisesRegex(ValueError,'settings changed'):
            workflow.run_workflow(config,resume=True,executor=lambda *a:self.fail('executed'))
        config.profile='smoke'
        with patch.object(workflow,'source_identity',return_value='different'):
            with self.assertRaisesRegex(ValueError,'source or output'):
                workflow.run_workflow(config,resume=True,executor=lambda *a:self.fail('executed'))

    def test_compact_export_rejects_changed_summary(self):
        config=self.config()
        with contextlib.redirect_stdout(io.StringIO()):
            workflow.run_workflow(config,executor=self.fake_stage)
        (config.output/'counts/summary.csv').write_text('changed')
        with self.assertRaisesRegex(ValueError,'changed|checksum'):
            reports.export_workflow(config.output,self.root/'export')
        self.assertFalse((self.root/'export').exists())

    def test_conflicting_writer_refused(self):
        with output_lock(self.root/'locked'):
            with self.assertRaisesRegex(RuntimeError,'writer'):
                with output_lock(self.root/'locked'):
                    self.fail('second writer')

    def test_all_figures_in_public_default(self):
        self.assertEqual(set(plotting.FIGURES),{str(i) for i in range(1,11)}|{'S'+str(i) for i in range(1,16)})

    def test_cmpb_publication_tables_and_workbook(self):
        from openpyxl import load_workbook
        from adjscope_tx.publication import Bundle, ARCHIVE_SCHEMA
        with contextlib.redirect_stdout(io.StringIO()):
            output=reports.export_publication(self.root/'publication')
        bundle=Bundle(output).verify()
        tables=[e for e in bundle.entries if e['kind']=='table']
        self.assertEqual(len(ARCHIVE_SCHEMA['tables']),98)
        self.assertEqual(len(tables),100)
        self.assertEqual(sum(int(e['rows']) for e in tables),15853)
        self.assertEqual(len(list((output/'tables').glob('*.csv'))),26)
        self.assertEqual(len(bundle.figures()),25)
        path=output/'Supplementary_Tables.xlsx'
        self.assertEqual({p for p in output.rglob('*') if p.is_file() and p.suffix!='.csv'},{path})
        wb=load_workbook(path,read_only=True)
        try:
            self.assertEqual(wb.sheetnames,['Catalogue']+[f'S{n:02d}' for n in range(1,24)])
            catalog={r[0]:r[1:5] for r in wb['Catalogue'].iter_rows(min_row=4,max_col=6,values_only=True)}
            self.assertEqual(catalog['S9.5'],('S09',57,2,7))
            self.assertEqual(catalog['S11.7'],('S11',5093,3,5))
            self.assertEqual(catalog['S22.1'],('S22',5,96,20))
            from adjscope_tx.supplement_workbook import workbook_value
            self.assertEqual(workbook_value('S2.1','base_significant',False),'False')
            self.assertEqual(workbook_value('S6.5','available',True),'TRUE')
            self.assertIs(workbook_value('S1.2','another_flag',False),False)
            self.assertEqual(workbook_value('S20.2','value','0.05'),.05)
            self.assertEqual(workbook_value('S19.6','sample','211'),211)
            self.assertEqual(workbook_value('S19.6','sample','0211'),'0211')
            self.assertEqual(workbook_value('S19.6','sample','1234567890123456'),'1234567890123456')
            for key in ('S9.5','S11.7'):
                sheet,header,rows,cols=catalog[key]
                xf=list(wb[sheet].iter_rows(min_row=header,max_row=header+rows,max_col=cols,values_only=True))
                source=bundle.read('table',key)
                self.assertEqual(list(xf[0]),list(source))
                for a,b in zip(xf[1:],source.itertuples(index=False,name=None)):
                    for x,y in zip(a,b):
                        if isinstance(y,float): self.assertAlmostEqual(x,y,places=14)
                        else: self.assertEqual(x,y)
        finally:
            wb.close()
        with path.open('ab') as f:
            f.write(b'tampered')
        with self.assertRaisesRegex(ValueError,'workbook changed'):
            Bundle(output).verify()

    def test_relative_paths_are_resolved_before_subprocess_changes_directory(self):
        c=workflow.WorkflowConfig(self.root/'planned',stages=('design',),data_work=Path('prepared'),
            raw_cache=('cache',),r_library=('R_library',),python_package_path=('packages',)).validate()
        command=workflow.stage_command(c,'design')
        self.assertEqual(command[command.index('--data-work')+1],str(Path('prepared').resolve()))
        self.assertEqual(c.specification()['data_work'],str(c.data_work))
        self.assertTrue(all(Path(v).is_absolute() for v in (*c.raw_cache,*c.r_library,*c.python_package_path)))


if __name__=='__main__':
    unittest.main()
