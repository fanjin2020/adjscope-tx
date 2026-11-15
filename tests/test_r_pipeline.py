"""Opt-in count-to-figure smoke test using an existing R installation."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from adjscope_tx.publication import Bundle, Computed, write_bundle
from adjscope_tx.storage import ROOT
from adjscope_tx.plotting import render_workflow


@unittest.skipUnless(os.environ.get('ADJSCOPE_TEST_R'), 'Set ADJSCOPE_TEST_R for real R smoke validation')
class RPipelineTests(unittest.TestCase):
    def test_counts_tails_export_and_resume(self):
        with tempfile.TemporaryDirectory(prefix='adjscope-r-') as directory:
            root = Path(directory)
            env = os.environ.copy()
            env['PYTHONPATH'] = str(ROOT) + os.pathsep + env.get('PYTHONPATH','')
            if os.name == 'nt':
                env.update(LC_ALL='English_United States.utf8', LANG='English_United States.utf8')
            for stage, module, datasets in [('counts','paired_count_calibration',4),
                                            ('tails','paired_tail_diagnostics',6)]:
                command = [sys.executable,'-B','-m',module+'.driver','--output',str(root/stage),
                           '--profile','smoke','--workers','2','--rscript',env['ADJSCOPE_TEST_R']]
                if env.get('ADJSCOPE_TEST_R_LIBRARY'):
                    command += ['--r-library',env['ADJSCOPE_TEST_R_LIBRARY']]
                if env.get('ADJSCOPE_TEST_ALLOW_VERSION_DRIFT') == '1':
                    command.append('--allow-version-drift')
                subprocess.run(command,cwd=ROOT,env=env,check=True,stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT,text=True,encoding='utf-8',timeout=300)
                before={str(p):p.stat().st_mtime_ns for p in (root/stage/'tasks').rglob('receipt.json')}
                self.assertEqual(len(before),datasets)
                subprocess.run(command+['--resume'],cwd=ROOT,env=env,check=True,stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT,text=True,encoding='utf-8',timeout=300)
                self.assertEqual(before,{name:Path(name).stat().st_mtime_ns for name in before})
                self.assertFalse((root/stage/'replicate_metrics.csv').exists())
                tasks=[Path(name).parent for name in sorted(before)]
                originals={task:json.loads((task/'result.json').read_text()) for task in tasks}
                damaged=tasks[0]/('events.csv.gz' if stage=='tails' else 'result.json')
                damaged.write_bytes(damaged.read_bytes()+b' ')
                (tasks[1]/'receipt.json').unlink()
                for name in ('result.json','receipt.json','events.csv.gz'):
                    (tasks[2]/name).unlink(missing_ok=True)
                (tasks[2]/'job.json').write_text('{}')
                subprocess.run(command+['--resume'],cwd=ROOT,env=env,check=True,stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT,text=True,encoding='utf-8',timeout=300)
                for task,original in originals.items():
                    current=json.loads((task/'result.json').read_text())
                    original.pop('attempt',None);current.pop('attempt',None)
                    self.assertEqual(original,current,'Seeded results changed after checkpoint recovery')
                self.assertFalse(list((root/stage).glob('*.zip')))
            result = write_bundle(Computed({s:root/s for s in ('counts','tails')}),root/'results')
            bundle = Bundle(result).verify()
            self.assertEqual(len(bundle.read('table','S22.1')),16)
            self.assertEqual(len(bundle.read('table','S23.1')),72)
            self.assertTrue(bundle.read('table','S22.1').datasets.eq(1).all())
            self.assertTrue({'10','S14','S15'} <= set(bundle.figures()))
            self.assertTrue(all(p.suffix=='.csv' for p in result.rglob('*') if p.is_file()))
            render_workflow(root, python=sys.executable)
            figures = {p.name:p.stat().st_mtime_ns for p in (root/'figures').glob('*.pdf')}
            self.assertEqual(set(figures), {'Fig'+name+'.pdf' for name in bundle.figures()})
            render_workflow(root, python=sys.executable)
            self.assertEqual(figures, {p.name:p.stat().st_mtime_ns for p in (root/'figures').glob('*.pdf')})


if __name__=='__main__':
    unittest.main()
