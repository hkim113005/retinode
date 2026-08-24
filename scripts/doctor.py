#!/usr/bin/env python3
"""Retinode preflight check: what works on this machine, and what is missing.

Run this BEFORE anything else. It uses only the Python standard library, so it
works on a bare Python 3.12 with nothing installed yet:

    python3 scripts/doctor.py

It checks the interpreter, uv and the uv environment, the compiled NEURON
mechanisms, node/npm and the web client, and the conda FEM environment. Every
check prints PASS, FAIL, or SKIP, and a failing check prints the exact command
that fixes it. The summary at the end says which of the three capability tiers
you actually have.

Nothing here installs, syncs, compiles, or writes anything. It is read only, so
it is safe to run at any time.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Kept in step with engine/cable/_neuron.py::_LIB_NAMES. nrnivmodl drops its
# output in a per-architecture directory beside the .mod files, so the arch
# directory name varies (arm64 on Apple Silicon, x86_64 on Intel and Linux).
MECHANISMS_DIR = REPO / "engine" / "cable" / "mechanisms"
LIB_NAMES = ("libnrnmech.dylib", "libnrnmech.so", ".libs/libnrnmech.so")

# Kept in step with api/fem_worker.py::_DEFAULT_FEM_PYTHON.
DEFAULT_FEM_PYTHON = "/opt/homebrew/Caskroom/miniforge/base/envs/retinode-fem/bin/python"

MIN_PYTHON = (3, 12)

# The fast suite needs store and api as well as dev, because pytest imports EVERY
# module under tests/ during collection, before -m deselects anything.
SYNC_CMD = "uv sync --extra dev --extra store --extra api"
FULL_SYNC_CMD = "uv sync --extra cable --extra dev --extra store --extra api"

# Imports are probed in a subprocess, and several of these libraries scribble on
# stdout and stderr while loading (NEURON prints a DISPLAY warning, MPI prints
# "numprocs=1"). Every result line is therefore tagged with this marker and
# tab-delimited, and unmarked output is ignored.
MARKER = "RETINODE_PROBE"

PROBE_SRC = r"""
import importlib, sys
for name in sys.argv[1:]:
    try:
        importlib.import_module(name)
        print("RETINODE_PROBE\t%s\tOK\t" % name, flush=True)
    except BaseException as exc:
        detail = " ".join(str(exc).split())[:160]
        print(
            "RETINODE_PROBE\t%s\tNO\t%s: %s" % (name, type(exc).__name__, detail),
            flush=True,
        )
"""

MACOS_NRNIVMODL_FIX = r"""
On macOS the pip `neuron` wheel bakes its build-time temp path into nrnivmodl,
so the compile above fails with a FileNotFoundError or "No rule to make target
.../wheel/platlib/bin/nrnmech_makefile". `import neuron` still works; only the
compile tooling is broken. Repoint the prefix in the two TEXT build files
(never the .dylib/.a binaries), then compile with the real binary:

  DATA="$PWD/.venv/lib/python3.12/site-packages/neuron/.data"
  TMP=$(grep -oE '/var/folders/[^"'"'"' ]*/wheel/platlib' "$DATA/bin/nrnivmodl" | head -1)
  perl -pi -e "s|\Q$TMP\E|$DATA|g" "$DATA/bin/nrnivmodl" "$DATA/include/nrnconf.h"
  (cd engine/cable/mechanisms && uv run --extra cable "$DATA/bin/nrnivmodl" .)

This patches .venv/, which is not version controlled, so a `uv sync` that
reinstalls neuron undoes it and you run the patch again.
"""


class Doctor:
    """Collects check results and prints them as it goes."""

    def __init__(self) -> None:
        self.counts = {"PASS": 0, "FAIL": 0, "SKIP": 0}

    def report(self, status, title, details=(), fix=None):
        self.counts[status] += 1
        print(f"[{status}] {title}")
        for detail in details:
            print(f"       {detail}")
        if fix:
            print("       fix:")
            for fix_line in fix.strip("\n").splitlines():
                # Blank separator lines inside a multi-line fix stay blank rather
                # than becoming a line of trailing spaces.
                print("         " + fix_line if fix_line.strip() else "")
        if details or fix:
            print()
        return status == "PASS"


def section(title):
    print()
    print(title)
    print("-" * len(title))


def venv_python(root):
    """Path to the uv environment's interpreter, whether or not it exists."""
    if os.name == "nt":
        return root / ".venv" / "Scripts" / "python.exe"
    return root / ".venv" / "bin" / "python"


