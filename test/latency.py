"""Measures how long a picture takes between TouchDesigner and Lanternist, both ways, over
Spout and NDI, on this computer: one side flips a picture between dark and light every half
second and logs when; the other logs when it sees each flip. Both use the system's precise
clock (GetSystemTimePreciseAsFileTime), so the logs line up.

    python integrations/touchdesigner/test/latency.py [--seconds 15]

Lanternist's side is `cargo test -p lanternist-render --test td_latency -- --ignored` (built
first); TouchDesigner's is latency_in_td.py. What a viewer sees adds each program's display
(a frame or two); TouchDesigner looks at what it receives once a frame (up to 17 ms).
"""

import argparse
import os
import pathlib
import socket
import statistics
import subprocess
import sys
import tempfile
import threading
import time

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent.parent.parent
sys.path.insert(0, str(HERE.parent / "build"))
import make  # noqa: E402


def read(path):
    out = []
    if path.exists():
        for line in path.read_text().splitlines():
            t, s = line.split()
            out.append((int(t), int(s)))
    return out


def latencies(sent, seen):
    """For each flip sent, the time to the first sighting of that state after it."""
    found = []
    for i, (t, s) in enumerate(sent):
        until = sent[i + 1][0] if i + 1 < len(sent) else float("inf")
        hit = next((u for u, v in seen if v == s and t <= u < until), None)
        if hit is not None:
            found.append((hit - t) / 1e6)
    return found


def lanternist(mode, log, seconds):
    env = dict(os.environ, LATENCY_MODE=mode, LATENCY_LOG=str(log), LATENCY_SECS=str(seconds),
               CARGO_BUILD_JOBS="8")
    # Without NDI Tools, Lanternist borrows TouchDesigner's NDI runtime for the measurement.
    td_ndi = make.DEFAULT_TD.with_name("Processing.NDI.Lib.x64.dll")
    has_ndi = any(k in env for k in ("LANTERNIST_NDI", "NDI_RUNTIME_DIR_V6", "NDI_RUNTIME_DIR_V5"))
    if not has_ndi and td_ndi.is_file():
        env["LANTERNIST_NDI"] = str(td_ndi)
    return subprocess.Popen(
        ["cargo", "test", "-q", "-p", "lanternist-render", "--test", "td_latency", "--",
         "--ignored", "--nocapture"],
        cwd=REPO, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def case(label, td_mode, lanternist_mode, td_first, seconds, work):
    td_log, ln_log = work / f"{label}-td.log", work / f"{label}-ln.log"
    # NDI receivers name a source `MACHINE (name)`.
    td_target = (f"{socket.gethostname().upper()} ({td_name(label)})" if td_mode == "recv_ndi"
                 else td_name(label))
    for p in (td_log, ln_log):
        if p.exists():
            p.unlink()
    td_thread = threading.Thread(
        target=make.run_in_td,
        args=(make.DEFAULT_TD, HERE / "latency_in_td.py",
              [td_mode, td_log, td_target, seconds + 6], seconds + 60),
        kwargs={"show": 4})
    if td_first:
        td_thread.start()
        time.sleep(6)
        proc = lanternist(lanternist_mode, ln_log, seconds)
    else:
        proc = lanternist(lanternist_mode, ln_log, seconds + 6)
        time.sleep(4)
        td_thread.start()
    proc.wait()
    td_thread.join()
    td, ln = read(td_log), read(ln_log)
    sent, seen = (td, ln) if td_mode.startswith("send") else (ln, td)
    found = latencies(sent, seen)
    if len(found) < 5:
        return f"{label}: not enough flips seen ({len(found)} of {len(sent)} sent)"
    found.sort()
    p95 = found[int(len(found) * 0.95) - 1]
    return (f"{label}: median {statistics.median(found):.1f} ms, p95 {p95:.1f} ms, "
            f"{len(found)} flips")


def td_name(label):
    return f"TD - latency - {label}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=int, default=15)
    args = ap.parse_args()
    subprocess.run(["cargo", "test", "-q", "-p", "lanternist-render", "--test", "td_latency",
                    "--no-run"], cwd=REPO, check=True, env=dict(os.environ, CARGO_BUILD_JOBS="8"))
    work = pathlib.Path(tempfile.mkdtemp(prefix="lanternist-latency-"))
    host = socket.gethostname().upper()
    rows = [
        case("td-to-lanternist-spout", "send_spout", f"recv:spout:{td_name('td-to-lanternist-spout')}",
             True, args.seconds, work),
        case("td-to-lanternist-ndi", "send_ndi",
             f"recv:ndi:{host} ({td_name('td-to-lanternist-ndi')})", True, args.seconds, work),
        case("lanternist-to-td-spout", "recv_spout",
             f"send_spout:{td_name('lanternist-to-td-spout')}", False, args.seconds, work),
        case("lanternist-to-td-ndi", "recv_ndi",
             f"send_ndi:{td_name('lanternist-to-td-ndi')}", False, args.seconds, work),
    ]
    print("\n".join(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
