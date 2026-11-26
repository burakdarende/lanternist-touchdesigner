"""Tests "Lanternist Studio for TouchDesigner" for real: a Lanternist Player plays a project
(its first output shared over Spout) on spare control ports, and TouchDesigner loads the built
component and runs test_in_td.py next to it.

    python integrations/touchdesigner/test/run_tests.py [--player PATH] [--td PATH]

Needs: the component built (build/make.py), a Player build (cargo build -p lanternist-player),
TouchDesigner installed. Exit code 0 when every check passed.
"""

import argparse
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import time
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
TD_DIR = HERE.parent
REPO = TD_DIR.parent.parent
sys.path.insert(0, str(TD_DIR / "build"))
import make  # noqa: E402

OSC, QUERY = 18000, 18001


def test_project(folder: pathlib.Path) -> tuple[pathlib.Path, str]:
    """examples/cues.lanternist with its first output shared over Spout."""
    text = (REPO / "examples" / "cues.lanternist").read_text(encoding="utf-8")
    first = text.index("kind: Output,")
    name = re.search(r'name: "([^"]+)"', text[first:]).group(1)
    at = text.index('"spout": Bool(false)', first)
    text = text[:at] + '"spout": Bool(true)' + text[at + len('"spout": Bool(false)'):]
    path = folder / "td-test.lanternist"
    path.write_text(text, encoding="utf-8", newline="\n")
    return path, f"Lanternist - {name}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--player", type=pathlib.Path,
                    default=REPO / "target" / "debug" / "lanternist-player.exe")
    ap.add_argument("--td", type=pathlib.Path, default=make.DEFAULT_TD)
    args = ap.parse_args()
    tox = TD_DIR / "lanternist_studio.tox"
    for need in (tox, args.player, args.td):
        if not need.is_file():
            print(f"missing: {need}", file=sys.stderr)
            return 1
    work = pathlib.Path(tempfile.mkdtemp(prefix="lanternist-td-test-"))
    project, sender = test_project(work)
    env = dict(os.environ, LOCALAPPDATA=str(work))  # the Player's settings and logs stay here
    player = subprocess.Popen(
        [str(args.player), str(project), "--windowed", "--osc", str(OSC), "--oscquery", str(QUERY)],
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.time() + 60
        while time.time() < deadline:
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{QUERY}/?HOST_INFO", timeout=1).read()
                break
            except OSError:
                time.sleep(0.5)
        else:
            print("the Player's OSCQuery did not answer", file=sys.stderr)
            return 1
        log = work / "td.log"
        text = make.run_in_td(args.td, HERE / "test_in_td.py",
                              [tox, log, OSC, QUERY, sender], timeout=90, show=4)
        engine_log = work / "Lanternist" / "logs" / "player.log"
        lines = (engine_log.read_text(encoding="utf-8", errors="replace").splitlines()
                 if engine_log.exists() else [])
        # The engine logs each cue a GO starts (`... cue cue=/path`; not the opening scene).
        cues = [line for line in lines if " cue " in line and "cue=" in line]
        went = "GO sent" in text and len(cues) >= 1
        text += ("PASS" if went else "FAIL") + f" GO runs Studio's cue list: {len(cues)} cues started\n"
        print(text, end="")
        return 0 if "DONE" in text and "FAIL" not in text else 1
    finally:
        player.kill()
        player.wait()


if __name__ == "__main__":
    sys.exit(main())
