# FaultRay Phase 0 Baseline Validation Report

This report records hands-on validation of FaultRay's cloud / Kubernetes /
Terraform discovery and simulation commands against **real** external
infrastructure (i.e. not the built-in `demo` model). Each section lists the
exact commands executed, verbatim output excerpts, and a per-criterion
judgement.

Judgement legend:
- ✓ — verified, behaves as expected.
- △ — partially verified, or verified with caveats worth documenting.
- ✗ — failed / not verified.

Environment:

- Date: 2026-04-17
- Host: WSL2 (Ubuntu), Docker Desktop WSL integration enabled
- FaultRay: installed editable from `/home/user/repos/faultray`, v11.2.0
- Tools:
  - `kind v0.27.0 go1.23.6 linux/amd64`
  - `kubectl Client Version: v1.35.4`
  - `docker 29.2.0` (accessed via `sg docker -c '...'` — the active shell is
    not yet in the `docker` group)

---

## K8s Discovery (Task 2)

**Goal.** Verify that `faultray scan --k8s` discovers a real Kubernetes
topology (three Deployments + Services across a namespace), that dependencies
are inferred, and that the resulting model can be fed straight into
`faultray simulate`.

### Commands run (verbatim)

```bash
# 1. Create kind cluster (control-plane + worker)
sg docker -c "/home/user/.local/bin/kind create cluster \
    --name faultray-test \
    --config /home/user/repos/faultray/tests/fixtures/kind-config.yaml"

# 2. Deploy sample workload (3 Deployments + 3 Services in faultray-demo ns)
sg docker -c "/home/user/.local/bin/kubectl --context kind-faultray-test \
    apply -f /tmp/sample-microservices.yaml"
sg docker -c "/home/user/.local/bin/kubectl --context kind-faultray-test \
    -n faultray-demo wait --for=condition=Available --timeout=180s \
    deployment/nginx deployment/redis deployment/app"

# 3. Scan
sg docker -c "python3 -m faultray scan --k8s \
    --context kind-faultray-test --namespace faultray-demo \
    --output /tmp/k8s-topology.json"

# 4. Simulate off the scan output
python3 -m faultray simulate --model /tmp/k8s-topology.json
python3 -m faultray simulate --model /tmp/k8s-topology.json --json

# 5. Tear down
sg docker -c "/home/user/.local/bin/kind delete cluster --name faultray-test"
```

### Cluster state before scan (verbatim)

```
NAME                    READY   UP-TO-DATE   AVAILABLE   AGE
deployment.apps/app     3/3     3            3           24s
deployment.apps/nginx   2/2     2            2           24s
deployment.apps/redis   1/1     1            1           24s

NAME            TYPE        CLUSTER-IP      EXTERNAL-IP   PORT(S)    AGE
service/app     ClusterIP   10.96.61.172    <none>        8080/TCP   24s
service/nginx   ClusterIP   10.96.170.83    <none>        80/TCP     24s
service/redis   ClusterIP   10.96.221.227   <none>        6379/TCP   24s

NAME                         READY   STATUS    RESTARTS   AGE
pod/app-69f7dc54cc-2k8g4     1/1     Running   0          24s
pod/app-69f7dc54cc-bzz4b     1/1     Running   0          24s
pod/app-69f7dc54cc-d9fvs     1/1     Running   0          24s
pod/nginx-f576985cc-5zbc8    1/1     Running   0          24s
pod/nginx-f576985cc-gwwgl    1/1     Running   0          24s
pod/redis-5f86f8f9c7-f7h2v   1/1     Running   0          24s
```

Matches the spec: **3 deployments, 3 services, 6 pods** all `Running`.

### `faultray scan --k8s` output (verbatim)

```
FaultRay v11.2.0 [Free Tier - upgrade at github.com/sponsors/mattyopon]
Scanning Kubernetes cluster (context: kind-faultray-test) (namespace:
faultray-demo)...
Discovered 3 components, 2 dependencies in 0.1s
    Infrastructure Overview
┏━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━┓
┃ Metric           ┃ Value    ┃
┡━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━┩
│ Components       │ 3        │
│ Dependencies     │ 2        │
│   app_server     │ 2        │
│   database       │ 1        │
│ Resilience Score │ 88.0/100 │
└──────────────────┴──────────┘

Model saved to /tmp/k8s-topology.json
```

Exit code `0`. Model file is valid JSON; components & dependencies extracted:

