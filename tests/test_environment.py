"""Version, code identity and coverage regression checks without network access."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from pipeline import study_runner as run
from adjscope_tx import environment as launcher
from pipeline import core, coverage, environment, lifecycle


class EnvironmentTests(unittest.TestCase):
    def fixture(self, root):
        for name in ('pipeline', 'analysis', 'tests', 'inputs'):
            (root / name).mkdir()
        for name in ('run.py', 'config.json'):
            (root / name).write_text('initial', encoding='utf-8')
        (root / 'requirements.txt').write_text('numpy==2.2.6\n', encoding='utf-8')
        (root / 'inputs/environment.json').write_text('{}', encoding='utf-8')

    def record(self):
        return {'python': {'python': '3.12.2', 'packages': {'numpy': '2.2.6'}, 'executable': 'a'},
                'R': {'R': '4.5.3', 'packages': {'limma': '3.66.0'}, 'paths': {'limma': 'a'}}}

    def test_environment_file_changes_code_identity(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self.fixture(root)
            identity = lifecycle.code_identity(root)
            (root / 'inputs/environment.json').write_text('{"changed":true}')
            with self.assertRaisesRegex(ValueError, 'changed during execution'):
                lifecycle.assert_code(root, identity)

    def test_tests_are_part_of_release_identity(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self.fixture(root)
            identity = lifecycle.code_identity(root)
            (root / 'tests/test_new.py').write_text('pass')
            self.assertNotEqual(identity, lifecycle.code_identity(root))

    def test_launcher_is_part_of_release_identity(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self.fixture(root)
            identity = lifecycle.code_identity(root)
            (root / 'adjscope_tx').mkdir()
            (root / 'adjscope_tx/environment.py').write_text('pass')
            self.assertNotEqual(identity, lifecycle.code_identity(root))

    def test_version_drift_rejected_without_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'software.json'
            record = self.record()
            environment.freeze_environment(path, record)
            before = path.read_bytes()
            record['python']['packages']['numpy'] = '2.5.3'
            with self.assertRaisesRegex(ValueError, 'Software versions changed'):
                environment.freeze_environment(path, record)
            self.assertEqual(before, path.read_bytes())

    def test_r_version_drift_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'software.json'
            record = self.record()
            environment.freeze_environment(path, record)
            record['R']['packages']['limma'] = 'other'
            with self.assertRaisesRegex(ValueError, 'Software versions changed'):
                environment.freeze_environment(path, record)

    def test_installation_location_is_not_science(self):
        a, b = self.record(), self.record()
        b['python']['executable'] = 'b'
        b['R']['paths']['limma'] = 'b'
        self.assertEqual(environment.scientific_identity(a), environment.scientific_identity(b))

    def test_transitive_r_version_is_part_of_identity(self):
        a, b = self.record(), self.record()
        a['R']['loaded_namespaces'] = {'Rcpp': '1.1.2'}
        b['R']['loaded_namespaces'] = {'Rcpp': 'other'}
        self.assertNotEqual(environment.scientific_identity(a), environment.scientific_identity(b))

    def test_exact_python_pins(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self.fixture(root)
            with patch.object(environment.sys, 'version_info', (3,12,0)), patch.object(environment.importlib, 'import_module', return_value=SimpleNamespace(__version__='2.5.3')):
                with self.assertRaisesRegex(ValueError, 'expected 2.2.6, found 2.5.3'):
                    environment.python_snapshot(root)

    def test_r_probe_checks_failure(self):
        with patch.object(environment.subprocess, 'run', return_value=SimpleNamespace(returncode=1, stdout='', stderr='missing limma')):
            with self.assertRaisesRegex(ValueError, 'missing limma'):
                environment.r_snapshot('Rscript', [])

    def test_r_probe_parses_marked_record(self):
        result = SimpleNamespace(returncode=0, stderr='', stdout='message\nPAPER1_ENVIRONMENT\t{"R":"4.5.3"}\n')
        with patch.object(environment.subprocess, 'run', return_value=result):
            self.assertEqual(environment.r_snapshot('Rscript', []), {'R': '4.5.3'})

    def test_full_coverage_gate_before_subprocess(self):
        from pipeline import coverage
        missing={'complete_paper':False,'missing':[{'id':'example','description':'missing implementation'}]}
        with patch.object(coverage,'report',return_value=missing), \
             patch.object(run.subprocess, 'run', side_effect=AssertionError('must not run')):
            with self.assertRaisesRegex(ValueError, 'FULL-PAPER REPRODUCTION NOT READY'):
                run.main(['--require-complete-paper'])


    def test_coverage_is_read_only(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / 'not_created'
            with contextlib.redirect_stdout(io.StringIO()) as text:
                self.assertEqual(run.main(['--coverage', '--output', str(out)]), 0)
            self.assertTrue(json.loads(text.getvalue())['complete_paper'])
            self.assertFalse(out.exists())


    def test_bad_python_candidate_never_selected(self):
        with patch.object(launcher, 'python_candidates', return_value=[Path('/bad/python')]), \
             patch.object(launcher.subprocess, 'run', return_value=SimpleNamespace(returncode=1, stdout='', stderr='bad')):
            with contextlib.redirect_stdout(io.StringIO()), self.assertRaisesRegex(RuntimeError, 'No compatible'):
                launcher.select_python()

    def test_good_python_candidate(self):
        result = SimpleNamespace(returncode=0, stderr='', stdout='PAPER1_PYTHON\t{"python":"3.12.2"}\n')
        with patch.object(launcher, 'python_candidates', return_value=[Path('/good/python')]), \
             patch.object(launcher.subprocess, 'run', return_value=result):
            path, record = launcher.select_python()
            self.assertEqual(record['python'], '3.12.2')
            self.assertEqual(path, Path('/good/python'))

    def test_explicit_python_path_is_not_resolved(self):
        with tempfile.TemporaryDirectory() as d:
            exe = Path(d) / 'venv' / 'bin' / 'python'
            exe.parent.mkdir(parents=True)
            exe.touch()
            with patch.object(Path, 'resolve', side_effect=AssertionError('must retain venv path')):
                self.assertEqual(launcher.python_candidates(str(exe)), [exe.absolute()])

    def test_nested_venv_is_discovered(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / 'paper1-from-publicV1'
            exe = root / 'paper1-from-public' / '.raw-reproduction-venv' / 'bin' / 'python'
            exe.parent.mkdir(parents=True)
            exe.touch()
            with patch.object(launcher, 'ROOT', root), \
                 patch.object(Path, 'resolve', side_effect=AssertionError('must retain venv path')):
                candidates = launcher.python_candidates()
            self.assertIn(exe.absolute(), candidates)
            self.assertEqual(candidates.count(exe.absolute()), 1)

    def test_venvs_sharing_python_target_remain_distinct(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / 'paper1-from-publicV1'
            target = Path(sys.executable).resolve()
            executables = [root / name / 'bin' / 'python'
                           for name in ('.raw-reproduction-venv', '.venv')]
            for exe in executables:
                exe.parent.mkdir(parents=True)
                try:
                    exe.symlink_to(target)
                except (OSError, NotImplementedError) as exc:
                    self.skipTest('OS does not permit executable symlinks: ' + str(exc))
            with patch.object(launcher, 'ROOT', root), patch.object(launcher.sys, 'executable', str(target)):
                candidates = launcher.python_candidates()
                self.assertIn(target, candidates)
                for exe in executables:
                    self.assertIn(exe, candidates)
                    self.assertEqual(launcher.python_candidates(str(exe)), [exe])
                bad = SimpleNamespace(returncode=1, stdout='', stderr='base version mismatch')
                good = SimpleNamespace(returncode=0, stderr='', stdout='PAPER1_PYTHON\t{"python":"3.12.2"}\n')
                with patch.object(launcher.subprocess, 'run', side_effect=[bad, good]) as probe, \
                     contextlib.redirect_stdout(io.StringIO()):
                    selected, _ = launcher.select_python()
                self.assertEqual(selected, executables[0])
                self.assertEqual(probe.call_args_list[1].args[0][0], str(executables[0]))

    def test_related_software_environment_is_discovered(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / 'paper1-from-publicV1'
            root.mkdir()
            exe = Path(d) / 'paper1_public_evidence' / 'paper3_mechanism_source_example' / '.venv' / 'bin' / 'python'
            exe.parent.mkdir(parents=True)
            exe.touch()
            with patch.object(launcher, 'ROOT', root):
                self.assertIn(exe, launcher.python_candidates())

    def test_broken_executable_does_not_hide_compatible_python(self):
        good = SimpleNamespace(returncode=0, stderr='', stdout='PAPER1_PYTHON\t{"python":"3.12.2"}\n')
        with patch.object(launcher, 'python_candidates', return_value=[Path('/bad/python'), Path('/good/python')]), \
             patch.object(launcher.subprocess, 'run', side_effect=[OSError('cannot execute'), good]), \
             contextlib.redirect_stdout(io.StringIO()):
            path, _ = launcher.select_python()
            self.assertEqual(path, Path('/good/python'))

    def test_timeout_does_not_hide_compatible_python(self):
        good = SimpleNamespace(returncode=0, stderr='', stdout='PAPER1_PYTHON\t{"python":"3.12.2"}\n')
        error = launcher.subprocess.TimeoutExpired('python', 180)
        with patch.object(launcher, 'python_candidates', return_value=[Path('/bad/python'), Path('/good/python')]), \
             patch.object(launcher.subprocess, 'run', side_effect=[error, good]), \
             contextlib.redirect_stdout(io.StringIO()):
            path, _ = launcher.select_python()
            self.assertEqual(path, Path('/good/python'))

    def test_corrupt_probe_record_is_rejected(self):
        result = SimpleNamespace(returncode=0, stderr='', stdout='PAPER1_PYTHON\tINVALID\n')
        with patch.object(launcher, 'python_candidates', return_value=[Path('/bad/python')]), \
             patch.object(launcher.subprocess, 'run', return_value=result), \
             contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(RuntimeError, 'No compatible'):
                launcher.select_python()

    def check_cli_environment(self, directory, options=(), resume=False):
        from adjscope_tx import cli
        from adjscope_tx.workflow import WorkflowConfig
        output = Path(directory) / 'run'
        if resume:
            output.mkdir()
            saved = WorkflowConfig(output=output, python='/recorded/python').specification()
            (output / 'workflow.json').write_text(json.dumps({'specification': saved}))
        arguments = ['run', '--output', str(output), '--check-env', *options]
        if resume:
            arguments.append('--resume')
        with contextlib.redirect_stdout(io.StringIO()), \
             patch.object(launcher, 'select_r', return_value=('Rscript', [], {'R': 'test'})):
            self.assertEqual(cli.execute_run(cli.parser().parse_args(arguments)), 0)
        if not resume:
            self.assertFalse(output.exists())

    def test_fresh_cli_does_not_treat_bootstrap_python_as_explicit(self):
        with tempfile.TemporaryDirectory() as d, \
             patch.object(launcher, 'select_python', return_value=(Path('/compatible/python'), {})) as select:
            self.check_cli_environment(d)
        select.assert_called_once_with(None, supplementary=True, package_paths=())

    def test_fresh_cli_retains_explicit_python(self):
        with tempfile.TemporaryDirectory() as d, \
             patch.object(launcher, 'select_python', return_value=(Path('/chosen/python'), {})) as select:
            self.check_cli_environment(d, ('--python', '/chosen/python'))
        select.assert_called_once_with('/chosen/python', supplementary=True, package_paths=())

    def test_resume_cli_retains_recorded_python(self):
        with tempfile.TemporaryDirectory() as d, \
             patch.object(launcher, 'select_python', return_value=(Path('/recorded/python'), {})) as select:
            self.check_cli_environment(d, resume=True)
        select.assert_called_once_with('/recorded/python', supplementary=True, package_paths=())

    def test_fresh_cli_falls_back_after_incompatible_current_environment(self):
        bad = SimpleNamespace(returncode=1, stdout='', stderr='numpy version mismatch')
        good = SimpleNamespace(returncode=0, stderr='', stdout='PAPER1_PYTHON\t{"python":"3.12.2"}\n')
        with tempfile.TemporaryDirectory() as d, \
             patch.object(launcher, 'python_candidates', return_value=[Path('/bad/python'), Path('/good/python')]) as candidates, \
             patch.object(launcher.subprocess, 'run', side_effect=[bad, good]) as probe:
            self.check_cli_environment(d)
        candidates.assert_called_once_with(None)
        self.assertEqual(probe.call_args_list[1].args[0][0], str(Path('/good/python')))

    def stage_fixture(self, base):
        root, work = base / 'source', base / 'work'
        root.mkdir()
        work.mkdir()
        self.fixture(root)
        (work / 'stages').mkdir()
        (work / 'fresh_run.json').write_text(json.dumps({'code': lifecycle.code_identity(root)}))
        (work / 'owner.json').write_text(json.dumps({'signature': 'fixture'}))
        return root, work

    def test_stage_rejects_empty_receipt(self):
        with tempfile.TemporaryDirectory() as d:
            root, work = self.stage_fixture(Path(d))
            (work / 'stages/example.json').write_text(json.dumps({'signature': 'fixture', 'outputs': {}}))
            with patch.object(core, 'ROOT', root), self.assertRaises(ValueError):
                core.stage('example', lambda: self.fail('must not run'), ['result.csv'], work, True)

    def test_stage_rejects_receipt_path_escape(self):
        with tempfile.TemporaryDirectory() as d:
            root, work = self.stage_fixture(Path(d))
            receipt = {'signature': 'fixture', 'outputs': {'../outside.csv': 'invalid'}}
            (work / 'stages/example.json').write_text(json.dumps(receipt))
            with patch.object(core, 'ROOT', root), self.assertRaisesRegex(ValueError, 'outside'):
                core.stage('example', lambda: self.fail('must not run'), ['result.csv'], work, True)

    def test_stage_checks_source_before_work(self):
        with tempfile.TemporaryDirectory() as d:
            root, work = self.stage_fixture(Path(d))
            (root / 'run.py').write_text('changed')
            with patch.object(core, 'ROOT', root), self.assertRaisesRegex(ValueError, 'changed during execution'):
                core.stage('example', lambda: self.fail('must not run'), ['result.csv'], work, False)

    def test_stage_never_receipts_work_after_source_mutation(self):
        with tempfile.TemporaryDirectory() as d:
            root, work = self.stage_fixture(Path(d))
            def compute():
                (work / 'result.csv').write_text('result')
                (root / 'run.py').write_text('changed')
            with patch.object(core, 'ROOT', root), contextlib.redirect_stdout(io.StringIO()), \
                 self.assertRaisesRegex(ValueError, 'changed during execution'):
                core.stage('example', compute, ['result.csv'], work, False)
            self.assertFalse((work / 'stages/example.json').exists())


class PythonSetupTests(unittest.TestCase):
    @contextlib.contextmanager
    def fixture(self):
        from adjscope_tx import workflow
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / 'code'
            root.mkdir()
            (root / 'requirements.txt').write_text('numpy==2.2.6\nopenpyxl==3.1.5\n')
            (root / 'requirements-supplementary.txt').write_text('-r requirements.txt\nscrublet>=0.2.3,<0.3\n')
            output = Path(d) / 'runtime'
            venv = output / 'environment'
            exe = venv / ('Scripts/python.exe' if launcher.os.name == 'nt' else 'bin/python')
            record = {'python': '3.12.2', 'executable': str(exe), 'packages': {'openpyxl': '3.1.5'},
                      'supplementary_packages': {'scrublet': '0.2.3'}}
            state = SimpleNamespace(root=root, output=output, exe=exe, record=record,
                                    calls=[], fail_install=False, mutate_requirements=False)

            def stage(command, env, log):
                state.calls.append(command)
                self.assertNotIn('PYTHONPATH', env)
                self.assertNotIn('PIP_TARGET', env)
                self.assertEqual(env['PIP_CONFIG_FILE'], launcher.os.devnull)
                self.assertEqual(env['R_LIBS'], '/unchanged/R/library')
                if 'venv' in command:
                    exe.parent.mkdir(parents=True, exist_ok=True)
                    exe.touch()
                if 'install' in command and state.fail_install:
                    raise RuntimeError('simulated interrupted package download')
                if 'install' in command and state.mutate_requirements:
                    (root / 'requirements.txt').write_text('numpy==9.0.0\n')

            probe = SimpleNamespace(returncode=0, stdout=json.dumps([str(venv), str(Path(d) / 'base')]))
            with patch.object(launcher, 'ROOT', root), \
                 patch.object(launcher.sys, 'version_info', (3, 12, 2)), \
                 patch.dict(launcher.os.environ, {'PYTHONPATH': '/old/site', 'PIP_TARGET': '/old/env',
                                                  'R_LIBS': '/unchanged/R/library'}), \
                 patch.object(workflow, 'run_stage', side_effect=stage), \
                 patch.object(launcher.subprocess, 'run', return_value=probe) as prefix_probe, \
                 patch.object(launcher, 'select_python', return_value=(exe, record)) as select, \
                 contextlib.redirect_stdout(io.StringIO()):
                state.prefix_probe, state.select = prefix_probe, select
                yield state

    def test_install_uses_owned_venv_full_requirements_and_pip_check(self):
        with self.fixture() as s:
            self.assertEqual(launcher.setup_python(s.output), s.exe)
            self.assertEqual(len(s.calls), 3)
            self.assertIn('venv', s.calls[0])
            self.assertEqual(s.calls[1][0], str(s.exe))
            self.assertIn('install', s.calls[1])
            self.assertEqual(s.calls[1][-1], str(s.output / 'requirements-supplementary.txt'))
            self.assertEqual(s.calls[2][-2:], ['pip', 'check'])
            s.select.assert_called_once_with(str(s.exe), supplementary=True, isolated=True)
            self.assertTrue((s.output / 'ready.json').is_file())
            self.assertEqual((s.output / 'requirements.txt').read_bytes(), (s.root / 'requirements.txt').read_bytes())

    def test_validated_runtime_is_reused_without_package_commands(self):
        with self.fixture() as s:
            launcher.setup_python(s.output)
            before = (s.output / 'ready.json').read_bytes()
            s.calls.clear()
            launcher.setup_python(s.output)
            launcher.setup_python(s.output, check_only=True)
            self.assertEqual(s.calls, [])
            self.assertEqual((s.output / 'ready.json').read_bytes(), before)

    def test_partial_install_retries_without_marking_ready(self):
        with self.fixture() as s:
            s.fail_install = True
            with self.assertRaisesRegex(RuntimeError, 'interrupted'):
                launcher.setup_python(s.output)
            self.assertTrue((s.output / 'setup.json').is_file())
            self.assertFalse((s.output / 'ready.json').exists())
            s.fail_install = False
            launcher.setup_python(s.output)
            self.assertTrue((s.output / 'ready.json').is_file())

    def test_check_only_missing_runtime_is_read_only(self):
        with self.fixture() as s:
            with self.assertRaisesRegex(ValueError, 'No validated'):
                launcher.setup_python(s.output, check_only=True)
            self.assertFalse(s.output.exists())
            self.assertEqual(s.calls, [])

    def test_check_only_does_not_finish_partial_install(self):
        with self.fixture() as s:
            s.fail_install = True
            with self.assertRaises(RuntimeError):
                launcher.setup_python(s.output)
            s.calls.clear()
            with self.assertRaisesRegex(ValueError, 'No validated'):
                launcher.setup_python(s.output, check_only=True)
            self.assertEqual(s.calls, [])

    def test_unowned_environment_is_untouched(self):
        with self.fixture() as s:
            s.output.mkdir()
            existing = s.output / 'other_environment.txt'
            existing.write_text('keep')
            with self.assertRaisesRegex(ValueError, 'not an owned runtime'):
                launcher.setup_python(s.output)
            self.assertEqual(list(s.output.iterdir()), [existing])
            self.assertEqual(existing.read_text(), 'keep')
            self.assertEqual(s.calls, [])

    def test_setup_cannot_overlap_source(self):
        with self.fixture() as s:
            with self.assertRaisesRegex(ValueError, 'overlaps source'):
                launcher.setup_python(s.root / 'runtime')
            self.assertFalse((s.root / 'runtime').exists())

    def test_wrong_bootstrap_python_stops_before_creation(self):
        with self.fixture() as s, patch.object(launcher.sys, 'version_info', (3, 11, 9)):
            with self.assertRaisesRegex(ValueError, 'Python 3.12'):
                launcher.setup_python(s.output)
            self.assertFalse(s.output.exists())

    def test_nonisolated_python_never_reaches_pip(self):
        with self.fixture() as s:
            s.prefix_probe.return_value.stdout = json.dumps(['/existing/conda', '/existing/conda'])
            with self.assertRaisesRegex(ValueError, 'not isolated'):
                launcher.setup_python(s.output)
            self.assertEqual(len(s.calls), 1)
            self.assertIn('venv', s.calls[0])
            self.assertFalse((s.output / 'ready.json').exists())

    def test_changed_validated_packages_are_not_repaired(self):
        with self.fixture() as s:
            launcher.setup_python(s.output)
            before = (s.output / 'ready.json').read_bytes()
            s.record['supplementary_packages']['scrublet'] = '0.2.4'
            s.calls.clear()
            with self.assertRaisesRegex(ValueError, 'Validated runtime changed'):
                launcher.setup_python(s.output)
            self.assertEqual(s.calls, [])
            self.assertEqual((s.output / 'ready.json').read_bytes(), before)

    def test_changed_requirements_do_not_modify_existing_runtime(self):
        with self.fixture() as s:
            launcher.setup_python(s.output)
            (s.root / 'requirements.txt').write_text('numpy==9.0.0\n')
            s.calls.clear()
            with self.assertRaisesRegex(ValueError, 'requirements changed'):
                launcher.setup_python(s.output)
            self.assertEqual(s.calls, [])

    def test_source_change_during_install_has_no_readiness_receipt(self):
        with self.fixture() as s:
            s.mutate_requirements = True
            with self.assertRaisesRegex(ValueError, 'Source requirements changed during setup'):
                launcher.setup_python(s.output)
            self.assertFalse((s.output / 'ready.json').exists())

    def test_failed_dependency_validation_has_no_readiness_receipt(self):
        with self.fixture() as s:
            s.select.side_effect = RuntimeError('missing openpyxl')
            with self.assertRaisesRegex(RuntimeError, 'missing openpyxl'):
                launcher.setup_python(s.output)
            self.assertFalse((s.output / 'ready.json').exists())

    def test_setup_is_explicit_cli_command(self):
        from adjscope_tx import cli
        with patch.object(launcher, 'setup_python') as setup:
            self.assertEqual(cli.main(['setup-python', '--output', 'runtime', '--check-only']), 0)
        setup.assert_called_once_with(Path('runtime'), check_only=True)


if __name__ == '__main__':
    unittest.main()
