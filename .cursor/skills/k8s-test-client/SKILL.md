---
name: k8s-test-client
description: >-
  Build and run Go test clients (comm-layer-server rpc_test_client,
  device-registry test_client, comm-worker-gnmi worker_test_client,
  comm-subscription-server subscription_test_client) against K8s-deployed
  services via SSH tunnel and kubectl port-forward. Use when the user wants
  to run test clients against a K8s cluster, generate test data on K8s, or
  connect to remote gRPC services through a jump host.
---

# K8s Test Client

Run the workspace test clients against services deployed in Kubernetes.
Runs `kubectl port-forward` on the jump host (listening on `0.0.0.0`) so the
client connects to `<jump-host>:<port>` -- no NodePort, Ingress, or Service
changes needed.

## Prerequisites

- SSH access to a jump host that has `kubectl` configured for the cluster.
- Jump host IP reachable from the dev machine (default `100.127.201.224`).

## Service / port mapping

| Service | Namespace | K8s svc port | Forward port | Client binary |
|---------|-----------|-------------|-------------|---------------|
| comm-layer-server | nsp-communicator | 9001 | 40055 | `bin/rpc_test_client` |
| device-registry | nsp-device | 9001 | 40058 | `bin/test-client` |
| comm-worker-gnmi | nsp-communicator | 9001 | 40051 | `bin/worker_test_client` |
| comm-subscription-server | nsp-communicator | 50056 | 40056 | `bin/subscription_test_client` |

## Scripts and env (workspace-settings)

| Artifact | Location |
|----------|----------|
| Env loader | `.cursor/scripts/k8s-test-client/k8s_test_env.sh` |
| Secrets template | `.cursor/scripts/k8s-test-client/k8s_test_env.local.example` → copy to `k8s_test_env.local` (gitignored) |
| Run script | `.cursor/scripts/k8s-test-client/k8s_run_test_client.sh` |

## Agent steps

### 1 -- Set up environment (once)

```bash
cd workspace-settings/.cursor/scripts/k8s-test-client
cp k8s_test_env.local.example k8s_test_env.local
# Edit k8s_test_env.local: jump host IP, SSH user/key
source k8s_test_env.sh
```

### 2 -- Check pods are running

```bash
cd workspace-settings/.cursor/scripts/k8s-test-client
bash k8s_run_test_client.sh --status --client comm-layer-server
bash k8s_run_test_client.sh --status --client device-registry
bash k8s_run_test_client.sh --status --client comm-worker-gnmi
bash k8s_run_test_client.sh --status --client comm-subscription-server
```

### 3 -- Run a test client

```bash
cd workspace-settings/.cursor/scripts/k8s-test-client

# comm-layer-server
bash k8s_run_test_client.sh --client comm-layer-server

# device-registry
bash k8s_run_test_client.sh --client device-registry

# comm-worker-gnmi
bash k8s_run_test_client.sh --client comm-worker-gnmi

# comm-subscription-server
bash k8s_run_test_client.sh --client comm-subscription-server

# Pass extra flags (e.g. subscribe gNMI, cancel, list)
bash k8s_run_test_client.sh --client comm-subscription-server -- -ne <ne-id> -cmd subscribe
bash k8s_run_test_client.sh --client comm-subscription-server -- -ne <ne-id> -protocol netconf -cmd subscribe
bash k8s_run_test_client.sh --client comm-subscription-server -- -ne <ne-id> -subscription-id <id> -cmd cancel
bash k8s_run_test_client.sh --client comm-subscription-server -- -ne <ne-id> -client-id mdm -cmd list

# Force rebuild + pass extra flags
bash k8s_run_test_client.sh --client comm-layer-server --build -- -tls -clientid myid
```

Or from the repo shortcut:

```bash
cd comm-layer-server && ./bin/k8s_rpc_test.sh
cd comm-worker-gnmi-go && ./bin/k8s_gnmi_test.sh
cd comm-subscription-server && ./bin/k8s_sub_test.sh
cd comm-subscription-server && ./bin/k8s_sub_test.sh -- -ne <ne-id> -cmd subscribe
```

The wrapper:
1. Builds the binary if needed
2. Kills any stale port-forward on the jump host
3. Starts `kubectl port-forward --address 0.0.0.0` on the jump host via SSH
4. Launches the client connecting to `<jump-host>:<forward-port>`
5. Tears down the port-forward on exit

## Adding a new client

See [reference.md](reference.md) for the step-by-step checklist.

## Troubleshooting

- **Port-forward fails to start**: check SSH access (`ssh root@<jump-host>`)
  and that `kubectl` works on the jump host (`ssh root@<jump-host> kubectl get nodes`).
- **Port already in use**: the script auto-kills stale port-forwards via
  `fuser`. If it still fails, change `CLS_FWD_PORT` / `DR_FWD_PORT` /
  `GNMI_FWD_PORT` / `SUB_FWD_PORT` in `k8s_test_env.local`.
- **Connection reset during RPC**: the pod may not be ready. Run
  `--status` to check. Also verify no network policy blocks port-forward.
- **TLS errors**: the test clients default to insecure gRPC. If the server
  requires TLS, pass `-- -tls` (and optionally `-ca`, `-cert`, `-key`).
