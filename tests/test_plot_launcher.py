"""Checks for the existing-environment publication figure launcher."""
import importlib.util
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
from adjscope_tx import plotting as L


class PlotLauncherTests(unittest.TestCase):
    def test_public_entry_accepts_every_manuscript_figure(self):
        from adjscope_tx import cli
        expected = [str(i) for i in range(1, 11)] + ['S' + str(i) for i in range(1, 16)]
        self.assertEqual(list(L.FIGURES), expected)
        snapshot = dict(packages={}, font='Arial')
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(L, 'select_python', return_value=(Path('python'), snapshot)), \
             contextlib.redirect_stdout(io.StringIO()):
            output = Path(directory) / 'figures'
            self.assertEqual(cli.main([
                'figures', '--source', str(ROOT / 'inputs/evidence'),
                '--output', str(output), '--check-env', '--figures', *expected]), 0)
            self.assertFalse(output.exists())

    def test_public_entry_rejects_unknown_figure_before_rendering(self):
        from adjscope_tx import cli
        with patch.object(L, 'select_python') as select, \
             contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
            cli.main(['figures', '--source', str(ROOT / 'inputs/evidence'),
                      '--output', 'unused-output', '--figures', 'S16'])
        self.assertEqual(error.exception.code, 2)
        select.assert_not_called()

    def test_new_short_output_beside_checkout(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'repository'
            root.mkdir()
            first = L.create_output(root, None)
            second = L.create_output(root, None)
            self.assertEqual(first.parent, root.parent)
            self.assertTrue(first.name.startswith('p1_fig_'))
            self.assertLess(len(first.name), 40)
            self.assertNotEqual(first, second)

    def test_existing_output_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            sentinel = path / 'keep.txt'
            sentinel.write_text('unchanged')
            with self.assertRaisesRegex(RuntimeError, 'already exists'):
                L.create_output(path, path)
            self.assertEqual(sentinel.read_text(), 'unchanged')

    def test_explicit_python_does_not_fall_back(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(L.sys, 'executable', '/irrelevant/python'):
                self.assertEqual(list(L.candidates(root, root / 'missing')), [])

    def test_missing_bundle_stops_before_environment_selection(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(L, 'select_python') as select:
                with self.assertRaisesRegex(ValueError, 'Missing or unsafe'):
                    L.main(['--project-root', directory, '--source', directory])
                select.assert_not_called()

    def test_check_env_does_not_create_output(self):
        snapshot = dict(packages={}, font='Arial')
        with patch.object(L, 'select_python', return_value=(Path('python'), snapshot)), \
             patch('adjscope_tx.publication.Bundle') as bundle:
            bundle.return_value.verify.return_value.figures.return_value=['1']
            with patch.object(L, 'create_output') as create:
                self.assertEqual(L.main(['--project-root', str(ROOT), '--source', str(ROOT), '--check-env']), 0)
                create.assert_not_called()


class WorkflowFigureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root/'results').mkdir()
        (self.root/'results/manifest.csv').write_text('test_double\n')
        bundle = patch('adjscope_tx.publication.Bundle')
        self.bundle = bundle.start()
        self.addCleanup(bundle.stop)
        self.bundle.return_value.verify.return_value.figures.return_value = ['10','S14']

    def renderer(self, options):
        # Test files exercise publication transactions, not scientific plotting.
        out = Path(options[options.index('--output')+1])
        out.mkdir()
        for name in ('Fig10','FigS14'):
            (out/(name+'.pdf')).write_bytes(b'%PDF-test-double')
        (out/'plot_environment.json').write_text('{}')
        (out/'layout_checks.json').write_text(json.dumps([
            dict(figure=name, out_of_canvas_text=[]) for name in ('Fig10','FigS14')]))

    def test_complete_figures_reused_after_receipt_verification(self):
        with patch.object(L, 'main', side_effect=self.renderer) as render:
            L.render_workflow(self.root)
            before = {p.name:p.stat().st_mtime_ns for p in (self.root/'figures').iterdir()}
            L.render_workflow(self.root)
            render.assert_called_once()
        self.assertEqual(before, {p.name:p.stat().st_mtime_ns for p in (self.root/'figures').iterdir()})

    def test_interrupted_render_has_no_partial_final_directory(self):
        def interrupted(options):
            self.renderer(options)
            raise RuntimeError('interrupted renderer')
        with patch.object(L, 'main', side_effect=interrupted), self.assertRaisesRegex(RuntimeError, 'interrupted'):
            L.render_workflow(self.root)
        self.assertFalse((self.root/'figures').exists())
        self.assertFalse(list(self.root.glob('.figure-render-*')))
        with patch.object(L, 'main', side_effect=self.renderer):
            L.render_workflow(self.root)

    def test_changed_or_unowned_figures_never_silently_overwritten(self):
        with patch.object(L, 'main', side_effect=self.renderer):
            L.render_workflow(self.root)
        (self.root/'figures/Fig10.pdf').write_bytes(b'edited')
        with self.assertRaisesRegex(ValueError, 'changed'):
            L.render_workflow(self.root)
        (self.root/'figures.json').unlink()
        with self.assertRaisesRegex(ValueError, 'no framework receipt'):
            L.render_workflow(self.root)
        self.assertEqual((self.root/'figures/Fig10.pdf').read_bytes(), b'edited')

    def test_invalid_layout_cannot_be_published(self):
        def invalid(options):
            self.renderer(options)
            out = Path(options[options.index('--output')+1])
            (out/'layout_checks.json').write_text('[]')
        with patch.object(L, 'main', side_effect=invalid), self.assertRaisesRegex(ValueError, 'layout'):
            L.render_workflow(self.root)
        self.assertFalse((self.root/'figures').exists())


if __name__ == '__main__':
    unittest.main()
