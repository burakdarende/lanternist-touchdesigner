"""Lanternist Studio for TouchDesigner: the component's logic.

MIT licence, (c) Lanternist. Built-in OPs and Python's standard library only, so it runs on
every TouchDesigner licence, Non-Commercial included.

- Finds Lanternist Studio (this computer first, then the local network over mDNS, the
  `_oscjson._tcp` service Studio announces), or the address typed in.
- Reads Studio's parameters from its OSCQuery tree and shows them on the "Studio parameters"
  page: a change in TouchDesigner goes to Studio over OSC, a change in Studio comes back over
  OSCQuery LISTEN (a WebSocket).
- GO, BACK and "go to cue" over OSC.
- Sends up to four TOPs to Studio over Spout (this computer: full size, no delay) or NDI (the
  network), and receives a Studio output back. If Spout cannot send (a licence without it),
  the TOPs go over NDI by themselves and the status says why.
"""

import glob
import json
import os
import queue
import socket
import struct
import threading
import time
import urllib.request

SLOTS = 4
MAX_PARAMS = 400
SERVICE = b"_oscjson._tcp.local"


def _osc_string(data, at):
    end = data.index(b"\0", at)
    text = data[at:end].decode("utf-8", "replace")
    return text, (end + 4) & ~3


def parse_osc(data):
    """(address, [values]) of one OSC message; bundles give their first message."""
    if data.startswith(b"#bundle"):
        size = struct.unpack(">i", data[16:20])[0]
        return parse_osc(data[20:20 + size])
    address, at = _osc_string(data, 0)
    tags, at = _osc_string(data, at)
    values = []
    for t in tags[1:]:
        if t == "f":
            values.append(struct.unpack(">f", data[at:at + 4])[0]); at += 4
        elif t == "i":
            values.append(struct.unpack(">i", data[at:at + 4])[0]); at += 4
        elif t == "d":
            values.append(struct.unpack(">d", data[at:at + 8])[0]); at += 8
        elif t == "h":
            values.append(struct.unpack(">q", data[at:at + 8])[0]); at += 8
        elif t == "s":
            s, at = _osc_string(data, at); values.append(s)
        elif t == "T":
            values.append(True)
        elif t == "F":
            values.append(False)
        else:
            break
    return address, values


def _dns_name(data, at):
    """A DNS name at `at` (compression followed) and where the record goes on."""
    labels, jumped, end = [], False, None
    for _ in range(64):
        n = data[at]
        if n == 0:
            at += 1
            break
        if n & 0xC0 == 0xC0:
            if not jumped:
                end = at + 2
            at, jumped = ((n & 0x3F) << 8) | data[at + 1], True
            continue
        labels.append(data[at + 1:at + 1 + n])
        at += 1 + n
    return b".".join(labels), (end if jumped else at)


def discover(seconds=1.5):
    """Studios announcing OSCQuery on the local network: [(name, ip, port)]."""
    query = struct.pack(">6H", 0, 0, 1, 0, 0, 0)
    for label in SERVICE.split(b"."):
        query += bytes([len(label)]) + label
    query += b"\0" + struct.pack(">2H", 12, 1)
    found = {}
    s = None
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("", 5353))
        s.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP,
                     socket.inet_aton("224.0.0.251") + socket.inet_aton("0.0.0.0"))
        s.settimeout(0.3)
        s.sendto(query, ("224.0.0.251", 5353))
        srv, addr = {}, {}
        deadline = time.time() + seconds
        while time.time() < deadline:
            try:
                data, sender = s.recvfrom(9000)
            except socket.timeout:
                continue
            try:
                counts = struct.unpack(">6H", data[:12])
                at = 12
                for _ in range(counts[2]):
                    _, at = _dns_name(data, at)
                    at += 4
                for _ in range(counts[3] + counts[4] + counts[5]):
                    name, at = _dns_name(data, at)
                    kind, _, _, size = struct.unpack(">HHIH", data[at:at + 10])
                    at += 10
                    rdata = at
                    at += size
                    if kind == 33:
                        port = struct.unpack(">H", data[rdata + 4:rdata + 6])[0]
                        target, _ = _dns_name(data, rdata + 6)
                        srv[name] = (target, port, sender[0])
                    elif kind == 1 and size == 4:
                        addr[name] = socket.inet_ntoa(data[rdata:rdata + 4])
            except (IndexError, struct.error, ValueError):
                continue
        for name, (target, port, sender) in srv.items():
            if SERVICE in name:
                found[name] = (name.split(b".")[0].decode("utf-8", "replace"),
                               addr.get(target, sender), port)
    except OSError:
        pass
    finally:
        if s is not None:
            s.close()
    return list(found.values())


