# Adding a new test client

Follow these steps to add support for another service and its test client.

## Checklist

### 1. Pick a local forward port

Choose a port not already in use on the jump host. Convention: use a port
in the 40000-49999 range based on the container gRPC port
(e.g. container 50051 -> forward port 40051).

### 2. Add env variable

In `agentic-workspace/.cursor/scripts/k8s-test-client/k8s_test_env.local.example`, add:

```bash
NEW_FWD_PORT="4XXXX"        # new-service gRPC
```

In `k8s_test_env.sh`, export the new variable with a default:

```bash
export NEW_FWD_PORT="${NEW_FWD_PORT:-4XXXX}"
```

### 3. Add a case to k8s_run_test_client.sh

Add a new block in the `case "$CLIENT"` section:

```bash
  new-service)
    REPO_DIR="${WORKSPACE_ROOT}/new-service"
    MAKE_TARGET="build-test-client"    # Makefile target that builds the binary
    BINARY="bin/test-client"           # path relative to REPO_DIR
    ADDR_FLAG="-server"                # CLI flag for the address
    FWD_PORT="${NEW_FWD_PORT}"
    K8S_SVC_PORT="9001"                # K8s Service port for gRPC
    K8S_NAMESPACE="new-namespace"
    K8S_SVC_NAME="new-service"
    ;;
```

Update the `usage()` function and the error message in the `*` fallback.

### 4. Create a repo shortcut script

In the new repo, create `bin/k8s_test.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKSPACE_SCRIPTS="${SCRIPT_DIR}/../../agentic-workspace/.cursor/scripts"
source "${WORKSPACE_SCRIPTS}/k8s_test_env.sh"
exec bash "${WORKSPACE_SCRIPTS}/k8s_run_test_client.sh" --client new-service "$@"
```

Make it executable: `chmod +x bin/k8s_test.sh`.

### 5. Update SKILL.md

Add the new service to the **Service / port mapping** table.

### 6. Verify

```bash
source k8s_test_env.sh
bash k8s_run_test_client.sh --status --client new-service
bash k8s_run_test_client.sh --client new-service
```
