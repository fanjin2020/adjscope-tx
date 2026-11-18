"""Publication-only recovery must not change or refit completed analyses."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from adjscope_tx import reports
from adjscope_tx.cli import parser
from adjscope_tx.storage import read_json,write_json,sha256,source_files,source_digest
from evidence_helpers import stage_frame


class FinalizationTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)/'run'
        (self.root/'counts').mkdir(parents=True)
        stage_frame('count_summary').to_csv(self.root/'counts/summary.csv',index=False)
        write_json(self.root/'counts/review_manifest.json',{'summary.csv':sha256(self.root/'counts/summary.csv')})
        self.original=source_files()
        self.original['publication_figures/design_figures.py']='0'*64
        self.record=dict(output=str(self.root),source_sha256=source_digest(self.original),
            specification=dict(stages=['counts'],python='existing-python',rscript='Rscript'),
            status='FINALIZING',stages={'counts':dict(status='COMPLETE',finished=123)})
        write_json(self.root/'workflow.json',self.record)
        reports.index_workflow(self.root)
        self.record.update(status='FAILED',error='Figure label outside canvas')
        write_json(self.root/'workflow.json',self.record)
        self.proof=self.root.parent/'source.json'
        write_json(self.proof,self.original)

    def renderer(self,output,**kwargs):
        self.assertEqual(Path(output),self.root)
        write_json(self.root/'figures.json',{'test_double':True})

    def finish(self,**kwargs):
        return reports.finish_existing_workflow(self.root,analysis_source_manifest=self.proof,**kwargs)

    def test_success_preserves_analysis_identity_values_and_stage_times(self):
        before={p:sha256(p) for p in self.root.rglob('*.csv')}
        with patch('adjscope_tx.plotting.render_workflow',side_effect=self.renderer), \
             patch('subprocess.run',side_effect=AssertionError('Finalization invoked an analysis process')):
            self.finish()
        record=read_json(self.root/'workflow.json')
        self.assertEqual(record['status'],'COMPLETE')
        self.assertEqual(record['source_sha256'],self.record['source_sha256'])
        self.assertEqual(record['stages'],self.record['stages'])
        self.assertFalse(record['publication']['analysis_refitted'])
        self.assertEqual(set(record['publication']['source_changes']),{'publication_figures/design_figures.py'})
        self.assertEqual(before,{p:sha256(p) for p in before})
        self.assertNotIn('error',record)
        with patch('adjscope_tx.plotting.render_workflow',side_effect=self.renderer):
            reports.finish_existing_workflow(self.root)

    def test_incomplete_analysis_is_rejected(self):
        self.record['stages']['counts']['status']='RUNNING'
        write_json(self.root/'workflow.json',self.record)
        with self.assertRaisesRegex(ValueError,'incomplete analysis'):
            self.finish()

    def test_legacy_source_change_requires_verified_original_manifest(self):
        with self.assertRaisesRegex(ValueError,'Legacy source changed'):
            reports.finish_existing_workflow(self.root)
        write_json(self.proof,dict(self.original,**{'run.py':'f'*64}))
        with self.assertRaisesRegex(ValueError,'does not match'):
            self.finish()

    def test_analysis_changes_cannot_be_hidden_by_publication_recovery(self):
        changed=dict(self.original,**{'pipeline/core.py':'f'*64})
        with self.assertRaisesRegex(ValueError,'Analysis/input code changed'):
            reports.publication_source_changes(changed,source_files(),source_digest(changed))

    def test_changed_source_file_set_is_rejected(self):
        changed=dict(self.original,**{'pipeline/new.py':'f'*64})
        with self.assertRaisesRegex(ValueError,'file set changed'):
            reports.publication_source_changes(changed,source_files(),source_digest(changed))

    def test_changed_exported_csv_is_rejected(self):
        path=self.root/'results/tables/TableS22.csv'
        path.write_text(path.read_text()+'\n')
        with self.assertRaises(ValueError):
            self.finish()

    def test_changed_analysis_input_is_rejected(self):
        path=self.root/'counts/summary.csv'
        path.write_text(path.read_text()+'\n')
        with self.assertRaisesRegex(ValueError,'Analysis input'):
            self.finish()

    def test_failed_render_does_not_mark_workflow_complete(self):
        before=(self.root/'workflow.json').read_bytes()
        with patch('adjscope_tx.plotting.render_workflow',side_effect=RuntimeError('render failed')), \
             self.assertRaisesRegex(RuntimeError,'render failed'):
            self.finish()
        self.assertEqual(before,(self.root/'workflow.json').read_bytes())

    def test_source_change_during_render_is_rejected(self):
        current=source_files()
        with patch('adjscope_tx.plotting.render_workflow',side_effect=self.renderer), \
             patch('adjscope_tx.reports.source_files',side_effect=[current,dict(current,extra='changed')]), \
             self.assertRaisesRegex(ValueError,'changed during finalization'):
            self.finish()

    def test_command_exposes_no_model_fitting_options(self):
        args=parser().parse_args(['finalize','--output',str(self.root),
                                 '--analysis-source-manifest',str(self.proof)])
        self.assertEqual(args.command,'finalize')
        self.assertFalse(hasattr(args,'workers'))


if __name__=='__main__':
    unittest.main()