def fetch(host, port, path="/", timeout=2.0):
    with urllib.request.urlopen(f"http://{host}:{port}{path}", timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def leaves(node, out):
    """Every parameter of an OSCQuery tree: (address, type, value, range)."""
    if len(out) >= MAX_PARAMS:
        return out
    t = node.get("TYPE")
    if t and node.get("ACCESS", 3) & 2 and t in ("f", "i", "T", "F", "d", "h"):
        rng = (node.get("RANGE") or [{}])[0] or {}
        value = (node.get("VALUE") or [None])[0]
        out.append((node.get("FULL_PATH", ""), t, value, (rng.get("MIN"), rng.get("MAX"))))
    for child in (node.get("CONTENTS") or {}).values():
        leaves(child, out)
    return out


def studio_on_this_computer():
    """(port, token) of the newest Lanternist Studio running here with its control port on
    (the one AI tools use), or None."""
    folder = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Lanternist", "mcp")
    best = None
    for path in glob.glob(os.path.join(folder, "*.json")):
        try:
            with open(path, encoding="utf-8") as f:
                info = json.load(f)
        except (OSError, ValueError):
            continue
        if info.get("app") == "lanternist-studio" and (best is None or info["started"] > best["started"]):
            best = info
    return (best["port"], best["token"]) if best else None


def add_surfaces(sources, names):
    """Adds a surface showing each live source path in `sources` (named after `names`) to the
    Studio running here, each one undo step. Returns how many were added, or raises OSError /
    RuntimeError with why not."""
    found = studio_on_this_computer()
    if found is None:
        raise RuntimeError("no Lanternist Studio with AI tools on is running on this computer")
    port, token = found
    with socket.create_connection(("127.0.0.1", port), timeout=3) as s:
        f = s.makefile("rw", encoding="utf-8", newline="\n")

        def ask(line):
            f.write(json.dumps(line) + "\n")
            f.flush()
            return json.loads(f.readline() or "{}")

        if "ok" not in ask({"token": token}):
            raise RuntimeError("Studio did not let the component in")
        added = 0
        for n, (source, name) in enumerate(zip(sources, names)):
            reply = ask({"id": 2 * n + 1, "op": "edit",
                         "edit": {"op": "add", "kind": "Surface", "name": name}})
            if "ok" not in reply:
                raise RuntimeError(reply.get("error", "Studio refused the surface"))
            surface = reply["ok"]["id"]
            reply = ask({"id": 2 * n + 2, "op": "edit",
                         "edit": {"op": "add", "kind": "Source", "parent": surface,
                                  "params": {"kind": "media", "path": source}}})
            if "ok" not in reply:
                raise RuntimeError(reply.get("error", "Studio refused the source"))
            added += 1
        return added


class LanternistStudio:
    def __init__(self, owner):
        self.owner = owner
        self.inbox = queue.Queue()
        self.address_of = {}
        self.par_of = {}
        self.host = None
        self.applying = False
        self.searching = False
        self.frames = 0
        self.spout_failed = ""
        self.status("Looking for Lanternist Studio")
        self.Apply()
        self.Find()

    # ---- status and send / receive OPs ------------------------------------------------

    def status(self, text):
        self.owner.par.Status = text

    def sender_name(self, i):
        top = getattr(self.owner.par, f"Top{i}").eval()
        base = self.owner.par.Name.eval().strip() or ("TD - " + project.name.rsplit(".", 1)[0])
        return f"{base} - {top.name if top else i}"

    def Apply(self):
        """Switches the Spout and NDI OPs on or off as the parameters say."""
        p = self.owner.par
        method = p.Method.eval()
        for i in range(1, SLOTS + 1):
            on = bool(getattr(p, f"Send{i}").eval()) and getattr(p, f"Top{i}").eval() is not None
            spout = self.owner.op(f"spout{i}")
            ndi = self.owner.op(f"ndi{i}")
            name = self.sender_name(i)
            spout.par.sendername = name
            ndi.par.name = name
            use_spout = on and method in ("spout", "both") and not self.spout_failed
            use_ndi = on and (method in ("ndi", "both") or (method == "spout" and self.spout_failed))
            spout.par.active = use_spout
            ndi.par.active = use_ndi
        recv = self.owner.op("from_studio")
        recv.par.index = 0 if p.Receivemethod.eval() == "spout" else 1
        self.owner.op("from_studio_spout").par.sendername = p.Receivename.eval()
        self.owner.op("from_studio_ndi").par.name = p.Receivename.eval()
        self.owner.op("from_studio_ndi").par.active = bool(p.Receive.eval()) and p.Receivemethod.eval() == "ndi"

    def check_spout(self):
        if self.spout_failed or self.owner.par.Method.eval() == "ndi":
            return
        for i in range(1, SLOTS + 1):
            op_ = self.owner.op(f"spout{i}")
            if op_.par.active.eval() and op_.errors():
                self.spout_failed = op_.errors()
                self.status("Spout cannot send here (" + self.spout_failed.strip()
                            + "): sending over NDI instead")
                self.Apply()
                return

    # ---- finding Studio ----------------------------------------------------------------

    def Find(self):
        if self.searching:
            return
        self.searching = True
        typed = self.owner.par.Studio.eval().strip()
        qport = int(self.owner.par.Queryport.eval())
        threading.Thread(target=self._find, args=(typed, qport), daemon=True).start()

    def _find(self, typed, qport):
        try:
            hosts = [(typed, qport)] if typed else [("127.0.0.1", qport)]
            if not typed:
                hosts += [(ip, port) for _, ip, port in discover()]
            for host, port in hosts:
                try:
                    info = fetch(host, port, "/?HOST_INFO")
                    tree = fetch(host, port, "/")
                except (OSError, ValueError):
                    continue
                self.inbox.put(("found", host, port, info, tree))
                return
            self.inbox.put(("missing", typed))
        finally:
            self.searching = False

    def found(self, host, port, info, tree):
        self.host = host
        p = self.owner.par
        p.Queryport = port
        osc = self.owner.op("osc_out")
        osc.par.address = host
        osc.par.port = int(info.get("OSC_PORT") or p.Oscport.eval())
        p.Oscport = osc.par.port.eval()
        self.build_params(tree)
        ws = self.owner.op("listen")
        ws.par.netaddress = host
        ws.par.port = port
        ws.par.active = True
        ws.par.reset.pulse()
        name = info.get("NAME") or "Lanternist Studio"
        self.status(f"Connected to {name} at {host} ({len(self.par_of)} parameters)")

    # ---- Studio's parameters -----------------------------------------------------------

    def build_params(self, tree):
        comp = self.owner
        page = next((pg for pg in comp.customPages if pg.name == "Studio parameters"), None)
        if page is not None:
            page.destroy()
        page = comp.appendCustomPage("Studio parameters")
        self.address_of, self.par_of = {}, {}
        self.applying = True
        try:
            for n, (address, t, value, (lo, hi)) in enumerate(leaves(tree, [])):
                name = f"Sp{n + 1}"
                if t in ("T", "F"):
                    par = page.appendToggle(name, label=address)[0]
                elif t in ("i", "h"):
                    par = page.appendInt(name, label=address)[0]
                else:
                    par = page.appendFloat(name, label=address)[0]
                if lo is not None and hi is not None and t not in ("T", "F"):
                    par.normMin, par.normMax = lo, hi
                    par.min, par.max = lo, hi
                    par.clampMin = par.clampMax = True
                if value is not None:
                    par.val = value
                self.address_of[name] = address
                self.par_of[address] = par
        finally:
            self.applying = False

    def send(self, address, values):
        if self.host is None:
            self.status("Not connected to Lanternist Studio")
            return
        self.owner.op("osc_out").sendOSC(address, values)

    # ---- callbacks (parameter execute, WebSocket, every frame) ------------------------

    def OnValueChange(self, par):
        name = par.name
        if self.applying or name == "Status":
            return
        if name in self.address_of:
            value = par.eval()
            self.send(self.address_of[name], [bool(value) if par.isToggle else value])
        elif name in ("Studio", "Queryport", "Oscport"):
            self.host = None
            self.Find()
        elif name in ("Method",):
            self.spout_failed = ""
            self.Apply()
        else:
            self.Apply()

    def OnPulse(self, par):
        name = par.name
        if name == "Go":
            self.send("/cue/go", [])
        elif name == "Back":
            self.send("/cue/back", [])
        elif name == "Gotocue":
            cue = self.owner.par.Cue.eval().strip()
            if cue:
                self.send("/cue/goto", [int(cue)] if cue.isdigit() else [cue])
        elif name == "Showinstudio":
            self.show_in_studio()
        elif name == "Reconnect":
            self.host = None
            self.Find()

    def show_in_studio(self):
        """A surface in Studio (on this computer) for each TOP being sent."""
        p = self.owner.par
        sources, names = [], []
        for i in range(1, SLOTS + 1):
            spout, ndi = self.owner.op(f"spout{i}"), self.owner.op(f"ndi{i}")
            name = self.sender_name(i)
            if spout.par.active.eval():
                sources.append("spout:" + name)
            elif ndi.par.active.eval():
                sources.append(f"ndi:{socket.gethostname().upper()} ({name})")
            else:
                continue
            top = getattr(p, f"Top{i}").eval()
            names.append("TD " + (top.name if top else str(i)))
        if not sources:
            self.status("Nothing is being sent: switch on a TOP on the Send to Studio page")
            return
        try:
            n = add_surfaces(sources, names)
            self.status(f"Added {n} surface(s) in Studio showing TouchDesigner")
        except (OSError, RuntimeError, ValueError, KeyError) as e:
            self.status(f"Could not add surfaces in Studio: {e}")

    def OnConnect(self, dat):
        for address in self.par_of:
            dat.sendText(json.dumps({"COMMAND": "LISTEN", "DATA": address}))

    def OnBinary(self, dat, contents):
        try:
            address, values = parse_osc(bytes(contents))
        except (ValueError, IndexError, struct.error):
            return
        par = self.par_of.get(address)
        if par is None or not values:
            return
        self.applying = True
        try:
            par.val = values[0]
        finally:
            self.applying = False

    def OnText(self, dat, text):
        # The project's parameters changed (surfaces added or removed): read them again.
        if "PATH_" in text:
            self.Find()

    def OnDisconnect(self, dat):
        if self.host is not None:
            self.status("Lost Lanternist Studio: looking again")
            self.host = None

    def Tick(self):
        self.frames += 1
        while True:
            try:
                msg = self.inbox.get_nowait()
            except queue.Empty:
                break
            if msg[0] == "found":
                self.found(*msg[1:])
            elif msg[0] == "missing":
                where = f"at {msg[1]}" if msg[1] else "on this computer or the network"
                self.status(f"No Lanternist Studio found {where}: is it running? Looking again")
        if self.frames % 60 == 0:
            self.check_spout()
        if self.host is None and not self.searching and self.frames % 300 == 0:
            self.Find()
