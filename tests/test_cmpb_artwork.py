import unittest
from unittest.mock import patch

from adjscope_tx import cli
from adjscope_tx.storage import ROOT, sha256


class CMPBArtworkTests(unittest.TestCase):
    options = ['figures', '--source', 'data', '--output', 'plates']

    def test_opt_in_keeps_archive_default(self):
        self.assertEqual(cli.parser().parse_args(self.options).layout, 'archive')
        self.assertEqual(sha256(ROOT/'artwork/cmpb/framework.pdf'),
                         '60d49fcc3283ad61e91cdce61b14c3fe96fe447a3315c628cd29e2a6c4b9bc4c')

    def test_separate_interpreter_and_error_propagation(self):
        with patch.object(cli.subprocess, 'run') as run:
            run.return_value.returncode = 2
            self.assertEqual(cli.main(self.options + ['--layout', 'cmpb', '--check-env', '--python', 'graphics-python']), 2)
            cmd = run.call_args.args[0]
            self.assertEqual(cmd[:4], ['graphics-python', '-B', '-m', 'artwork.cmpb.redraw_figures'])
            self.assertIn('--check-env', cmd)
            self.assertEqual(run.call_args.kwargs['cwd'], ROOT)

    def test_incompatible_options_do_not_silently_drop_or_overwrite_artwork(self):
        for layout in ('cmpb', 'cmpb-supplement'):
            for extra in (['--figures','2'], ['--editable'], ['--tiff']):
                with self.subTest(layout=layout, extra=extra), self.assertRaisesRegex(ValueError,'archive-only'):
                    cli.main(self.options + ['--layout',layout] + extra)

    def test_supplement_layout_uses_its_own_renderer(self):
        with patch.object(cli.subprocess, 'run') as run:
            run.return_value.returncode = 0
            self.assertEqual(cli.main(self.options + ['--layout','cmpb-supplement','--python','graphics-python']), 0)
            self.assertEqual(run.call_args.args[0][:4], ['graphics-python','-B','-m','artwork.cmpb.supplement'])

    def test_s9_source_preserves_paired_designs_and_method_medians(self):
        from adjscope_tx.publication import Bundle
        source = Bundle(ROOT / 'inputs/evidence')
        z = source.read('figure_data', 'general_calibration')
        z = z.loc[(z.status == 'regular') & (z.error_law == 'matched_gaussian')]
        methods = ['model_based','HC3','independence_comparator']
        for case, expected in [('quality_zero',[4.97,4.45,0.00]), ('delta_two_reference_SD',[50.34,46.42,0.00])]:
            t = z.loc[z.mean_case == case].pivot(index='design',columns='method',values='rejection')
            self.assertEqual(t.shape, (30,3))
            self.assertFalse(t.isna().any().any())
            self.assertEqual((100*t[methods].median()).round(2).tolist(), expected)
        self.assertAlmostEqual(100*t['independence_comparator'].max(), 8.12)
