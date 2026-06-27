"""Tests for the opt-in PATH launcher (kdbx install-launcher — issue #10)."""

import importlib
import os
import stat
import subprocess

import pytest

launcher = importlib.import_module("kdbx_core.launcher")
ops = importlib.import_module("kdbx_core.ops")

# The launcher is a POSIX `sh` shim (chmod 0755, runs via `sh`). A Windows `.cmd`
# launcher is a follow-up (#1), so this whole module is POSIX-only.
pytestmark = pytest.mark.skipif(
    os.name == "nt", reason="launcher is a POSIX sh shim; Windows .cmd is a follow-up (#1)"
)


def _is_exec(p):
    return bool(p.stat().st_mode & stat.S_IXUSR)


def test_install_writes_executable_shim(tmp_path):
    dest = launcher.install(tmp_path)
    assert dest == tmp_path / "kdbx"
    assert _is_exec(dest)
    body = dest.read_text()
    assert launcher.MARKER in body
    assert "exec uv run --locked" in body


def test_overwrites_its_own_managed_shim(tmp_path):
    launcher.install(tmp_path)
    # second call without --force is fine: the existing file is ours (has the marker)
    launcher.install(tmp_path)
    assert (tmp_path / "kdbx").read_text().count(launcher.MARKER) == 1


def test_refuses_foreign_file_without_force(tmp_path):
    foreign = tmp_path / "kdbx"
    foreign.write_text("#!/bin/sh\necho not ours\n")
    with pytest.raises(FileExistsError):
        launcher.install(tmp_path)
    # --force overwrites
    launcher.install(tmp_path, force=True)
    assert launcher.MARKER in foreign.read_text()


def test_dispatch_refusal_exits_4(tmp_path, capsys):
    (tmp_path / "kdbx").write_text("foreign")
    rc = ops.dispatch(["install-launcher", "--dir", str(tmp_path)])
    assert rc == 4
    assert "--force" in capsys.readouterr().err


def test_dispatch_success(tmp_path):
    rc = ops.dispatch(["install-launcher", "--dir", str(tmp_path)])
    assert rc == 0
    assert _is_exec(tmp_path / "kdbx")


# --- functional: run the generated shim with a fake $HOME + stub `uv` ---------


def _stub_uv(bindir):
    """A fake `uv` on PATH that echoes its argv so we can assert what the shim ran."""
    uv = bindir / "uv"
    uv.write_text('#!/bin/sh\necho "UV $@"\n')
    uv.chmod(0o755)


def _run_shim(shim, home, bindir, *args):
    env = dict(os.environ, HOME=str(home), PATH=f"{bindir}{os.pathsep}{os.environ['PATH']}")
    return subprocess.run(["sh", str(shim), *args], capture_output=True, text=True, env=env)


def _mk_install(d, version):
    """A stub kdbx install: kdbx.py + a sibling kdbx_core/__init__.py with `version`
    (the shim reads the version from there to pick the newest across channels)."""
    d.mkdir(parents=True, exist_ok=True)
    (d / "kdbx.py").write_text("# stub")
    core = d / "kdbx_core"
    core.mkdir(exist_ok=True)
    (core / "__init__.py").write_text(f'__version__ = "{version}"\n')
    return d / "kdbx.py"


def _standalone(home):
    return home / ".claude" / "skills" / "kdbx"


def _cache(home, version):
    return (
        home
        / ".claude"
        / "plugins"
        / "cache"
        / "yarrasys-skills"
        / "kdbx"
        / version
        / "skills"
        / "kdbx"
    )


def test_shim_uses_the_only_install(tmp_path):
    home = tmp_path / "home"
    py = _mk_install(_standalone(home), "0.2.0")
    bindir = tmp_path / "bin"
    bindir.mkdir()
    _stub_uv(bindir)
    shim = launcher.install(tmp_path / "shimdir")

    p = _run_shim(shim, home, bindir, "check")
    assert p.returncode == 0
    assert f"UV run --locked {py} check" in p.stdout


def test_shim_picks_newest_plugin_cache(tmp_path):
    home = tmp_path / "home"
    _mk_install(_cache(home, "0.1.0"), "0.1.0")
    newest = _mk_install(_cache(home, "0.2.0"), "0.2.0")
    bindir = tmp_path / "bin"
    bindir.mkdir()
    _stub_uv(bindir)
    shim = launcher.install(tmp_path / "shimdir")

    p = _run_shim(shim, home, bindir, "envs")
    assert p.returncode == 0
    assert str(newest) in p.stdout


def test_shim_resolves_newest_across_channels(tmp_path):
    # #14: standalone is STALE (0.1.0), plugin-cache is newer (0.2.0) — the cache copy
    # must win so a `/plugin update` is never silently shadowed by the old standalone.
    home = tmp_path / "home"
    _mk_install(_standalone(home), "0.1.0")
    newest = _mk_install(_cache(home, "0.2.0"), "0.2.0")
    bindir = tmp_path / "bin"
    bindir.mkdir()
    _stub_uv(bindir)
    shim = launcher.install(tmp_path / "shimdir")

    p = _run_shim(shim, home, bindir, "run")
    assert p.returncode == 0
    assert str(newest) in p.stdout
    assert f"{_standalone(home) / 'kdbx.py'} run" not in p.stdout  # stale standalone NOT used


def test_shim_errors_helpfully_when_missing(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    bindir = tmp_path / "bin"
    bindir.mkdir()
    _stub_uv(bindir)
    shim = launcher.install(tmp_path / "shimdir")

    p = _run_shim(shim, home, bindir, "check")
    assert p.returncode == 127
    assert "could not locate kdbx.py" in p.stderr
