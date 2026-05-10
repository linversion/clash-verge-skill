# Clash Verge Skill

A local skill for controlling **Clash Verge Rev / mihomo** from OpenClaw.

It uses:
- the mihomo external controller API for runtime changes
- local Clash Verge config files for persistent changes
- `networksetup` for macOS system proxy inspection/control

## What it can do

- check runtime status
- switch proxy mode: `rule` / `global` / `direct`
- toggle runtime TUN
- toggle persistent TUN
- inspect system proxy state
- enable / disable system proxy
- inspect groups, nodes, delays, connections, rules, DNS

## Main commands

```bash
python3 scripts/clash-verge.py status
python3 scripts/clash-verge.py configs

python3 scripts/clash-verge.py mode rule
python3 scripts/clash-verge.py mode global
python3 scripts/clash-verge.py mode direct

python3 scripts/clash-verge.py tun
python3 scripts/clash-verge.py tun on
python3 scripts/clash-verge.py tun off
python3 scripts/clash-verge.py persist-tun on
python3 scripts/clash-verge.py persist-tun off

python3 scripts/clash-verge.py system-proxy
python3 scripts/clash-verge.py system-proxy status
python3 scripts/clash-verge.py system-proxy on
python3 scripts/clash-verge.py system-proxy off
```

## How it works

### Runtime control
Runtime changes go to mihomo `/configs`, usually through:
- `/tmp/verge/verge-mihomo.sock`
- fallback: `http://127.0.0.1:9090`

### Persistent control
Persistent changes edit these files:
- `~/Library/Application Support/io.github.clash-verge-rev.clash-verge-rev/verge.yaml`
- `~/Library/Application Support/io.github.clash-verge-rev.clash-verge-rev/config.yaml`

### System proxy control
System proxy changes use macOS `networksetup` on detected network services.

## Notes

- This does **not** automate the Clash Verge GUI.
- It assumes the current Clash Verge file layout is still valid.
- `system-proxy status` is the safest diagnostic entrypoint because app preference and actual OS state can differ.
