---
name: clash-verge
description: Control Clash Verge Rev via mihomo API. Use this whenever the user mentions Clash Verge, mihomo, proxy nodes, TUN mode, system proxy, Discord/network proxy issues, or wants to inspect or change Clash runtime or persistent settings. Supports runtime TUN, persistent TUN, proxy mode, proxy groups, node switching, delay tests, connections, DNS, and unified system proxy on/off/status control.
---

# Clash Verge Skill

Control Clash Verge Rev (mihomo core) through its external controller API, plus a small macOS helper layer for persistent settings and system proxy control.

## Best use cases

Use this skill for:
- checking whether Clash Verge / mihomo is running
- checking whether TUN is active
- toggling TUN at runtime
- toggling TUN persistently
- switching proxy mode: `rule` / `global` / `direct`
- checking Clash Verge saved system-proxy preference vs actual macOS proxy state
- enabling or disabling macOS system proxy together with Clash Verge's saved preference
- listing groups and nodes, switching nodes, testing delay
- inspecting connections, rules, DNS, and runtime config

## Boundary

This skill talks to the **mihomo runtime API** and edits known Clash Verge config files on macOS.
It does **not** drive the Clash Verge GUI directly.

That means:
- it **can** patch runtime `/configs`
- it **can** edit persistent Clash Verge config files
- it **can** use `networksetup` to inspect or set macOS proxy state
- it **cannot guarantee** future Clash Verge versions keep the same file layout or proxy behavior

## CLI Tool

```bash
python3 {baseDir}/scripts/clash-verge.py
```

## Connection

Preferred connection:
- Unix socket: `/tmp/verge/verge-mihomo.sock`

Fallback:
- HTTP API: `http://127.0.0.1:9090`

Optional overrides:
- env: `CLASH_SOCK`, `CLASH_API`, `CLASH_SECRET`
- flags: `--sock`, `--api`, `--secret`

## Commands

```bash
# Overall status
clash-verge.py status

# Full runtime config
clash-verge.py configs

# Proxy mode
clash-verge.py mode
clash-verge.py mode rule
clash-verge.py mode global
clash-verge.py mode direct

# TUN runtime control
clash-verge.py tun
clash-verge.py tun on
clash-verge.py tun off
clash-verge.py tun on --stack mixed
clash-verge.py tun on --stack gvisor

# TUN persistent control
clash-verge.py persist-tun on
clash-verge.py persist-tun off
clash-verge.py persist-tun on --stack mixed

# System proxy
clash-verge.py system-proxy
clash-verge.py system-proxy status
clash-verge.py system-proxy on
clash-verge.py system-proxy off

# Proxy groups & nodes
clash-verge.py groups
clash-verge.py nodes <group>
clash-verge.py select <group> <node>

# Delay testing
clash-verge.py delay <node>
clash-verge.py delay-group <group>

# Connections / rules / DNS
clash-verge.py conns [--limit N]
clash-verge.py rules [--limit N]
clash-verge.py dns <domain> [--type A|AAAA|CNAME]
clash-verge.py flush-dns

# Maintenance
clash-verge.py restart
clash-verge.py upgrade-geo
```

## How runtime TUN works

Runtime TUN is enabled by PATCHing mihomo `/configs` with a payload like:

```json
{
  "tun": {
    "enable": true,
    "stack": "mixed",
    "auto-route": true,
    "auto-detect-interface": true,
    "dns-hijack": ["any:53"]
  }
}
```

## How `persist-tun` works

`persist-tun on/off` does three things:
1. backs up local Clash Verge config files
2. edits persistent config in:
   - `~/Library/Application Support/io.github.clash-verge-rev.clash-verge-rev/verge.yaml`
   - `~/Library/Application Support/io.github.clash-verge-rev.clash-verge-rev/config.yaml`
3. patches current runtime so the effect is immediate

## How `system-proxy` works

`system-proxy status` reports both:
- Clash Verge saved preference: `enable_system_proxy` in `verge.yaml`
- actual macOS proxy state from `networksetup`

That dual view matters because app preference and OS reality can drift apart.

`system-proxy on/off`:
- backs up `verge.yaml`
- sets `enable_system_proxy` to `true` or `false`
- applies web + secure web proxy state for each detected macOS network service
- when enabling, uses the current mihomo `mixed-port`
- waits briefly, then re-reads the OS proxy state

Treat this as a practical control flow, not a forever guarantee across app upgrades.

## Notes

- No external Python deps.
- Unix socket is preferred over HTTP.
- Group/node names with emoji or CJK are supported.
- Runtime TUN changes alone may not update Clash Verge GUI preference files.
- Persistent behavior relies on the current Clash Verge file layout.
- If Discord or another app ignores system proxy, TUN is often the right fix.
