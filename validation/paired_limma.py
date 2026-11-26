"""Compare paired WLS differences with an independent limma contrast (Supplementary Methods S11)."""
import csv
import hashlib
import io
import json
from pathlib import Path
import platform
import shutil
import subprocess

from adjscope_tx.storage import ROOT, sha256

SEED, N, G, TOL = 213, 48, 12, 1e-12
KERNEL_FILES = ("adjscope_tx/diagnostics.py", "pipeline/calibration.py",
                "requirements.txt", "inputs/environment.json")


def fixture():
    import numpy as np

    # Keep the draw order and the 17-digit CSV serialization of the published check.
    rng = np.random.default_rng(SEED)
    target, nuisance = rng.normal(size=N), rng.normal(size=N)
    x0 = np.column_stack((np.ones(N), target, nuisance))
    z = np.column_stack((0.45*target + rng.normal(size=N),
                         0.2*nuisance - 0.3*target + rng.normal(size=N)))
    x1 = np.column_stack((x0, z))
    w = np.exp(rng.normal(0, 0.22, N))
    y = x1 @ rng.normal(size=(5, G)) + rng.normal(size=(N, G)) / np.sqrt(w[:, None])
    genes = [f"gene{i:02d}" for i in range(1, G+1)]
    wire = io.StringIO()
    np.savetxt(wire, np.column_stack((x1, w, y)), fmt="%.17g", delimiter=",", comments="",
               header=",".join(["intercept", "target", "nuisance", "z1", "z2", "weight", *genes]))
    return x0, x1, w, y, genes, wire.getvalue()


def reference(rscript, libraries, wire, genes, locks):
    from numpy import array

    script = Path(__file__).with_suffix(".R")
    try:
        run = subprocess.run([str(rscript), "--vanilla", str(script), *map(str, libraries)],
                             input=wire, capture_output=True, text=True, encoding="utf-8",
                             errors="replace", timeout=120)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("The independent limma check timed out.") from exc
    if run.returncode:
        raise RuntimeError(f"limma exited {run.returncode}: " + (run.stderr + run.stdout).strip()[-1800:])
    lines = run.stdout.splitlines()
    if not lines or not lines[0].startswith("VERSIONS\t"):
        raise ValueError("Missing version record from limma.")
    _, r_version, limma_version = lines[0].split("\t")
    if locks and (r_version, limma_version) != (locks["R"], locks["packages"]["limma"]):
        raise ValueError("The R/limma fit did not use the versions verified by the preflight.")
    reader = csv.DictReader(lines[1:])
    if reader.fieldnames != ["gene", "delta", "se"]:
        raise ValueError("Unexpected limma output columns.")
    rows = list(reader)
    if [v["gene"] for v in rows] != genes:
        raise ValueError("Reference output has missing or misaligned genes.")
    est = array([[float(v["delta"]), float(v["se"])] for v in rows])
    return est, r_version, limma_version


def check(rscript, libraries, locks):
    import numpy as np
    import pandas as pd
    import scipy
    from adjscope_tx.diagnostics import compare_models

    x0, x1, w, y, genes, wire = fixture()
    rows = compare_models(y, x0, x1, weights=w, target=1, variance="model", gene_ids=genes)["genes"]
    if [v["gene_id"] for v in rows] != genes or any(v["status"] != "available" for v in rows):
        raise ValueError("AdjScope-Tx did not return all estimable genes in order.")
    paired = np.array([[v["delta"], v["paired_se"]] for v in rows])
    ref, r, limma = reference(rscript, libraries, wire, genes, locks)
    if not (np.isfinite([paired, ref]).all() and (paired[:, 1] > 0).all() and (ref[:, 1] > 0).all()):
        raise ValueError("Nonfinite estimates or nonpositive standard errors.")
    errors = np.max(np.abs(ref - paired), axis=0)
    passed = bool((errors < TOL).all())
    return {"status": ("PASS_LOCKED" if locks else "SMOKE_PASS_NOT_LOCKED") if passed else "FAIL",
            "locked_environment_checked": bool(locks), "seed": SEED, "samples": N, "genes": G,
            "contrast": "extended minus baseline; shared positive weights; unmoderated model-based SE",
            "absolute_tolerance_strictly_below": TOL, "max_abs_difference_coefficient": float(errors[0]),
            "max_abs_difference_standard_error": float(errors[1]),
            "versions": {"python": platform.python_version(), "numpy": np.__version__, "scipy": scipy.__version__,
                         "pandas": pd.__version__, "R": r, "limma": limma},
            "fixture_sha256": hashlib.sha256(wire.encode("ascii")).hexdigest(),
            "repository_file_sha256": {name: sha256(ROOT/name) for name in KERNEL_FILES}}


def run(args):
    from adjscope_tx.environment import library_candidates, select_r
    from pipeline.environment import python_snapshot

    path = args.output
    if path and path.exists():
        raise FileExistsError("Report already exists: " + str(path))
    exe = args.rscript or shutil.which("Rscript")
    if not exe:
        raise FileNotFoundError("Activate the paper1 environment or supply --rscript.")
    if args.smoke:
        libs, locks = library_candidates(args.r_library), None
    else:
        python_snapshot(ROOT)
        exe, libs, locks = select_r(exe, args.r_library)
    result = check(exe, libs, locks)
    text = json.dumps(result, indent=2, allow_nan=False)
    if path:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8", newline="\n") as f:
            f.write(text + "\n")
    print(text)
    return int(result["status"] == "FAIL")
