"""Bind the stock builder's actual external project inputs to the pre-outcome declaration."""
from contextlib import contextmanager
import os
from pathlib import Path
import re
import shlex
import shutil
from tempfile import TemporaryDirectory

from .outcome_rollouts import ROOT, check, equal, file_record

GENERATED = {"AI/jkBotLily.inc", "stock_functions.inc"}
OBJECTS = {"replay.o", "rdMatrix.o", "rdMath.o", "rdVector.o", "stdMath.o", "sithSector.o"}


def declared(decl):
    expected = decl["project_build_inputs_sha256"]
    check(isinstance(expected, dict) and expected, "missing external project inputs")
    for name, digest in expected.items():
        path = Path(name)
        check(path.as_posix() == name and len(path.parts) >= 2 and path.parts[0] in ("source","configured")
              and ".." not in path.parts and re.fullmatch(r"[0-9a-f]{64}", digest), "invalid project input")
    for name, digest in decl["fixture_reference"]["source_hashes"].items():
        equal(expected.get("source/"+name), digest, "historical project source "+name)
    return expected


def retain(expected, work, source, build):
    roots = {"source":source, "configured":build}
    for name, digest in expected.items():
        scope, relative = name.split("/",1)
        original = roots[scope]/relative
        check(original.resolve() == original, "indirect external project input "+name)
        target = work/name
        target.parent.mkdir(exist_ok=True, parents=True)
        shutil.copyfile(original, target)
        equal(file_record(target)["sha256"], digest, "changed external project input "+name)


@contextmanager
def compiler_dependencies():
    """GCC emits non-system prerequisites for each real translation unit during the one build."""
    # The pinned builder inherits its environment. Set this before dispatching any
    # workers and restore it even on compiler failure. System include overrides
    # could otherwise make project headers invisible to GCC's dependency output.
    keys = ("DEPENDENCIES_OUTPUT","SUNPRO_DEPENDENCIES","CPATH","C_INCLUDE_PATH")
    original = {key:os.environ[key] for key in keys if key in os.environ}
    with TemporaryDirectory(prefix="lily-outcome-deps-") as tmp:
        path = Path(tmp)/"dependencies.mk"
        try:
            for key in keys:
                os.environ.pop(key, None)
            os.environ["DEPENDENCIES_OUTPUT"] = str(path)
            yield path
        finally:
            for key in keys:
                os.environ.pop(key, None)
            os.environ.update(original)


def verify_compilation(depfile, work, build, decl):
    expected = declared(decl)
    legacy = decl["fixture_reference"]["source_hashes"]
    project = {"source/"+name for name in legacy}
    targets = []
    generated = set()
    for line in depfile.read_text().replace("\\\n", " ").splitlines():
        target, dependencies = line.split(": ", 1)
        targets.append(target)
        for token in shlex.split(dependencies):
            path = Path(token).resolve(strict=True)
            if path.is_relative_to(work/"source"):
                name = path.relative_to(work).as_posix()
            elif path.is_relative_to(build):
                name = "configured/"+path.relative_to(build).as_posix()
            elif path.is_relative_to(work):
                generated.add(path.relative_to(work).as_posix())
                continue
            elif path.is_relative_to(ROOT):
                name = path.relative_to(ROOT).as_posix()
                equal(file_record(path)["sha256"], decl["fixture_reference"]["fixture_source_sha256"].get(name),
                      "unbound fixture compile input "+name)
                continue
            else:
                raise ValueError(f"unbound external compile input {path}")
            equal(file_record(path)["sha256"], expected.get(name), "unbound external project input "+name)
            project.add(name)
    check(len(targets) == len(OBJECTS) and set(targets) == OBJECTS, "incomplete compiler dependency output")
    check(generated == GENERATED, "generated compile inputs")
    check(project == set(expected), "declared project/actual compiler dependencies")
