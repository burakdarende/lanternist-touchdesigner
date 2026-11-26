"""Builds "Lanternist Studio for TouchDesigner" (lanternist_studio.tox) from the text sources.

    python integrations/touchdesigner/build/make.py [--td PATH_TO_TouchDesigner.exe]

TouchDesigner saves components in its own format, so the build runs inside TouchDesigner:
this script writes a tiny start project as text (nothing of Derivative's in it), turns it into
a .toe with TouchDesigner's own `toecollapse`, and opens it minimised; its start script runs
`build_tox.py`, which assembles the component from `src/` with TouchDesigner's Python API,
saves `lanternist_studio.tox` and closes TouchDesigner. Any TouchDesigner licence works,
Non-Commercial included. `run_in_td` runs the tests the same way (test/run_tests.py).
"""

import argparse
import pathlib
import shutil
import struct
import subprocess
import sys
import tempfile
import time

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
DEFAULT_TD = pathlib.Path(r"C:\Program Files\Derivative\TouchDesigner\bin\TouchDesigner.exe")


def dat_text(text: str) -> bytes:
    """A DAT's text as TouchDesigner's expanded format keeps it."""
    body = text.encode("utf-8")
    return b"2\n*" + struct.pack(">6I", 1, 1, 1, 1, 2, len(body)) + body


def boot_project(folder: pathlib.Path, script: pathlib.Path, args: list) -> None:
    """The start project, expanded, in `folder`: it runs `script` with `args` (`args[1]`: the
    log, where an error goes) and ends TouchDesigner if the script fails."""
    d = folder / "boot.toe.dir"
    (d / "project1").mkdir(parents=True)
    (d / "local").mkdir()
    files = {
        ".build": "version 099\nbuild 2023.12120\ntime Thu Nov 26 00:00:00 2026\n"
                  "osname Windows\nosversion 10\n",
        ".start": "cookrate 60\nrealtime on\nviewers off\n",
        ".grps": "-2\n0\n",
        ".root": "v 0 0 1\nend\n",
        ".parm": "?\n?\n",
        "project1.n": "COMP:container\ntile 0 0 160 130\nflags =  viewer 1\nend\n",
        "project1.parm": "?\n?\n",
        "project1/boot.n": "DAT:execute\ntile 0 0 130 90\nflags =  viewer 1\nend\n",
        "project1/boot.parm": "?\nstart 0 on\nlanguage 0 python\n?\n",
        # A timeline, so frames run (for scripts that wait for frames: the tests).
        "local.n": "COMP:container\ntile 0 200 160 130\nflags =  viewer 1\nend\n",
        "local.parm": "?\n?\n",
        "local/time.n": "COMP:time\ntile 0 0 160 130\nflags = \nend\n",
        "local/time.parm": "?\nrate 17 60 $COOKRATE\nindependent 0 on\n?\n",
    }
    for name, text in files.items():
        (d / name).write_text(text, encoding="utf-8", newline="\n")
    argv = [script.name] + [str(a) for a in args]
    log = str(args[1])
    script_text = (
        "def onStart():\n"
        "\timport os, runpy, sys, traceback\n"
        f"\tsys.argv = {argv!r}\n"
        "\ttry:\n"
        f"\t\trunpy.run_path({str(script)!r}, init_globals=globals(), run_name='__main__')\n"
        "\texcept Exception:\n"
        f"\t\topen({log!r}, 'a').write(traceback.format_exc())\n"
        "\t\tos._exit(1)\n"
    )
    (d / "project1" / "boot.text").write_bytes(dat_text(script_text))
    (folder / "boot.toe.toc").write_text("\n".join(files) + "\nproject1/boot.text\n",
                                         encoding="utf-8", newline="\n")


def run_in_td(td: pathlib.Path, script: pathlib.Path, args: list, timeout: float,
              show: int = 7) -> str:
    """Opens TouchDesigner (minimised) on a start project that runs `script` with `args`
    (`args[1]` is the log); returns the log's text once TouchDesigner has closed."""
    collapse = td.with_name("toecollapse.exe")
    if not td.is_file() or not collapse.is_file():
        raise FileNotFoundError(f"TouchDesigner not found at {td}")
    work = pathlib.Path(tempfile.mkdtemp(prefix="lanternist-td-"))
    log = pathlib.Path(args[1])
    try:
        boot_project(work, script, args)
        subprocess.run([str(collapse), "boot.toe.toc"], cwd=work, check=True,
                       stdout=subprocess.DEVNULL)
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = show
        proc = subprocess.Popen([str(td), str(work / "boot.toe")], cwd=work,
                                startupinfo=startup)
        deadline = time.time() + timeout
        while proc.poll() is None and time.time() < deadline:
            time.sleep(0.5)
        if proc.poll() is None:
            proc.kill()
            proc.wait()
            with open(log, "a", encoding="utf-8") as f:
                f.write("TouchDesigner did not finish in time\n")
        return log.read_text(encoding="utf-8", errors="replace") if log.exists() else ""
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--td", type=pathlib.Path, default=DEFAULT_TD)
    ap.add_argument("--out", type=pathlib.Path, default=ROOT / "lanternist_studio.tox")
    ap.add_argument("--timeout", type=float, default=120.0)
    args = ap.parse_args()
    out = args.out.resolve()
    if out.exists():
        out.unlink()
    logdir = pathlib.Path(tempfile.mkdtemp(prefix="lanternist-td-log-"))
    try:
        print(run_in_td(args.td, HERE / "build_tox.py", [out, logdir / "build.log"],
                        args.timeout), end="")
    finally:
        shutil.rmtree(logdir, ignore_errors=True)
    if not out.exists():
        print("no component was saved", file=sys.stderr)
        return 1
    print(f"built {out} ({out.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
