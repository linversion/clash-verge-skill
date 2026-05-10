#!/usr/bin/env python3
"""Clash Verge CLI - control Clash Verge Rev / mihomo via external controller API.

Extended locally to support runtime TUN toggling, persistent TUN settings,
and system proxy inspection/disable flows.
"""

import argparse
import json
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_SOCK = "/tmp/verge/verge-mihomo.sock"
DEFAULT_HTTP = "http://127.0.0.1:9090"
APP_SUPPORT_DIR = Path("/Users/stan/Library/Application Support/io.github.clash-verge-rev.clash-verge-rev")
VERGE_YAML = APP_SUPPORT_DIR / "verge.yaml"
CONFIG_YAML = APP_SUPPORT_DIR / "config.yaml"


def _get_args():
    import os
    sock = os.environ.get("CLASH_SOCK", DEFAULT_SOCK)
    http = os.environ.get("CLASH_API", DEFAULT_HTTP)
    secret = os.environ.get("CLASH_SECRET", "")
    return sock, http, secret


class UnixHTTPConnection:
    def __init__(self, sock_path):
        self.sock_path = sock_path
        self.timeout = 10
        self._sock = None

    def request(self, method, url, body=None, headers=None):
        headers = headers or {}
        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._sock.settimeout(self.timeout)
        self._sock.connect(self.sock_path)
        lines = [f"{method} {url} HTTP/1.1", "Host: localhost", "Connection: close"]
        if body:
            lines.append(f"Content-Length: {len(body)}")
        for k, v in headers.items():
            lines.append(f"{k}: {v}")
        lines.extend(["", ""])
        raw = "\r\n".join(lines).encode()
        if body:
            raw += body.encode() if isinstance(body, str) else body
        self._sock.sendall(raw)

    def getresponse(self):
        data = b""
        while True:
            chunk = self._sock.recv(65536)
            if not chunk:
                break
            data += chunk
        self._sock.close()
        return _RawResponse(data)


class _RawResponse:
    def __init__(self, data):
        parts = data.split(b"\r\n\r\n", 1)
        header_block = parts[0].decode(errors="replace")
        self.body = parts[1] if len(parts) > 1 else b""
        first = header_block.split("\r\n")[0]
        pieces = first.split(" ", 2)
        self.status = int(pieces[1]) if len(pieces) > 1 else 0
        self.reason = pieces[2] if len(pieces) > 2 else ""
        self._headers = {}
        for line in header_block.split("\r\n")[1:]:
            if ": " in line:
                k, v = line.split(": ", 1)
                self._headers[k.lower()] = v
        if self._headers.get("transfer-encoding", "").lower() == "chunked":
            self.body = self._decode_chunked(self.body)

    def _decode_chunked(self, data):
        out = b""
        while data:
            line_end = data.find(b"\r\n")
            if line_end == -1:
                break
            size_str = data[:line_end].decode().strip()
            if not size_str:
                data = data[line_end + 2:]
                continue
            size = int(size_str, 16)
            if size == 0:
                break
            out += data[line_end + 2:line_end + 2 + size]
            data = data[line_end + 2 + size + 2:]
        return out

    def read(self):
        return self.body


