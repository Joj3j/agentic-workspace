---
name: subscription-local-dev-run
description: >-
  Run the non-interactive comm-subscription-server subscribe + Kafka listen demo
  for local dev: creates an SRL gNMI subscription, appends more paths to it after a
  delay, and streams the matching Kafka topic in a readable, color-coded format —
  in two terminals/tmux panes side by side. Always checks that comm-subscription-server
  and comm-worker-gnmi are both running first and asks the user to start whichever is
  down instead of proceeding. Use when asked to demo subscription_test_client, show a
  live gNMI subscribe + Kafka notification flow, or manually verify a gNMI path-building
  fix end-to-end against a local CSS + worker + Kafka stack.
---

# Subscription live demo (subscribe + Kafka listen)

Wraps `comm-subscription-server/cmd/subscription_test_client/scripts/` — do not
reimplement this logic inline; call the scripts.

## Prerequisites — check before anything else

This demo needs three local processes: Kafka broker, `comm-subscription-server` (CSS,
gRPC `:50056`), and `comm-worker-gnmi` (gRPC `:50051`, http/livez `:8092`).

**Always run the preflight check first, and never start CSS/worker yourself:**

```bash
cd /home/joji/Go/comm-subscription-server
cmd/subscription_test_client/scripts/check_prereqs.sh
```

- Exit 0 + `prereqs OK: ...` → continue.
- Exit 1 → it prints exactly which service is down and the command to start it
  (`go run ./cmd/comm-subscription-server/main.go` from `comm-subscription-server/`, or
  `go run main.go` from `comm-worker-gnmi-go/`). **Stop and ask the user to start the
  missing service(s) in their own terminal** — do not launch it in a background shell
  on their behalf unless they explicitly ask you to.

If both are up but the target NE (default SRL `92.4.201.116`, topic
`SrlGnmiMdcNBI-25.10.2`) isn't reachable (no lab VPN/tunnel from this machine), CSS/worker
calls still succeed (bookkeeping only) but the Kafka pane stays idle — this is expected
and is not a failure of the demo scripts.

## Run it

Preferred — one command, two tmux panes:

```bash
cd /home/joji/Go/comm-subscription-server
cmd/subscription_test_client/scripts/demo_tmux.sh
tmux attach -t sub-demo
```

- Left pane: `demo_kafka_listen.sh` — continuous, pretty-printed Kafka stream (never exits on its own; `Ctrl-b d` to detach, `tmux kill-session -t sub-demo` to stop).
- Right pane: `demo_subscribe_flow.sh` — `subset-create` → sleep `WAIT_SECONDS` (default `60`) → `subset-add` on the same `subscription_id`, then exits.

Without tmux, run the two scripts in separate terminals:

```bash
# terminal A
cmd/subscription_test_client/scripts/demo_kafka_listen.sh
# terminal B
WAIT_SECONDS=60 cmd/subscription_test_client/scripts/demo_subscribe_flow.sh
```

Env overrides (all optional): `ADDR` (CSS addr, default `localhost:50056`), `TOPIC`
(default `SrlGnmiMdcNBI-25.10.2`), `NE_IDS` (default `92.4.201.116`), `WAIT_SECONDS`
(default `60`), `WORKER_HTTP_ADDR` (worker livez, default `localhost:8092`), `SESSION`
(tmux session name, default `sub-demo`).

## Reading the output

`demo_subscribe_flow.sh` prints two `SubscribeResponse` JSON blocks (create, then add) and
the `subscription_id` — save it; cancel afterward with:

```bash
bin/subscription_test_client -subscription-id <id> -cmd cancel
```

**A single `cancel` only removes that one `subscription_id`.** If other subscriptions are still
active for the same NE (e.g. left over from a previous run), the worker's southbound session and
the Kafka `LIVE` feed stay up regardless — cancelling one subscription will *not* quiet the pane.
Check what's still active and sweep it all with:

```bash
bin/subscription_test_client -ne 92.4.201.116 -client-id mdm -cmd list
bin/subscription_test_client -ne 92.4.201.116 -client-id mdm -cmd cancel-all
```

Always run `cancel-all` after a demo session to avoid leaking subscriptions into the next one.

`demo_kafka_listen.sh` output (via `pretty_listen.py`) is one line per event:

```
21:37:00.787 SYNC   srl_nokia-interfaces:interface[name=ethernet-1/1]     CREATE    admin-state=enable, oper-state=up
21:37:00.825 SYNC   nsp-model-notification:/subscription-sync-complete   SYNC_COMPLETE ne=92.4.201.116
21:37:05.200 LIVE   srl_nokia-platform:platform/control[slot=A]/oper-state UPDATE   oper-state=up
```

Columns: time · `source` (SYNC=snapshot / LIVE=streaming / REPLAY) · instance path (or
schema node id for sentinels) · `operation` (or sentinel name) · short value summary. Expect
a `SYNC` burst right after `subset-create`/`subset-add`, a `SYNC_COMPLETE` sentinel, then
ongoing `LIVE` updates.

## Reference

Full runbook and verified sample output (including a real end-to-end run against the lab NE):
[`comm-subscription-server/docs/actual/local-dev-live-demo.md`](/home/joji/Go/comm-subscription-server/docs/actual/local-dev-live-demo.md).
