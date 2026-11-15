#!/usr/bin/env bash
# Launch the unified framework with verified downloads from an earlier run.
set -Eeuo pipefail

fail() { printf 'STOP: %s\n' "$*" >&2; exit 2; }
usage() {
    cat <<'HELP'
Usage: bash run_server.sh --raw-cache OLD_RUN [--plan]
       bash run_server.sh --raw-cache OLD_RUN --setup-python [--python-env DIRECTORY]
       bash run_server.sh --resume RUN_DIRECTORY

Defaults: 36 workers, full study, conda environment paper1.
Set --raw-cache (or RAW_CACHE) to a completed run containing core/raw and supplementary/raw.
Optional environment variables: CODE_DIR, RAW_CACHE, OUTPUT, WORKERS, PYTHON, PYTHON_ENV, BASE.
--plan checks paths and prints commands without fitting or downloading.
--resume uses a completed or interrupted run created by this framework.
Verified raw downloads are reused; missing inputs may still be downloaded.
--setup-python explicitly installs Python dependencies into a separate owned environment.
The default runtime location is BASE/p1_python_3_3_0; completed setup is reused read-only.
--setup-python cannot be combined with --plan or --resume. Existing R libraries are unchanged.
No Git operations, deletion, reuse of old fit results, or implicit package installation.
HELP
}