def api(method, path, body=None):
    sock, http_url, secret = _get_args()
    headers = {"Content-Type": "application/json"}
    if secret:
        headers["Authorization"] = f"Bearer {secret}"
    payload = json.dumps(body) if body is not None else None

    if Path(sock).exists():
        conn = UnixHTTPConnection(sock)
        conn.request(method, path, body=payload, headers=headers)
        resp = conn.getresponse()
        raw = resp.read()
        if resp.status >= 400:
            print(f"API error {resp.status}: {raw.decode(errors='replace')}", file=sys.stderr)
            sys.exit(1)
        return json.loads(raw) if raw.strip() else {}

    url = http_url.rstrip("/") + path
    req = urllib.request.Request(url, data=payload.encode() if payload else None, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read()
            return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as e:
        print(f"API error {e.code}: {e.read().decode(errors='replace')}", file=sys.stderr)
        sys.exit(1)


def _must_exist(path: Path):
    if not path.exists():
        print(f"Missing file: {path}", file=sys.stderr)
        sys.exit(1)


def _read_text(path: Path) -> str:
    _must_exist(path)
    return path.read_text()


def _write_text(path: Path, text: str):
    path.write_text(text)


def _backup(path: Path) -> Path:
    ts = time.strftime("%Y%m%d-%H%M%S")
    backup = path.with_name(path.name + f".bak.{ts}")
    backup.write_text(path.read_text())
    return backup


def _replace_line(text: str, key: str, value: str) -> str:
    lines = text.splitlines()
    replaced = False
    prefix = f"{key}:"
    for i, line in enumerate(lines):
        if line.startswith(prefix):
            lines[i] = f"{key}: {value}"
            replaced = True
            break
    if not replaced:
        lines.append(f"{key}: {value}")
    return "\n".join(lines) + "\n"


def _set_config_tun_block(text: str, enable: bool, stack: str, mode: str | None = None) -> str:
    lines = text.splitlines()
    out = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("mode:") and mode is not None:
            out.append(f"mode: {mode}")
            i += 1
            continue
        if line == "tun:":
            out.extend([
                "tun:",
                f"  enable: {'true' if enable else 'false'}",
                f"  stack: {stack}",
                "  auto-route: true",
                "  strict-route: false",
                "  auto-detect-interface: true",
                "  dns-hijack:",
                "  - any:53",
            ])
            i += 1
            while i < len(lines) and (lines[i].startswith("  ") or lines[i].strip() == ""):
                i += 1
            continue
        out.append(line)
        i += 1
    return "\n".join(out) + "\n"


def _tun_patch(enable: bool, stack: str):
    api("PATCH", "/configs", {
        "tun": {
            "enable": enable,
            "stack": stack,
            "auto-route": True,
            "auto-detect-interface": True,
            "dns-hijack": ["any:53"],
        }
    })


def _network_services():
    out = subprocess.check_output(["networksetup", "-listallnetworkservices"], text=True)
    return [line.strip() for line in out.splitlines()[1:] if line.strip() and not line.startswith("*")]


def _proxy_state_for(service: str):
    web = subprocess.check_output(["networksetup", "-getwebproxy", service], text=True)
    secure = subprocess.check_output(["networksetup", "-getsecurewebproxy", service], text=True)
    return {"web": web.strip(), "secure": secure.strip()}


def _disable_proxy_for(service: str):
    subprocess.run(["networksetup", "-setwebproxystate", service, "off"], check=True)
    subprocess.run(["networksetup", "-setsecurewebproxystate", service, "off"], check=True)


def cmd_status(_args):
    ver = api("GET", "/version")
    cfg = api("GET", "/configs")
    conns = api("GET", "/connections")

    tun = cfg.get("tun", {})
    print(f"Mihomo {ver.get('version', '?')}")
    print(f"Mode: {cfg.get('mode', '?')}")
    print(f"Mixed port: {cfg.get('mixed-port', '?')}")
    print(f"TUN: {'enabled' if tun.get('enable') else 'disabled'}")
    print(f"TUN stack: {tun.get('stack', '?')}")
    print(f"TUN device: {tun.get('device', '') or '-'}")
    print(f"Connections: {len(conns.get('connections', []))} active")
    print(f"Traffic: ↑ {_fmt_bytes(conns.get('uploadTotal', 0))}  ↓ {_fmt_bytes(conns.get('downloadTotal', 0))}")


def cmd_configs(_args):
    print(json.dumps(api("GET", "/configs"), ensure_ascii=False, indent=2))


def cmd_mode(args):
    if args.value:
        api("PATCH", "/configs", {"mode": args.value})
        print(f"Mode set to: {args.value}")
    else:
        print(api("GET", "/configs").get("mode", "?"))


def cmd_tun(args):
    if not args.value:
        tun = api("GET", "/configs").get("tun", {})
        print(json.dumps(tun, ensure_ascii=False, indent=2))
        return
    stack = "mixed" if args.stack == "mixed" else "gVisor"
    _tun_patch(args.value == "on", stack)
    tun = api("GET", "/configs").get("tun", {})
    state = "enabled" if tun.get("enable") else "disabled"
    print(f"TUN {state}")
    print(f"stack: {tun.get('stack', '?')}")
    print(f"device: {tun.get('device', '') or '-'}")


def cmd_persist_tun(args):
    enable = args.value == "on"
    stack = "mixed" if args.stack == "mixed" else "gvisor"
    _backup(VERGE_YAML)
    _backup(CONFIG_YAML)
    verge = _read_text(VERGE_YAML)
    verge = _replace_line(verge, "enable_tun_mode", "true" if enable else "false")
    _write_text(VERGE_YAML, verge)
    config = _read_text(CONFIG_YAML)
    config = _set_config_tun_block(config, enable=enable, stack=stack, mode=None)
    _write_text(CONFIG_YAML, config)
    _tun_patch(enable, "mixed" if args.stack == "mixed" else "gVisor")
    tun = api("GET", "/configs").get("tun", {})
    print(f"persist_tun: {'on' if enable else 'off'}")
    print(f"runtime_enable: {tun.get('enable')}")
    print(f"runtime_device: {tun.get('device', '') or '-'}")
    print(f"verge_pref: {'true' if 'enable_tun_mode: true' in _read_text(VERGE_YAML) else 'false'}")


def _set_system_proxy(enable: bool):
    _backup(VERGE_YAML)
    verge = _read_text(VERGE_YAML)
    verge = _replace_line(verge, "enable_system_proxy", "true" if enable else "false")
    _write_text(VERGE_YAML, verge)
    mixed_port = api("GET", "/configs").get("mixed-port", 7897)
    for svc in _network_services():
        if enable:
            subprocess.run(["networksetup", "-setwebproxy", svc, "127.0.0.1", str(mixed_port)], check=True)
            subprocess.run(["networksetup", "-setsecurewebproxy", svc, "127.0.0.1", str(mixed_port)], check=True)
            subprocess.run(["networksetup", "-setwebproxystate", svc, "on"], check=True)
            subprocess.run(["networksetup", "-setsecurewebproxystate", svc, "on"], check=True)
        else:
            _disable_proxy_for(svc)
    time.sleep(2)
    state = "on" if enable else "off"
    print(f"set Clash Verge preference: enable_system_proxy={state}")
    for svc in _network_services():
        ps = _proxy_state_for(svc)
        print(f"[{svc}]")
        print(ps['web'])
        print("---")
        print(ps['secure'])


def cmd_system_proxy(args):
    if args.value == "status":
        verge = _read_text(VERGE_YAML)
        app_pref = "true" if "enable_system_proxy: true" in verge else "false"
        print(f"app_pref_enable_system_proxy: {app_pref}")
        for svc in _network_services():
            state = _proxy_state_for(svc)
            print(f"[{svc}]")
            print(state['web'])
            print("---")
            print(state['secure'])
    elif args.value == "on":
        _set_system_proxy(True)
    else:
        _set_system_proxy(False)


def cmd_groups(_args):
    data = api("GET", "/proxies")
    proxies = data.get("proxies", {})
    group_types = ("Selector", "URLTest", "Fallback", "LoadBalance")
    for name, g in sorted(proxies.items()):
        if g.get("type") in group_types:
            print(f"{name} ({g.get('type', '?')}): {g.get('now', '-')} [{len(g.get('all', []))} nodes]")


def cmd_nodes(args):
    data = api("GET", f"/proxies/{_urlencode(args.group)}")
    if "all" not in data:
        print(f"'{args.group}' is not a group or not found.", file=sys.stderr)
        sys.exit(1)
    print(f"Group: {args.group}")
    print(f"Current: {data.get('now', '-')}")
    for node in data.get("all", []):
        marker = " ★" if node == data.get("now") else ""
        print(f"  {node}{marker}")


def cmd_select(args):
    api("PUT", f"/proxies/{_urlencode(args.group)}", {"name": args.node})
    print(f"Switched '{args.group}' → {args.node}")


def cmd_delay(args):
    url = args.url or "http://www.gstatic.com/generate_204"
    timeout = args.timeout or 5000
    result = api("GET", f"/proxies/{_urlencode(args.target)}/delay?timeout={timeout}&url={_urlencode(url)}")
    d = result.get("delay", 0)
    print(f"{args.target}: {d}ms" if d > 0 else f"{args.target}: timeout / unreachable")


def cmd_delay_group(args):
    url = args.url or "http://www.gstatic.com/generate_204"
    timeout = args.timeout or 5000
    data = api("GET", f"/proxies/{_urlencode(args.group)}")
    for node in data.get("all", []):
        try:
            r = api("GET", f"/proxies/{_urlencode(node)}/delay?timeout={timeout}&url={_urlencode(url)}")
            d = r.get("delay", 0)
        except SystemExit:
            d = 0
        print(f"{node}: {d}ms" if d > 0 else f"{node}: timeout")


def cmd_conns(args):
    data = api("GET", "/connections")
    conns = data.get("connections", [])
    limit = args.limit or 20
    for c in conns[:limit]:
        md = c.get("metadata", {})
        print(f"{c.get('id')}  {md.get('type', '?')}  {md.get('host', '') or md.get('destinationIP', '')}  via {' > '.join(c.get('chains', []))}")
    print(f"showing {min(limit, len(conns))} / {len(conns)} connections")


def cmd_rules(args):
    data = api("GET", "/rules")
    rules = data.get("rules", [])
    limit = args.limit or 30
    for r in rules[:limit]:
        print(f"{r.get('type', '?')}: {r.get('payload', '')} -> {r.get('proxy', '')}")
    print(f"showing {min(limit, len(rules))} / {len(rules)} rules")


def cmd_dns(args):
    data = api("GET", f"/dns/query?name={_urlencode(args.domain)}&type={_urlencode(args.type)}")
    print(json.dumps(data, ensure_ascii=False, indent=2))


def cmd_flush_dns(_args):
    api("POST", "/cache/fakeip/flush")
    print("DNS cache flushed.")


def cmd_restart(_args):
    api("PUT", "/restart")
    print("Core restarting...")


def cmd_upgrade_geo(_args):
    api("POST", "/configs/geo")
    print("GeoIP/GeoSite update triggered.")


def _fmt_bytes(n):
    for unit in ("B", "KB", "MB", "GB"):
        if abs(n) < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


def _urlencode(s):
    import urllib.parse
    return urllib.parse.quote(str(s), safe="")


def main():
    p = argparse.ArgumentParser(description="Clash Verge CLI - control mihomo via API")
    p.add_argument("--sock", help=f"Unix socket path (default: {DEFAULT_SOCK})")
    p.add_argument("--api", help=f"HTTP API URL (default: {DEFAULT_HTTP})")
    p.add_argument("--secret", help="API secret")
    sub = p.add_subparsers(dest="cmd")

    sub.add_parser("status", help="Show overall status")
    sub.add_parser("configs", help="Show full runtime configs")

    s = sub.add_parser("mode", help="Get/set proxy mode")
    s.add_argument("value", nargs="?", choices=["rule", "global", "direct"])

    s = sub.add_parser("tun", help="Get/set runtime TUN state")
    s.add_argument("value", nargs="?", choices=["on", "off"])
    s.add_argument("--stack", default="mixed", choices=["mixed", "gvisor"], help="TUN stack when enabling")

    s = sub.add_parser("persist-tun", help="Persist TUN setting to Clash Verge files and runtime")
    s.add_argument("value", choices=["on", "off"])
    s.add_argument("--stack", default="mixed", choices=["mixed", "gvisor"], help="TUN stack when enabling")

    s = sub.add_parser("system-proxy", help="Show or set Clash Verge system proxy state")
    s.add_argument("value", nargs="?", choices=["status", "on", "off"], default="status")

    sub.add_parser("groups", help="List proxy groups")

    s = sub.add_parser("nodes", help="List nodes in a group")
    s.add_argument("group")

    s = sub.add_parser("select", help="Select node in a group")
    s.add_argument("group")
    s.add_argument("node")

    s = sub.add_parser("delay", help="Test node delay")
    s.add_argument("target")
    s.add_argument("--url")
    s.add_argument("--timeout", type=int)

    s = sub.add_parser("delay-group", help="Test all nodes in a group")
    s.add_argument("group")
    s.add_argument("--url")
    s.add_argument("--timeout", type=int)

    s = sub.add_parser("conns", help="List active connections")
    s.add_argument("--limit", type=int)

    s = sub.add_parser("rules", help="List rules")
    s.add_argument("--limit", type=int)

    s = sub.add_parser("dns", help="Query DNS")
    s.add_argument("domain")
    s.add_argument("--type", default="A")

    sub.add_parser("flush-dns", help="Flush DNS cache")
    sub.add_parser("restart", help="Restart mihomo core")
    sub.add_parser("upgrade-geo", help="Update GeoIP/GeoSite databases")

    args = p.parse_args()

    import os
    if args.sock:
        os.environ["CLASH_SOCK"] = args.sock
    if args.api:
        os.environ["CLASH_API"] = args.api
    if args.secret:
        os.environ["CLASH_SECRET"] = args.secret

    dispatch = {
        "status": cmd_status,
        "configs": cmd_configs,
        "mode": cmd_mode,
        "tun": cmd_tun,
        "persist-tun": cmd_persist_tun,
        "system-proxy": cmd_system_proxy,
        "groups": cmd_groups,
        "nodes": cmd_nodes,
        "select": cmd_select,
        "delay": cmd_delay,
        "delay-group": cmd_delay_group,
        "conns": cmd_conns,
        "rules": cmd_rules,
        "dns": cmd_dns,
        "flush-dns": cmd_flush_dns,
        "restart": cmd_restart,
        "upgrade-geo": cmd_upgrade_geo,
    }
    if args.cmd in dispatch:
        dispatch[args.cmd](args)
    else:
        p.print_help()


if __name__ == "__main__":
    main()