def _probe_one(python, name, timeout):
    """Import a single module in a fresh interpreter. Returns (ok, detail)."""
    try:
        proc = subprocess.run(
            [str(python), "-c", PROBE_SRC, name],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return False, f"timed out after {timeout}s"
    except OSError as exc:
        reason = getattr(exc, "strerror", None) or str(exc)
        return False, f"could not run {python} ({reason})"

    for line in (proc.stdout or "").splitlines():
        if not line.startswith(MARKER):
            continue
        parts = line.split("\t")
        if len(parts) >= 4 and parts[1] == name:
            return parts[2] == "OK", parts[3]

    # The probe never reported, so the interpreter died before it could print
    # (a segfault in a native extension, for example). Say so with its stderr.
    tail = " / ".join((proc.stderr or "").strip().splitlines()[-2:])
    return False, tail or f"the interpreter exited with code {proc.returncode}"


def probe_imports(python, modules, timeout=120):
    """Import each module in `python`. Returns {name: (ok, detail)}.

    Each module gets its OWN fresh interpreter, deliberately. Importing them all
    in one process is faster, but these libraries have side effects on each
    other: NEURON in particular has been seen to fail to import in a process
    that already loaded another heavy native extension, which would make the
    doctor report a missing dependency that is in fact installed. A false FAIL
    here is worse than a slow check, so isolation wins.

    A failure is retried once for the same reason: the failure mode above is
    intermittent, and only failures pay the retry cost.

    Never raises: a missing interpreter, a crash, or a hang all come back as
    failures with a readable reason instead of a traceback.
    """
    results = {}
    for name in modules:
        ok, detail = _probe_one(python, name, timeout)
        if not ok:
            ok, detail = _probe_one(python, name, timeout)
        results[name] = (ok, detail)
    return results


def compiled_library():
    """The compiled mechanism library, or None if nrnivmodl has not run yet."""
    if not MECHANISMS_DIR.is_dir():
        return None
    for arch in sorted(MECHANISMS_DIR.iterdir()):
        if not arch.is_dir():
            continue
        for name in LIB_NAMES:
            lib = arch / name
            if lib.exists():
                return lib
    return None


def run_version(executable, args=("--version",)):
    """First line of `executable --version`, or None if it cannot be run."""
    try:
        proc = subprocess.run(
            [executable, *args], capture_output=True, text=True, timeout=30
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    out = (proc.stdout or proc.stderr or "").strip().splitlines()
    return out[0] if out else ""


def python_version_of(python):
    """(major, minor, micro) of an interpreter, or None if it cannot be run.

    Asks the interpreter itself rather than parsing `--version`, so a banner or a
    warning on stderr cannot be mistaken for a version.
    """
    if not Path(python).exists():
        return None
    try:
        proc = subprocess.run(
            [str(python), "-c", "import sys; print('%s.%s.%s' % sys.version_info[:3])"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    for line in (proc.stdout or "").splitlines():
        parts = line.strip().split(".")
        if len(parts) == 3 and all(p.isdigit() for p in parts):
            return tuple(int(p) for p in parts)
    return None


def rel(path):
    """Path relative to the repo root when it is inside it, else absolute."""
    try:
        return str(Path(path).relative_to(REPO))
    except ValueError:
        return str(path)


def main():
    if "--help" in sys.argv or "-h" in sys.argv:
        print(__doc__)
        return 0

    doc = Doctor()
    print("Retinode doctor")
    print(f"repo:     {REPO}")
    machine = os.uname().machine if hasattr(os, "uname") else ""
    print(f"platform: {sys.platform} {machine}")
    print(f"running:  {sys.executable}")

    # ------------------------------------------------------------------
    section("1. Python")
    # ------------------------------------------------------------------
    # Two interpreters matter and they are often different. The one running this
    # script is incidental (it only has to be new enough to parse the file). The
    # one that runs the project is .venv/bin/python, and that is the one that has
    # to be 3.12. On a machine with conda on PATH, a bare `python3` is very often
    # an old conda base, which is exactly the trap that makes a bare `pytest`
    # fail on datetime.UTC.
    version = ".".join(str(n) for n in sys.version_info[:3])
    venv_ver = python_version_of(venv_python(REPO))
    venv_str = ".".join(str(n) for n in venv_ver) if venv_ver else None

    if venv_ver and venv_ver >= MIN_PYTHON:
        details = [f"This script is running under {version} ({sys.executable})."]
        if sys.version_info < MIN_PYTHON:
            details += [
                "That interpreter is older than 3.12, which is harmless here because",
                "the project runs out of .venv. It does mean a bare `python` or",
                "`pytest` on this PATH is NOT the project's interpreter, so always",
                'run tests as `uv run python -m pytest`, never as bare `pytest`.',
            ]
        doc.report("PASS", f"Python {venv_str} in .venv (>= 3.12 required)", details)
    elif venv_ver:
        doc.report(
            "FAIL",
            f"Python {venv_str} in .venv is too old, 3.12 or newer is required",
            ["The engine uses datetime.UTC and other 3.11+ APIs."],
            "uv python install 3.12\nuv venv --python 3.12\n" + FULL_SYNC_CMD,
        )
    elif sys.version_info >= MIN_PYTHON:
        doc.report(
            "PASS",
            f"Python {version} (>= 3.12 required)",
            ["No .venv yet, so this is the interpreter that was checked."],
        )
    else:
        doc.report(
            "FAIL",
            f"Python {version} is too old, 3.12 or newer is required",
            [
                "There is no .venv yet either, so nothing on this machine is known",
                "to satisfy the 3.12 floor. uv can install one.",
            ],
            "uv python install 3.12\n" + FULL_SYNC_CMD,
        )

    # ------------------------------------------------------------------
    section("2. uv")
    # ------------------------------------------------------------------
    uv_path = shutil.which("uv")
    if uv_path:
        uv_ver = run_version("uv") or "version unknown"
        doc.report("PASS", f"uv found: {uv_path} ({uv_ver})")
    else:
        doc.report(
            "FAIL",
            "uv not found on PATH",
            ["uv creates and manages the .venv that everything below needs."],
            "curl -LsSf https://astral.sh/uv/install.sh | sh\n"
            "# or:  brew install uv",
        )

    # ------------------------------------------------------------------
    section("3. uv environment (.venv)")
    # ------------------------------------------------------------------
    vpy = venv_python(REPO)
    sync_cmd = SYNC_CMD

    core = {}
    if not vpy.exists():
        doc.report(
            "FAIL",
            f"no uv environment at {rel(vpy.parent.parent)}",
            ["Nothing below can be checked until the environment exists."],
            sync_cmd,
        )
        doc.report("SKIP", "importable packages (no environment to probe)")
    elif venv_ver is None:
        doc.report(
            "FAIL",
            f"{rel(vpy)} exists but could not be run",
            ["The environment looks broken or half written. Recreating it is quickest."],
            "rm -rf .venv\n" + FULL_SYNC_CMD,
        )
        doc.report("SKIP", "importable packages (the interpreter does not run)")
    else:
        probed = probe_imports(
            vpy,
            ["engine", "numpy", "scipy", "fastapi", "pyarrow", "h5py", "pytest", "neuron"],
        )
        core = probed
        env_version = "Python " + ".".join(str(n) for n in venv_ver)
        if probed["engine"][0]:
            doc.report("PASS", f"uv environment synced: {rel(vpy)} ({env_version})")
        else:
            doc.report(
                "FAIL",
                "uv environment exists but `import engine` fails",
                ["{}".format(probed["engine"][1])],
                sync_cmd,
            )

        groups = [
            ("engine core", ["numpy", "scipy"], sync_cmd),
            ("api extra", ["fastapi"], "uv sync --extra api"),
            ("store extra", ["pyarrow", "h5py"], "uv sync --extra store"),
            ("dev extra", ["pytest"], "uv sync --extra dev"),
            ("cable extra", ["neuron"], "uv sync --extra cable"),
        ]
        for label, mods, fix in groups:
            missing = [m for m in mods if not probed[m][0]]
            if not missing:
                doc.report("PASS", "{}: {}".format(label, ", ".join(mods)))
            else:
                reasons = [f"{m}: {probed[m][1]}" for m in missing]
                doc.report("FAIL", "{}: {} missing".format(label, ", ".join(missing)), reasons, fix)

        if not (probed["pytest"][0] and probed["fastapi"][0] and probed["pyarrow"][0]):
            doc.report(
                "SKIP",
                "fast test suite needs dev + store + api together",
                [
                    "pytest imports EVERY module under tests/ during collection, before",
                    "-m deselects anything, so tests/api and tests/store must import even",
                    "for the fast suite. dev alone is not enough.",
                ],
                sync_cmd + '\nuv run python -m pytest -m "not slow and not neuron and not fem"',
            )

    # ------------------------------------------------------------------
    section("4. NEURON mechanisms")
    # ------------------------------------------------------------------
    neuron_ok = bool(core) and core.get("neuron", (False, ""))[0]
    lib = compiled_library()
    compile_cmd = "uv sync --extra cable\n(cd engine/cable/mechanisms && uv run nrnivmodl .)"

    if not MECHANISMS_DIR.is_dir():
        doc.report(
            "FAIL",
            f"mechanisms directory missing: {rel(MECHANISMS_DIR)}",
            ["This should be checked in. The working tree looks incomplete."],
            "git status\ngit checkout -- engine/cable/mechanisms",
        )
    elif lib is not None:
        mod_files = ", ".join(sorted(p.name for p in MECHANISMS_DIR.glob("*.mod")))
        doc.report(
            "PASS",
            f"mechanisms compiled: {rel(lib)}",
            [f"Built from {mod_files}"],
        )
    else:
        found = sorted(p.name for p in MECHANISMS_DIR.iterdir() if p.is_dir())
        details = [
            f"Looked for {' or '.join(LIB_NAMES)} in every arch directory"
            f" under {rel(MECHANISMS_DIR)}.",
            f"Arch directories present: {', '.join(found) if found else 'none'}",
            "Without this, every NEURON threshold search fails.",
        ]
        fix = compile_cmd
        if sys.platform == "darwin":
            fix = compile_cmd + "\n" + MACOS_NRNIVMODL_FIX
        doc.report("FAIL", "mechanisms NOT compiled", details, fix)

    if bool(core) and not neuron_ok:
        doc.report(
            "SKIP",
            "neuron not importable in .venv, so mechanisms cannot be compiled yet",
            [core.get("neuron", (False, ""))[1]],
            "uv sync --extra cable",
        )

    # ------------------------------------------------------------------
    section("5. Web client (node + npm)")
    # ------------------------------------------------------------------
    node_path = shutil.which("node")
    npm_path = shutil.which("npm")
    if node_path:
        doc.report("PASS", "node found: {} ({})".format(node_path, run_version("node") or "?"))
    else:
        doc.report(
            "FAIL",
            "node not found on PATH",
            ["Only the React client needs it. The engine and API do not."],
            "brew install node\n# or see https://nodejs.org/",
        )
    if npm_path:
        doc.report("PASS", "npm found: {} ({})".format(npm_path, run_version("npm") or "?"))
    else:
        doc.report(
            "FAIL", "npm not found on PATH", [], "brew install node\n# npm ships with node"
        )

    node_modules = REPO / "app" / "web" / "node_modules"
    if node_modules.is_dir():
        doc.report("PASS", f"web dependencies installed: {rel(node_modules)}")
    elif npm_path:
        doc.report(
            "FAIL",
            f"web dependencies not installed ({rel(node_modules)} missing)",
            ["The dev client proxies /api to port 8000, so start the API first."],
            "npm --prefix app/web install\nnpm --prefix app/web run dev",
        )
    else:
        doc.report("SKIP", "web dependencies (npm not available to install them)")

    # ------------------------------------------------------------------
    section("6. Conda FEM environment")
    # ------------------------------------------------------------------
    fem_env = os.environ.get("RETINODE_FEM_PYTHON")
    fem_python = fem_env or DEFAULT_FEM_PYTHON
    source = (
        "$RETINODE_FEM_PYTHON"
        if fem_env
        else "the default miniforge path (unset $RETINODE_FEM_PYTHON)"
    )
    create_cmd = (
        "conda env create -f env/fem-environment.yml\n"
        "conda activate retinode-fem\n"
        "pip install -e . --no-deps    # so `import engine` works; conda supplies the deps"
    )
    point_cmd = "export RETINODE_FEM_PYTHON=/path/to/envs/retinode-fem/bin/python"

    fem_mods = {}
    fem_interpreter_ok = False
    fem_exists = Path(fem_python).exists()
    fem_ver = python_version_of(fem_python) if fem_exists else None
    if not fem_exists:
        details = [
            f"Looked at: {fem_python}",
            f"Source: {source}",
            "Everything 3D or FEM is unavailable, including the headline reproduction.",
            "The analytical tier is unaffected, and the app says so plainly when a",
            "request needs FEM.",
        ]
        fix = create_cmd if not fem_env else point_cmd + "\n# or create it:\n" + create_cmd
        doc.report("FAIL", "FEM interpreter not found", details, fix)
        doc.report("SKIP", "dolfinx / gmsh / neuron (no FEM interpreter to probe)")
    elif fem_ver is None:
        # The path is there but it is not a working interpreter, so probing it for
        # dolfinx would just repeat the same error four times under four
        # misleading conda fixes. Say the real thing once.
        doc.report(
            "FAIL",
            f"FEM interpreter at {fem_python} exists but could not be run",
            [
                f"Source: {source}",
                "It is not a working Python interpreter.",
            ],
            point_cmd + "\n# or create it:\n" + create_cmd,
        )
        doc.report("SKIP", "dolfinx / gmsh / neuron (the interpreter does not run)")
    else:
        fem_mods = probe_imports(fem_python, ["dolfinx", "gmsh", "neuron", "engine"])
        fem_interpreter_ok = True
        doc.report(
            "PASS",
            f"FEM interpreter found: {fem_python}",
            [
                f"Source: {source}",
                "Python {}".format(".".join(str(n) for n in fem_ver)),
            ],
        )

        for name, why in (
            ("dolfinx", "the FEM solver itself"),
            ("gmsh", "the mesh front end"),
            ("neuron", "so one env can drive cells from the FEM field"),
        ):
            ok, detail = fem_mods[name]
            if ok:
                doc.report("PASS", f"FEM env: {name} imports ({why})")
            else:
                doc.report(
                    "FAIL",
                    f"FEM env: {name} does NOT import ({why})",
                    [detail],
                    create_cmd,
                )

        ok, detail = fem_mods["engine"]
        if ok:
            doc.report("PASS", "FEM env: engine imports (installed editable)")
        else:
            doc.report(
                "FAIL",
                "FEM env: engine does NOT import",
                [detail, "The headline reproduction runs in this env and imports engine."],
                "conda activate retinode-fem\npip install -e . --no-deps",
            )

    # ------------------------------------------------------------------
    # Capability tiers
    # ------------------------------------------------------------------
    def got(mapping, name):
        return bool(mapping) and mapping.get(name, (False, ""))[0]

    engine_core_ok = got(core, "numpy") and got(core, "scipy") and got(core, "engine")
    fast_tests_ok = got(core, "pytest") and got(core, "fastapi") and got(core, "pyarrow") and got(
        core, "h5py"
    )
    tier2_ok = engine_core_ok and got(core, "neuron") and compiled_library() is not None
    tier3_ok = (
        fem_interpreter_ok
        and got(fem_mods, "dolfinx")
        and got(fem_mods, "gmsh")
        and got(fem_mods, "neuron")
        and got(fem_mods, "engine")
    )

    section("Capability tiers")
    if engine_core_ok and fast_tests_ok:
        tier1 = "AVAILABLE"
        tier1_note = ['uv run python -m pytest -m "not slow and not neuron and not fem"']
    elif engine_core_ok:
        tier1 = "PARTIAL"
        missing = [m for m in ("pytest", "fastapi", "pyarrow", "h5py") if not got(core, m)]
        tier1_note = [
            "The engine runs, so the tool is usable.",
            "The fast suite needs: {}".format(", ".join(missing)),
            f"Fix: {sync_cmd}",
        ]
    else:
        tier1 = "UNAVAILABLE"
        tier1_note = [f"Fix: {sync_cmd}"]

    print(f"Tier 1  analytical engine + fast tests ......... {tier1}")
    for note in tier1_note:
        print(f"        {note}")
    print()

    print("Tier 2  NEURON thresholds ...................... "
          + ("AVAILABLE" if tier2_ok else "UNAVAILABLE"))
    if tier2_ok:
        print("        uv run python -m pytest -m neuron")
    else:
        if not got(core, "neuron"):
            print("        neuron is not importable in .venv. Fix: uv sync --extra cable")
        if compiled_library() is None:
            print("        mechanisms are not compiled. See check 4 above for the exact fix.")
    print()

    print("Tier 3  FEM, 3D, headline reproduction ......... "
          + ("AVAILABLE" if tier3_ok else "UNAVAILABLE"))
    if tier3_ok:
        print("        $RETINODE_FEM_PYTHON examples/reproduce_headline.py")
        print(f"        (or: {fem_python} examples/reproduce_headline.py)")
    else:
        print("        Needs the conda retinode-fem env. See check 6 above.")
        print("        Everything analytical still works without it.")
    print()

    print(
        f'{doc.counts["PASS"]} passed, {doc.counts["FAIL"]} failed, '
        f'{doc.counts["SKIP"]} skipped.'
    )

    if tier1 == "UNAVAILABLE":
        print("Tier 1 is broken, so the tool will not run. Start with the fixes above.")
        return 1
    print("Tier 1 works, so the tool is usable.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\ninterrupted")
        sys.exit(130)