PLAN=0
RESUME=0
SETUP_PYTHON=0
while (($#)); do
    case "$1" in
        --plan) PLAN=1; shift ;;
        --setup-python) SETUP_PYTHON=1; shift ;;
        --python-env)
            (($# >= 2)) && [[ -n "$2" && "$2" != --* ]] || fail '--python-env requires a directory'
            PYTHON_ENV=$2; shift 2 ;;
        --raw-cache)
            (($# >= 2)) || fail '--raw-cache requires an actual download directory'
            RAW_CACHE=$2; shift 2 ;;
        --resume)
            (($# >= 2)) || fail '--resume requires an actual run directory'
            OUTPUT=$2; RESUME=1; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) fail "Unknown argument: $1" ;;
    esac
done
if ((SETUP_PYTHON && (PLAN || RESUME))); then fail '--setup-python cannot be combined with --plan or --resume'; fi

BASE=${BASE:-$HOME/git/repository}
PYTHON_ENV=${PYTHON_ENV:-$BASE/p1_python_3_3_0}
PYTHON_EXPLICIT=${PYTHON:-}
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
WORKERS=${WORKERS:-36}
[[ "$WORKERS" =~ ^[1-9][0-9]*$ ]] || fail 'WORKERS must be a positive integer'

if [[ -n "${CODE_DIR:-}" ]]; then
    CANDIDATES=("$CODE_DIR")
else
    CANDIDATES=("$SCRIPT_DIR" "$BASE/paper1-from-publicV1")
fi
CODE_DIR=
for candidate in "${CANDIDATES[@]}"; do
    if [[ -f "$candidate/run.py" && -f "$candidate/adjscope_tx/cli.py" && -f "$candidate/pipeline/cache.py" ]]; then
        CODE_DIR=$(cd -- "$candidate" && pwd -P)
        break
    fi
done
[[ -n "$CODE_DIR" ]] || fail 'Final framework not found. Set CODE_DIR to the directory containing run.py and adjscope_tx.'

if ((RESUME)); then
    [[ -f "$OUTPUT/workflow.json" ]] || fail "No workflow.json in $OUTPUT. This is not a framework run."
    OUTPUT=$(cd -- "$OUTPUT" && pwd -P)
else
    [[ -n "${RAW_CACHE:-}" ]] || fail 'Set --raw-cache OLD_RUN to reuse verified downloads. Nothing was downloaded.'
    [[ -d "$RAW_CACHE" ]] || fail "Raw cache not found: $RAW_CACHE. Nothing was downloaded."
    RAW_CACHE=$(cd -- "$RAW_CACHE" && pwd -P)
    for component in core supplementary; do
        raw="$RAW_CACHE/$component/raw"
        [[ -d "$raw" ]] || fail "Raw download directory missing: $raw. Nothing was downloaded."
        receipt=$(find "$raw" -type f \( -name '*.download.json' -o -name '*.receipt.json' \) -print -quit)
        [[ -n "$receipt" ]] || fail "No download receipts in $raw. Use the full original run, not a review package."
    done
    OUTPUT=${OUTPUT:-$BASE/p1_final_$(date +%Y%m%d_%H%M%S)_$$}
    [[ ! -e "$OUTPUT" && ! -L "$OUTPUT" ]] || fail "Output already exists: $OUTPUT. Use --resume for a framework run."
fi

if [[ -z "${PYTHON:-}" ]]; then
    if [[ "${CONDA_DEFAULT_ENV:-}" != paper1 ]]; then
        CONDA_SETUP=
        for setup in "$HOME/miniconda3/etc/profile.d/conda.sh" "$HOME/anaconda3/etc/profile.d/conda.sh"; do
            if [[ -f "$setup" ]]; then CONDA_SETUP=$setup; break; fi
        done
        [[ -n "$CONDA_SETUP" ]] || fail 'Activate the existing paper1 environment first, or set PYTHON to its interpreter.'
        source "$CONDA_SETUP"
        conda activate paper1
    fi
    PYTHON=$(command -v python) || fail 'Python not found'
fi
command -v "$PYTHON" >/dev/null || fail "Python not found: $PYTHON"
export PYTHONDONTWRITEBYTECODE=1

MANAGED_PYTHON=0
if ((SETUP_PYTHON)); then
    "$PYTHON" -B "$CODE_DIR/run.py" setup-python --output "$PYTHON_ENV"
    MANAGED_PYTHON=1
elif ((!RESUME && !PLAN)) && [[ -z "$PYTHON_EXPLICIT" && -f "$PYTHON_ENV/ready.json" ]]; then
    "$PYTHON" -B "$CODE_DIR/run.py" setup-python --output "$PYTHON_ENV" --check-only
    MANAGED_PYTHON=1
fi
if ((MANAGED_PYTHON)); then
    PYTHON=$("$PYTHON" -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["executable"])' "$PYTHON_ENV/ready.json")
    [[ -f "$PYTHON" ]] || fail "Validated Python executable is missing: $PYTHON"
    unset PYTHONPATH PYTHONHOME PYTHONUSERBASE
    export PYTHONNOUSERSITE=1
    printf 'ISOLATED PYTHON %s\n' "$PYTHON"
fi

# The framework owns analysis, cache verification, checkpoint recovery and export.
CMD=("$PYTHON" "$CODE_DIR/run.py" run --output "$OUTPUT" --workers "$WORKERS")
if ((MANAGED_PYTHON)); then CMD+=(--python "$PYTHON"); fi
if ((RESUME)); then
    CMD+=(--resume)
else
    CMD+=(--profile full --raw-cache "$RAW_CACHE")
fi
if ((PLAN)); then CMD+=(--plan); fi
printf 'CODE %s\nOUTPUT %s\nWORKERS %s\n' "$CODE_DIR" "$OUTPUT" "$WORKERS"
if ((!RESUME)); then printf 'RAW CACHE %s\n' "$RAW_CACHE"; fi
printf 'NO GIT OPERATIONS; ANALYSIS DOES NOT INSTALL PACKAGES; OLD RESULTS READ ONLY\n'
printf 'RESUME: bash %q --resume %q\n' "$SCRIPT_DIR/$(basename -- "${BASH_SOURCE[0]}")" "$OUTPUT"
cd -- "$CODE_DIR"
if ((PLAN)); then exec "${CMD[@]}"; fi

mkdir -p -- "$(dirname -- "$OUTPUT")"
LOG="$OUTPUT.log"
printf 'LOG %s\n' "$LOG"
if "${CMD[@]}" 2>&1 | tee -a -- "$LOG"; then
    printf 'COMPLETE: %s/results\nFIGURES: %s/figures\n' "$OUTPUT" "$OUTPUT"
else
    status=$?
    printf '\nSTOP: exit %s. No files were deleted. Log: %s\n' "$status" "$LOG" >&2
    exit "$status"
fi