```
keys: ['schema_version', 'components', 'dependencies']
components:
 - faultray-demo/app   | app_server
 - faultray-demo/nginx | app_server
 - faultray-demo/redis | database
dependencies:
 - deploy-faultray-demo-app   -> deploy-faultray-demo-redis  (requires, tcp)
 - deploy-faultray-demo-nginx -> deploy-faultray-demo-redis  (requires, tcp)
```

Note: redis was auto-classified as `database` — that's a label-heuristic from
the scanner, not something we declared in the manifest. The two inferred deps
point from the two `app_server` components to the `database`, which matches
what a heuristic "every non-DB talks to the DB" rule would produce. There is
**no** edge from nginx ↔ app, even though a real HTTP fan-out topology
typically has one; the scanner does not yet use label/selector co-location or
Service endpoint analysis to infer that. See "Notes & Phase 1 candidates"
below.

### `faultray simulate --model` output (trimmed)

```
FaultRay v11.2.0 [Free Tier - upgrade at github.com/sponsors/mattyopon]
Loading infrastructure model...
Running chaos simulation (3 components)...
Scenarios: 66 generated, 66 tested

╭────────────────────── FaultRay Chaos Simulation Report ──────────────────────╮
│ Resilience Score: 88/100                                                     │
│ Scenarios tested: 66                                                         │
│ Critical: 11  Warning: 1  Passed: 54                                         │
╰──────────────────────────────────────────────────────────────────────────────╯
```

Exit code `0`. `simulate --json` additionally emits a machine-readable payload
with `scenarios`, `resilience_score`, etc. (131-line rich output in text mode;
the cascade traces correctly model both app and nginx failing 30 s after redis
goes down, matching the inferred dependency graph).

### Judgement

| # | Criterion (from the task spec) | Verdict | Evidence |
|---|---|---|---|
| 1 | scan output is YAML/JSON parseable | ✓ | `json.load('/tmp/k8s-topology.json')` succeeds; top-level keys `schema_version`, `components`, `dependencies`. |
| 2 | 3 components (nginx, redis, app) detected | ✓ | Table shows `Components: 3`; JSON lists all three names (`faultray-demo/nginx`, `faultray-demo/redis`, `faultray-demo/app`). |
| 3 | dependencies are inferred | △ | 2 deps inferred (`app→redis`, `nginx→redis`) via DB-heuristic only. No edge inferred between `nginx` and `app`, even though both are in the same namespace and a typical nginx+app pair has one. Phase 1 candidate: use Service selector + Endpoints API to discover east/west HTTP edges. |
| 4 | completes without errors | ✓ | Exit code 0, no stderr, 0.1 s wall-clock. |
| 5 | simulate consumes scan output | ✓ | `faultray simulate --model /tmp/k8s-topology.json` finishes with exit 0, runs 66 scenarios, produces a sensible cascade (redis failure propagates to app+nginx after 30 s). `--json` mode also parses. |

### Cleanup verification

```
$ sg docker -c "/home/user/.local/bin/kind get clusters"
No kind clusters found.
```

### Notes & Phase 1 candidates

1. **East/west dependency inference is thin.** The scanner only draws edges
   into components it has labelled as `database` (heuristic on image/name).
   There is no edge `nginx → app` or `app → nginx`, even though they share a
   namespace and have exposing Services. Consider using the Endpoints API
   and/or Service.spec.selector overlap to infer HTTP-tier edges in a future
   release.
2. **Component identity is a little inconsistent.** In the rendered table
   components are listed as `faultray-demo/<name>` but dependency IDs use
   `deploy-faultray-demo-<name>`. The JSON dependency records don't carry the
   resolved component names — consumers have to re-key. Low-severity Phase 1
   polish candidate.
3. **Port `0` in inferred dependencies.** Both inferred deps have `port: 0`
   and `latency_ms: 0.0`. The scanner isn't pulling port/protocol info from
   the Service spec. That's OK for topology, but simulation accuracy would
   improve if the actual service port (`6379` for redis) were attached.

### Files produced by this task

- `tests/fixtures/kind-config.yaml` — kind cluster config (control-plane + worker, named `faultray-test`).
- `tests/integration/test_k8s_discovery.py` — pytest integration test, marked `@pytest.mark.integration`, skipped automatically if kind/docker/kubectl aren't reachable from the session. Manual verification above is the primary evidence; the test is the reproducer.
- This report section.
