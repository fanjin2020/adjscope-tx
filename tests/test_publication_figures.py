"""Manuscript figure inputs, dependencies and integrity checks."""

import ast
import csv
import gzip
import hashlib
from pathlib import Path, PurePosixPath
import unittest
from adjscope_tx.publication import Bundle, SCHEMA


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'publication_figures'
FIGURES = {str(i) for i in range(1, 11)} | {'S' + str(i) for i in range(1, 16)}


class PublicationFigureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = Bundle(ROOT/'inputs/evidence').verify()
        cls.records = [e for e in cls.bundle.entries if e['kind']=='figure_data']
        cls.tree = ast.parse((PACKAGE / 'make_figures.py').read_text(encoding='utf-8'))

    def test_complete_manifest_with_portable_paths(self):
        self.assertEqual(len(self.records), 30)
        indexed = {row['file'] for row in self.records}
        self.assertLess(len(indexed), len(self.records))
        self.assertFalse((PACKAGE/'data').exists())
        for row in self.records:
            for column in ['file']:
                path = PurePosixPath(row[column])
                self.assertFalse(path.is_absolute())
                self.assertNotIn('..', path.parts)
                self.assertNotIn(':', row[column])
                self.assertNotIn('\\', row[column])
            self.assertIn(PurePosixPath(row['file']).parts[0], ('tables','figure_data'))

    def test_checksums_and_row_counts(self):
        for row in self.records:
            with self.subTest(file=row['file']):
                path = self.bundle.root / row['file']
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), row['sha256'])
                self.assertEqual(len(self.bundle.read('figure_data',row['id'])),int(row['rows']))

    def test_figure_functions_and_data_coverage(self):
        functions = {node.name for node in self.tree.body if isinstance(node, ast.FunctionDef)}
        expected = {'fig' + str(i) for i in range(1, 9)}
        expected |= {'figs' + str(i) for i in range(1, 13)}
        self.assertTrue(expected.issubset(functions))
        extension = ast.parse((PACKAGE/'design_figures.py').read_text(encoding='utf-8'))
        self.assertTrue({'fig9','figs13'}.issubset({n.name for n in extension.body if isinstance(n,ast.FunctionDef)}))
        calibration = ast.parse((PACKAGE/'calibration_figures.py').read_text(encoding='utf-8'))
        self.assertTrue({'fig10','figs14','figs15'}.issubset({n.name for n in calibration.body if isinstance(n,ast.FunctionDef)}))
        referenced = {figure for row in self.records for figure in row['figures'].split(';') if figure}
        self.assertEqual(referenced, FIGURES - {'S9'})
        for node in ast.walk(self.tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == 'read' and node.args
                    and isinstance(node.args[0], ast.Constant)):
                self.assertIn(node.args[0].value, {row['id'] for row in self.records})

    def test_default_output_is_package_local_and_ignored(self):
        options = [node for node in ast.walk(self.tree)
                   if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                   and node.func.attr == 'add_argument' and node.args
                   and isinstance(node.args[0], ast.Constant)
                   and node.args[0].value == '--output']
        self.assertEqual(len(options), 1)
        default = next(item.value for item in options[0].keywords if item.arg == 'default')
        self.assertEqual(ast.dump(default), ast.dump(ast.parse("ROOT / 'output'", mode='eval').body))
        self.assertIn('/publication_figures/output/', (ROOT / '.gitignore').read_text().splitlines())

    def test_analysis_pipeline_does_not_read_fixed_plot_extracts(self):
        paths = list((ROOT / 'pipeline').rglob('*.py'))
        paths += [ROOT / 'run.py', ROOT / 'adjscope_tx/environment.py']
        for path in paths:
            with self.subTest(file=path.relative_to(ROOT).as_posix()):
                self.assertNotIn('publication_figures', path.read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
