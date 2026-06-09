# End-to-End Application Delivery Platform CI/CD, GitOps & Bare-Metal Kubernetes Automation
A cloud-native delivery platform implementing automated CI/CD and GitOps workflows to continuously build, validate, release, and synchronize applications from source code to a bare-metal Kubernetes cluster using GitHub Actions, Argo CD, MetalLB, and Longhorn.

```
=============================================================================================================================================
                                           AUTOMATION PLANE : DEVELOPMENT, CI/CD & GITOPS LIFECYCLE LOOP
=============================================================================================================================================

 [ DEVELOPER WORKSTATION ]
         │
         │ Git Push / Pull Request
         ▼
 ┌────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
 │ REPOSITORY 1: khaledelhannat/url-shortener-app (Source Code & CI Workflows)                                                            │
 └───────┬────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
         │
         ├─► Triggers: .github/workflows/quality_gate_pipeline.yml
         │   │
         │   ▼ [ Ephemeral Test Environment ]
         │   ┌────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
         │   │ GitHub Actions Runner (ubuntu-latest)                                                                                      │
         │   │  ├─► docker compose up -d (API + Redis + PostgreSQL)                                                                       │
         │   │  ├─► Health Check Loop: curl -f http://localhost:8000/health (Up to 30 attempts)                                           │
         │   │  ├─► Test Execution: python ci_smoke_tests.py (Validates endpoint behavior)                                                │
         │   │  └─► Cleanup: docker compose down -v (Deterministic sandbox destruction)                                                   │
         │   └────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
         │
         └─► On Success ──► Triggers: .github/workflows/release_pipeline.yml
             │
             ├──► Job 1: docker_ops (Artifact Compilation)
             │    ├─► docker login (Authenticated via DOCKER_USERNAME/DOCKER_PASSWORD secrets)                                            │
             │    └─► docker build & push ──► [ DOCKER HUB REGISTRY ]                                                                     │
             │                                 ├─► khaledelhannat/url-shortener-api:latest                                                │
             │                                 └─► khaledelhannat/url-shortener-api:${{ github.sha }} (Immutable Hash)                    │
             │                                                                                                                            │
             └──► Job 2: update_infra_manifest (Manifest Mutation)                                                                        │
                  ├─► Checkout REPOSITORY 2 (url-shortener-infra) via Git Personal Access Token (INFRA_REPO_PAT)                          │
                  ├─► Execute: yq -i '.spec.template.spec.containers[0].image = "url-shortener-api:${{ github.sha }}"'                    │
                  │   Targeting File: environments/dev/app/deployment.yaml                                                                │
                  └─► git commit & push ("chore: bump api image version... [skip ci]") back to Repo 2 main branch                         │
                                                              │
                                                              │
 ┌────────────────────────────────────────────────────────────┴───────────────────────────────────────────────────────────────────────────┐
 │ REPOSITORY 2: khaledelhannat/url-shortener-infra (Declarative Environment State Specs)                                                 │
 └────────────────────────────────────────────┬───────────────────────────────────────────────────────────────────────────────────────────┘
                                              │
                                              │ Continuous Out-of-Sync Polling Loop
                                              ▼
 ┌────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
 │ ARGOCD CONTROL PLANE (Namespace: argocd)                                                                                               │
 │  ├─► argocd-application-controller-0  : Evaluates cluster live state vs. REPOSITORY 2 manifests                                        │
 │  ├─► argocd-repo-server               : Indexes, parses, and caches YAML files from the tracking path                                  │
 │  ├─► argocd-redis                     : In-memory cache optimized to reduce remote API threshold limits                                │
 │  └─► CRD Tracking Manifest            : application.yaml (Targeting: url-shortener-dev | Status: Synced / Healthy)                     │
 └────────────────────────────────────────────┬───────────────────────────────────────────────────────────────────────────────────────────┘
                                              │
                                              │ Enforces Declarative State (RollingUpdate Execution)
                                              ▼
=============================================================================================================================================
                                           RUNTIME PLANE : BARE-METAL KUBERNETES TOPOGRAPHY
=============================================================================================================================================

 [ NORTHBOUND TRAFFIC ENTRY POINT ]
                 │
                 ▼ Client Requests (HTTP/HTTPS)
 ┌────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
 │ NETWORK INGRESS TIER (Namespace: ingress-nginx)                                                                                        │
 │  ├─► MetalLB LoadBalancer VIP : 192.168.141.241 (Layer 2 ARP Leader Election | Address Pool: 192.168.141.240-192.168.141.250)          │
 │  └─► Ingress Controller Pod   : ingress-nginx-controller (Binds to Port 80:30145 and Port 443:32200)                                   │
 └────────────────────────────────────────────┬───────────────────────────────────────────────────────────────────────────────────────────┘
                                              │
                                              │ Evaluates Resource Object: url-shortener-ingress
                                              │ Match Criteria: path: /api(/|$)(.*) (ImplementationSpecific)
                                              │ Target Annotation: nginx.ingress.kubernetes.io/rewrite-target: /$2
                                              ▼
 ┌────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
 │ CORE WORKLOAD ENVIRONMENT (Namespace: url-shortener-api)                                                                               │
 │                                                                                                                                        │
 │   ┌────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐   │
 │   │ INTERNAL SERVICE ROUTING LAYER                                                                                                 │   │
 │   │  ├─► url-shortener-api-service (ClusterIP: 10.103.111.45) ──► Targets Internal Container Port: 8000                            │   │
 │   │  ├─► redis-service             (ClusterIP: 10.106.184.212) ──► Targets Internal Container Port: 6379                           │   │
 │   │  └─► postgres-service          (ClusterIP: None - Headless)──► Targets Stateful Network Identity Port: 5432                    │   │
 │   └──────────────────────────┬─────────────────────────────────┬───────────────────────────────────┬───────────────────────────────┘   │
 │                              │                                 │                                   │                                   │
 │                              ▼ Load-Balanced Stream            ▼ Cache Lookups                     ▼ Relational Transactions           │
 │   ┌───────────────────────────────────────────────────────┐ ┌─────────────────────────────┐ ┌──────────────────────────────────────┐   │
 │   │ STATELESS COMPUTE WORKLOADS                           │ │ TRANSIENT CACHING WORKLOAD  │ │ STATEFUL WORKLOAD                    │   │
 │   │  Deployment: url-shortener-api-deployment             │ │ Deployment: redis-deployment│ │ StatefulSet: postgres-statefulset    │   │
 │   │  Replicas: 2 (Multi-Node Availability)                │ │ Replicas: 1                 │ │ Replicas: 1                          │   │
 │   │  Strategy: RollingUpdate (MaxSurge: 25%)              │ │ Target Image: redis:7       │ │ Target Image: postgres:15            │   │
 │   │                                                       │ │                             │ │                                      │   │
 │   │  ┌──────────────────────┐   ┌──────────────────────┐  │ │ ┌─────────────────────────┐ │ │ ┌──────────────────────────────────┐ │   │
 │   │  │ Pod: url-shortener-01│   │ Pod: url-shortener-02│  │ │ │ Pod: redis-cache-01     │ │ │ │ Pod: postgres-0                  │ │   │
 │   │  │ QoS: Burstable       │   │ QoS: Burstable       │  │ │ │ Probes: tcpSocket:6379│ │ │ │ │ Access Mode: ReadWriteOnce (RWO) │ │   │
 │   │  │ Port: 8000           │   │ Port: 8000           │  │ │ └─────────────────────────┘ │ │ └───────────────┬──────────────────┘ │   │
 │   │  │ Probes: /health      │   │ Probes: /health      │  │ └─────────────────────────────┘ └─────────────────┼────────────────────┘   │
 │   │  └──────────────────────┘   └──────────────────────┘  │                                                   │                        │
 │   └───────────────────────────────────────────────────────┘                                                   │ VolumeClaimTemplate    │
 │                                                                                                               ▼                        │
 │   ┌────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐   │
 │   │ DISTRIBUTED STORAGE LAYER                                                                                                      │   │
 │   │  ├─► PVC: postgres-storage-postgres-0 (Status: Bound | Requested Capacity: 1Gi)                                                │   │
 │   │  ├─► PV : pvc-dc6ef8c2-79e8-4d4e-acea-e4b10d1b7b4f (Dynamic Allocation)                                                        │   │
 │   │  └─► StorageClass: longhorn (Provisioner: driver.longhorn.io | Reclaim: Delete | Binding: Immediate | AllowExpansion: true)    │   │
 │   └───────────────────────────────────────────────────────┬────────────────────────────────────────────────────────────────────────┘   │
 └───────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────────────────┘
                                                             │
                                                             ▼ Synchronous Volume Chunk Replication
 ┌────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
 │ UNDERLYING BARE-METAL INFRASTRUCTURE TOPOGRAPHY (Hardware Compute Base)                                                                │
 │  ┌────────────────────────┐  ┌────────────────────────┐  ┌────────────────────────┐  ┌────────────────────────┐                        │
 │  │ Node 1: k8s-master     │  │ Node 2: k8s-worker1    │  │ Node 3: k8s-worker2    │  │ Node 4: k8s-worker3    │                        │
 │  │ Role: Control Plane    │  │ Role: Worker Engine    │  │ Role: Worker Engine    │  │ Role: Worker Engine    │                        │
 │  │ OS: CentOS Stream 9    │  │ Storage Replica Chunk  │  │ Storage Replica Chunk  │  │ Storage Replica Chunk  │                        │
 │  └────────────────────────┘  └────────────────────────┘  └────────────────────────┘  └────────────────────────┘                        │
 └────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```
## Platform Overview & Technical Stack

A quick look at the core design patterns, tools, and structural decisions powering the platform.

### Core Capabilities
* **Zero-Downtime Rollouts:** Managed via `RollingUpdate` strategies paired with HTTP health probes.
* **Automated Quality Gates:** Pre-merge verification using Docker Compose sandboxes in GitHub Actions.
* **Declarative GitOps:** Automated drift correction and synchronization orchestrated via ArgoCD.
* **Replicated Storage:** High-availability block storage dynamically provisioned and mirrored by Longhorn.
* **Cloud-Agnostic Ingress:** Native L2 load-balancing via MetalLB and Nginx Ingress (Zero vendor lock-in).

### Technology Stack
* **Compute & OS:** Kubernetes, Containerd, CentOS Stream 9
* **Networking & Edge:** MetalLB (L2 Mode), Nginx Ingress, Flannel CNI
* **Persistence & Caching:** PostgreSQL, Redis (In-Memory Ephemeral)
* **Storage Engine:** Longhorn Distributed Block Storage
* **CI/CD Automation:** GitHub Actions, ArgoCD, Docker, `yq`

### Strategic Architecture Decisions
* **Decoupled Dual-Repo:** Isolates application business logic from environment infrastructure manifests.
* **Pull-Based Delivery:** ArgoCD pulls state configurations securely without exposing cluster API keys to CI.
* **Bare-Metal First:** Software-defined layers ensure the identical stack runs on local hardware or any public cloud.

## Phase 1: Core Kubernetes Cluster & Compute Topology

This phase establishes the foundational compute layer. No high-level storage providers, networking overlays, load balancers, or GitOps controllers can be initialized until the underlying compute nodes match these exact parameters and display a unified `Ready` status.

### 1.1 Cluster Architecture & Node Matrix

The cluster operates on a 4-node bare-metal/VM architecture orchestrated by Kubernetes **v1.30.14**. The node fleet utilizes CentOS Stream 9 as the base operating system with homogeneous Linux kernels, running an intentionally captured snapshot of minor container runtime variations across the infrastructure.

| Hostname | Role | Internal IP | External IP | Operating System | Kernel Version | Container Runtime |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `k8s-master` | Control Plane | `192.168.141.10` | `<none>` | CentOS Stream 9 | `5.14.0-661.el9.x86_64` | `containerd://2.2.3` |
| `k8s-worker1` | Worker | `192.168.141.11` | `<none>` | CentOS Stream 9 | `5.14.0-661.el9.x86_64` | `containerd://2.2.2` |
| `k8s-worker2` | Worker | `192.168.141.12` | `<none>` | CentOS Stream 9 | `5.14.0-661.el9.x86_64` | `containerd://2.2.2` |
| `k8s-worker3` | Worker | `192.168.141.13` | `<none>` | CentOS Stream 9 | `5.14.0-661.el9.x86_64` | `containerd://2.2.3` |

#### Compute Topology Blueprint
<p align="center">
  <img 
    src="https://github.com/user-attachments/assets/1f4d2ac5-f690-4e18-bbf8-5375a2ea0f3f"
    alt="Architecture"
    width="700"
  />
</p>

```
[ Physical L2 Network Subnet: 192.168.141.0/24 ]
 ├── k8s-master   (192.168.141.10) -> [Control Plane] (containerd v2.2.3)
 ├── k8s-worker1  (192.168.141.11) -> [Worker Node]  (containerd v2.2.2)
 ├── k8s-worker2  (192.168.141.12) -> [Worker Node]  (containerd v2.2.2)
 └── k8s-worker3  (192.168.141.13) -> [Worker Node]  (containerd v2.2.3)
```
#### Execution & Validation
To verify node registration, health status, and runtime strings across the compute fleet, execute:

```
kubectl get nodes -o wide
```
<p align="center">
  <img 
    src="https://github.com/user-attachments/assets/ef3ea9b4-f02b-4fab-a127-2ff4334d8dcf"
    alt="Architecture"
    width="900"
  />
</p>

### 1.2 Core Control Plane State
The cluster control plane is managed via static pods bootstrapped by `kubeadm`. These control workloads execute exclusively on the master node (`192.168.141.10`) within the `kube-system` namespace.
- **Distributed Datastore:** `etcd-k8s-master` (manages cluster state consistency)
- **API Entrypoint:** `kube-apiserver-k8s-master` (exposes the Kubernetes control interface)
- **State Reconcilers:** `kube-controller-manager-k8s-master` and `kube-scheduler-k8s-master`

#### Execution & Validation
To confirm the operational uptime and isolation of the static control plane components, execute:

```
kubectl get pods -n kube-system | grep master
```
<p align="center">
  <img 
    src="https://github.com/user-attachments/assets/9bc398e3-0db5-4b06-8760-d9fde2204a5a"
    alt="Architecture"
    width="900"
  />
</p>

### 1.3 Container Network Interface (CNI) Fabric
Network encapsulation and pod-to-pod routing fabrics are driven by Calico, deployed via the declarative operator lifecycle model.
- **Lifecycle Manager:** `tigera-operator` (Namespace: `tigera-operator`)
- **Control Sync Engine:** `calico-kube-controllers` (Namespace: `kube-system`)
- **Data Plane Daemons:** `calico-node` (DaemonSet running natively on host network contexts across all 4 nodes)

#### CNI Component Deployment Tree
```
kube-system/
 ├── calico-kube-controllers-6df7596dbd-rj7jb
 ├── calico-node-4dtlc  (Scheduled: k8s-master)
 ├── calico-node-chx4g  (Scheduled: k8s-worker1)
 ├── calico-node-skbs8  (Scheduled: k8s-worker2)
 └── calico-node-n74pz  (Scheduled: k8s-worker3)
```

#### Execution & Validation
To evaluate cross-node CNI agent health and verify internal pod IP allocations from the Calico IPAM pool, execute:
```
kubectl get pods -n kube-system -o wide | grep calico
```
<p align="center">
  <img 
    src="https://github.com/user-attachments/assets/246e7b60-3b59-4cbc-bbe2-3b7d009273a0"
    alt="Architecture"
    width="900"
  />
</p>


## Phase 2: Core Networking & Load Balancing (MetalLB Integration)

This phase establishes the bare-metal load-balancing tier for the cluster network. Because standard Kubernetes clusters running on virtualized or bare-metal nodes do not ship with an integrated out-of-the-box `LoadBalancer` implementation, **MetalLB** is deployed to govern network routing and provision external IP addresses for northbound cluster ingress.

---

### 2.1 MetalLB Load Balancer Architecture

MetalLB operates natively within the cluster to handle external service routing. For this infrastructure, it is configured in **Layer 2 Mode (Data-Link Layer)**. 

#### Operational Mechanics
* **Traffic Routing:** In Layer 2 mode, one node in the cluster elects itself as the primary leader to handle traffic for an allocated external IP address. It answers all local incoming ARP (Address Resolution Protocol) requests, mapping the virtual load balancer IP to its own physical MAC address.
* **Failover Behavior:** If the leader node hosting an external IP goes offline, Kubernetes detects the node failure, and MetalLB automatically re-elects a surviving worker node to take over the IP, broadcasting a gratuitous ARP to update the local network switch interfaces within seconds.

#### Traffic Flow Blueprint
<p align="center">
  <img 
    src="https://github.com/user-attachments/assets/8699c9c9-3364-4004-8de2-50bbb7d105b9"
    alt="Architecture"
    width="600"
  />
</p>

### 2.2 Network Pool Configuration
The external IP address allocations are strictly bounded to a designated slice of the primary network subnet (`192.168.141.0/24`). This configuration is declared using two primary CRDs inside the `metallb-system` namespace.

#### 1. IP Address Pool (`IPAddressPool`)
Defines the exact explicit ranges of network addresses that MetalLB is authorized to allocate to Kubernetes services requesting a load balancer.

#### 2. Layer 2 Advertisement (`L2Advertisement`)
Instructs MetalLB to advertise the defined pool using standard Layer 2 ARP mechanics across the cluster's physical interfaces.

#### Core Configuration Manifests
```YAML
apiVersion: metallb.io/v1beta1
kind: IPAddressPool
metadata:
  name: metallb-pool
  namespace: metallb-system
spec:
  addresses:
    - 192.168.141.240-192.168.141.250
---
apiVersion: metallb.io/v1beta1
kind: L2Advertisement
metadata:
  name: metallb-l2
  namespace: metallb-system
```

### 2.3 LoadBalancer Service Binding
The primary consumer of the MetalLB network pool is the Nginx Ingress Controller. Upon creation, the Ingress Controller service requests a load balancer IP, and MetalLB assigns the next available address from the `metallb-pool`.

#### Allocated Address Map
- **Service Targeted:** `ingress-nginx-controller`
- **Assigned External IP:** `192.168.141.241`
- **Port Bindings:** Exposes Port `80` (mapped to node target port `30145`) and Port `443` (mapped to node target port `32200`).

#### Execution & Validation
To verify that the Ingress Service has successfully transitioned out of a <pending> state and bound directly to the MetalLB assigned external IP, execute the following validation commands:

```
kubectl get svc ingress-nginx-controller -n ingress-nginx
```
<p align="center">
  <img 
    src="https://github.com/user-attachments/assets/4a2bc4da-fe4c-48dc-bf6d-19d5d3c41db9"
    alt="Architecture"
    width="900"
  />
</p>


```
# Comprehensive verification of all services within the ingress namespace
kubectl get svc -n ingress-nginx
```
<p align="center">
  <img 
    src="https://github.com/user-attachments/assets/8d11f86e-eee9-469a-8ae4-4e3f16882681"
    alt="Architecture"
    width="900"
  />
</p>

## Phase 3: Storage Engine & Persistence (Longhorn Integration)

This phase establishes the persistent data layer of the cluster. To maintain state for stateful applications, the cluster utilizes **Longhorn**, a highly available, distributed block storage system designed specifically for Kubernetes. 

---

### 3.1 StorageClass Specifications

Longhorn abstracts local node storage disks into a unified, resilient pool and exposes it via a cluster-wide `StorageClass`. This class serves as the default storage engine, enabling automated volume provisioning without manual administrative intervention.

#### Core Storage Parameters
* **Provisioner:** `driver.longhorn.io` (handles volume lifecycle events like creation, attachment, and deletion).
* **Volume Binding Mode:** `Immediate` (volumes are provisioned instantly when a PersistentVolumeClaim is observed, rather than waiting for pod scheduling decisions).
* **Volume Expansion:** `true` (supports live volume resizing without unmounting or terminating active workloads).
* **Reclaim Policy:** `Delete` (underlying block storage devices are automatically wiped and reclaimed when their corresponding PersistentVolumeClaim is explicitly deleted).

#### Execution & Validation
To inspect the current parameters, expansion configurations, and default markers of the storage fabric, execute:
```
kubectl get storageclass
```
<p align="center">
  <img 
    src="https://github.com/user-attachments/assets/39b68809-ade9-4257-8671-f8faa4c581e9"
    alt="Architecture"
    width="900"
  />
</p>

### 3.2 Dynamic Storage Provisioning Mechanics
The primary consumer of the Longhorn storage fabric is PostgreSQL, deployed as a `StatefulSet`. Instead of manually declaring a `PersistentVolume` (PV), the engine utilizes a `volumeClaimTemplates` block inside the workload manifest.

#### Lifecycle of the Database Volume
1. The Template Trigger: When the `StatefulSet` initializes the `postgres-0` pod, the controller processes the template named `postgres-storage`.
2. Automated Naming: It automatically requests a PVC matching the exact naming standard: `<template-name>-<pod-name>` (`postgres-storage-postgres-0`).
3. Engine Allocation: Longhorn intercepts the request, provisions an isolated block device matching the required capacity, creates a matching cluster `PersistentVolume` object, and firmly transitions the status to `Bound`.

Storage Topology Blueprint
<p align="center">
  <img 
    src="https://github.com/user-attachments/assets/05c3ad68-e634-4e2b-8bb5-e1100327e5ef"
    alt="Architecture"
    width="600"
  />
</p>

### 3.3 Persistence State Verification
The database volume operates under strict ReadWriteOnce (RWO) access constraints, ensuring that only a single node can mount and execute write paths to the persistent volume at any given moment.

#### Active Volume Metadata
- **Target PVC Name:** `postgres-storage-postgres-0`
- **Target Namespace:** `url-shortener-api`
- **Assigned Unique Volume ID:** `pvc-dc6ef8c2-79e8-4d4e-acea-e4b10d1b7b4f`
- **Requested Storage Capacity:** `1Gi`

#### Execution & Validation
To confirm that the database persistence volume has successfully bound to Longhorn and is actively attached to the workload, execute:
```
kubectl get pvc -n url-shortener-api
```
<p align="center">
  <img 
    src="https://github.com/user-attachments/assets/223d3419-f50e-4ea7-8364-48fe1e50c815"
    alt="Architecture"
    width="900"
  />
</p>

## Phase 4: Core Application Stack & Deployment Layer

This phase details the runtime deployment profiles, container life-cycle settings, resource allocations, and internal service discovery mechanisms governing the core application layer. This section covers the stateless API application controllers and the transient caching tier.

---

### 4.1 API Application Architecture (`url-shortener-api`)

The primary backend service is engineered as an isolated, stateless microservice. It handles business logic, URL redirection rules, database mutations, and cache interactions.

#### 1. Replica Strategy & High Availability
To ensure continuous availability during system upgrades and node disruptions, the service is managed by a standard `Deployment` controller enforcing an absolute multi-instance state.

* **Target Replica Count:** `2` (statically scaled across available worker nodes).
* **Strategy Type:** `RollingUpdate`
* **Rolling Adjustments:** Configured with `maxSurge: 25%` and `maxUnavailable: 25%`. This ensures that during a rolling code deployment, a minimum of 2 healthy instances remain online at all times while capping the maximum transient container footprint at 3 instances.
* **Graceful Termination:** `terminationGracePeriodSeconds: 20`. Allows active HTTP requests to drain safely from the worker network stream before the pod receives a final `SIGKILL` signal.

#### 2. Compute Resource Constraints & Quality of Service (QoS)
To prevent rogue compute loops or memory leaks from degrading competing infrastructure elements, the workload runs under strict cgroup control limits, qualifying it for a **Burstable** Quality of Service class.

| Resource Type | Request Allocation | Hard Limit Boundary |
| :--- | :--- | :--- |
| **CPU** | `50m` (0.05 cores) | `200m` (0.20 cores) |
| **Memory** | `64Mi` | `256Mi` |

#### 3. Application Health & Probes
The container implements an isolated three-tier probe hierarchy targeting the internal `/health` HTTP endpoint on container port `8000` to prevent deadlocked or uninitialized workloads from serving live traffic.

```
[ Pod Initialization ]
          │
          ▼
┌──────────────────────────┐
│ Startup Probe            │ ──► Success ──► [ Drops into Lifecycle Loop ]
│ Max Window: 150 seconds  │
└──────────────────────────┘
          │
          ▼ Ongoing Lifecycle Loop
┌──────────────────────────────────┐         ┌──────────────────────────────────┐
│ Liveness Probe                   │         │ Readiness Probe                  │
│ Period: 10s | Timeout: 5s        │         │ Period: 10s | Timeout: 2s        │
│ Action: Restarts stuck container │         │ Action: Pulls Pod from Service   │
└──────────────────────────────────┘         └──────────────────────────────────┘
```
- **Startup Probe:** Evaluates slower external startup overheads (such as cold database pool initializations). Runs every `5s` with a `failureThreshold: 30`, giving the runtime up to 150 seconds to pass its initial state check before the controller triggers a restart loop.
- **Liveness Probe:** Monitored continuously every `10s`. If `3` consecutive HTTP checks timeout or return status codes `≥ 400`, the kubelet terminates and reinitializes the container.
- **Readiness Probe:** Monitored continuously every `10s` with a strict `2s` timeout. If it encounters failures, the endpoint controller strips the specific pod IP from the cluster load balancer, preventing client traffic from routing to a malfunctioning pod instance.

#### Execution & Validation
To inspect deployment rollout health, replica numbers, and active container statuses, execute:

```
kubectl get deployment url-shortener-api-deployment -n url-shortener-api -o
```
<p align="center">
  <img 
    src="https://github.com/user-attachments/assets/cbc3fbda-1cb1-44aa-ad9b-9d5d31d0672e"
    alt="Architecture"
    width="900"
  />
</p>

### 4.2 Caching Tier Architecture (redis-deployment)
High-speed transactional caching and rate-limiting states are handled via an in-memory Redis layer. Because this cache state is ephemeral and fully reconstructible by the API, it is deployed as a single-replica stateless Deployment without underlying longhorn persistence mounts.

#### Caching Resource Profile
- **Container Core Image:** `redis:7`
- **Target Replica Count:** `1`
- **Resource Limits:** Requests allocated at `50m` CPU / `60Mi` Memory; Hard limits capped at `100m` CPU / `120Mi` Memory.
- **Health Tracking:** Utilizes native `tcpSocket` verification targeting port `6379`. The readiness probe initializes quickly (`initialDelaySeconds: 3`) to ensure the cache pool is fully online before the API attempts backend connection handshakes.

#### Execution & Validation
To verify the performance constraints and stability of the caching instance, execute:
```
kubectl get pods -n url-shortener-api -l app=redis,tier=cache
```
<p align="center">
  <img 
    src="https://github.com/user-attachments/assets/52736d00-3bfb-46cd-85fe-99522daf1620"
    alt="Architecture"
    width="900"
  />
</p>

### 4.3 Internal Service Discovery Layer
To decouple the communication paths between the API layer, the caching layer, and the relational database, the cluster implements internal CoreDNS routing maps via abstraction `Service` definitions.

<p align="center">
  <img 
    src="https://github.com/user-attachments/assets/cdb767fd-1e1d-40c3-9a70-7c09552033a2"
    alt="Architecture"
    width="900"
  />
</p>

1. **API Internal Entry Point** (`url-shortener-api-service`)
- **Type:** `ClusterIP` (Internal Virtual IP allocation)
- **Port Mapping:** Exposes port `8000` internally, passing target streams straight to container port `8000`.
- **Label Selectors Bound:** `app: url-shortener-api, tier: backend`.
- **Internal DNS Address:** `url-shortener-api-service.url-shortener-api.svc.cluster.local`

2. **Cache Discovery Point** (`redis-service`)
**Type:** `ClusterIP`
**Port Mapping:** Exposes port `6379` internally, matching the Redis container port configuration.
**Label Selectors Bound:** `app: redis`, `tier: cache`.
**Internal DNS Address:** `redis-service.url-shortener-api.svc.cluster.local`

#### Execution & Validation
To extract the cluster virtual IPs and check the target ports assigned to internal network endpoints, execute:
```
kubectl get svc -n url-shortener-api
```
<p align="center">
  <img 
    src="https://github.com/user-attachments/assets/825a86b4-c4b9-4ecc-bf8a-09f0f6b42d85"
    alt="Architecture"
    width="900"
  />
</p>



## Phase 5: Ingress Traffic Control & Edge Routing

This phase governs northbound edge routing and external traffic ingress. It outlines how the application securely exposes its API entry points to the local subnet using an enterprise-grade Ingress Controller combined with advanced regular expression (Regex) URI rewriting.

---

### 5.1 Ingress Routing Architecture

Edge traffic control is driven by the **Ingress-Nginx Controller**. The resource explicitly requests processing by the Nginx data plane via the `ingressClassName` field.

#### Network Ingress Integration
* **Controller Assignment:** `ingressClassName: nginx`
* **Address Mapping:** The controller interacts dynamically with the load-balancing tier established in Phase 2. The Ingress resource automatically inherits and binds to the controller's allocated External IP address: `192.168.141.241`.
* **ArgoCD Lifecycle Tracking:** The manifest includes live metadata tracking hooks (`argocd.argoproj.io/tracking-id`), confirming that its actual live-state loop is actively driven by the GitOps engine.

#### Ingress Traffic Flow Diagram
<p align="center">
  <img 
    src="https://github.com/user-attachments/assets/8bc0867f-ba83-4081-ae7e-e9b41bfa4e7b"
    alt="Architecture"
    width="600"
  />
</p>

### 5.2 Regex Path Parsing & Rewrite Mechanics
To isolate api endpoints from client applications while maintaining standard, clean route handling within the container, the Ingress resource implements deep path matching and traffic manipulation annotations.

#### Routing Directives
- **Path Regex Specification:** `/api(/|$)(.*)`
- **Path Match Type:** `ImplementationSpecific`
- **Rewrite Strategy:** `nginx.ingress.kubernetes.io/rewrite-target: /$2`

#### Request Transformation Matrix
The rewrite engine splits incoming paths into captured variables. The second match group `(.*)` is extracted and rewritten as the final target endpoint passed to the container layer:
|Incoming Client URL                  |Regex Evaluation           |Internal Target Path|Upstream Port|
|-------------------------------------|---------------------------|--------------------|-------------|
|http://192.168.141.241/api           |Matches boundary condition |/                   |8000         |
|http://192.168.141.241/api/          |Matches trailing slash     |/                   |8000         |
|http://192.168.141.241/api/health    |Group 2 extracts health    |/health             |8000         |
|http://192.168.141.241/api/v1/shorten|Group 2 extracts v1/shorten|/v1/shorten         |8000         |

### 5.3 Target Upstream Specifications
Once paths are successfully decoupled and parsed by Nginx, the controller targets the internal routing abstraction layer within the core namespace.
- **Upstream Cluster Service:** `url-shortener-api-service`
- **Target Container Port:** `8000`
- **Namespace Boundary:** `url-shortener-api`

### 5.4 Ingress State Verification
#### Execution & Validation
To extract the complete runtime operational state, tracking configurations, and verified load-balancer status from the cluster edge, execute:

```
kubectl get ingress url-shortener-ingress -n url-shortener-api -o yaml
```
<p align="center">
  <img 
    src="https://github.com/user-attachments/assets/80712133-04f0-4509-a38c-c2428960691b"
    alt="Architecture"
    width="600"
  />
</p>

## Phase 6: GitOps Controller & ArgoCD Orchestration

This phase details the continuous delivery engine driving the automated reconciliation of infrastructure states. The cluster implements a **Pull-Based GitOps Model** orchestrated via ArgoCD, ensuring that the live cluster state continuously matches the declarative manifests stored in the remote infrastructure repository.

---

### 6.1 ArgoCD Core Infrastructure

The ArgoCD control plane runs inside the isolated `argocd` namespace. It functions as an in-cluster operator that continuously monitors Git repositories, compares desired states against live cluster configurations, and automatically corrects configuration drift.

#### Core Control Plane Workloads
The following system components drive the GitOps lifecycle:
* **`argocd-application-controller`:** The core state engine. It parses active custom resources (`Application`) and interacts directly with the cluster API server to apply manifests.
* **`argocd-repo-server`:** Maintains a local cache of the remote Git repository, indexing and generating raw Kubernetes manifests from the tracking branch.
* **`argocd-server`:** Exposes the API endpoint and underlying web user interface for administrative control and visualization.
* **`argocd-redis`:** Provides a high-speed caching engine for configuration states, reducing API calls to both GitHub and the cluster control plane.

#### Execution & Validation
To confirm that the entire GitOps control plane is operational and processing cluster events smoothly, execute:
```
kubectl get pods -n argocd
```
<p align="center">
  <img 
    src="https://github.com/user-attachments/assets/4396e8d9-eea6-4f4a-ae15-93c516af170f"
    alt="Architecture"
    width="900"
  />
</p>

### 6.2 Declarative Application Definition (`url-shortener-dev`)
The GitOps delivery pipeline is managed via an explicit custom resource definition (`Application`). This resource links the live cluster namespaces directly to the tracking path inside the Git environment.

#### Target Mapping Specs
- **Application Target Name:** `url-shortener-dev`
- **Source Repository:** `https://github.com/khaledelhannat/url-shortener-infra.git`
- **Target Management Path:** `environments/dev/`
- **Tracking Branch:** main
- **Destination Cluster Endpoint:** `https://kubernetes.default.svc` (Local Target Cluster)
- **Destination Working Namespace:** `url-shortener-api`

#### The GitOps Reconciliation Loop
<p align="center">
  <img 
    src="https://github.com/user-attachments/assets/c2550b58-a3c6-470e-8b37-658ce862cd4c"
    alt="Architecture"
    width="600"
  />
</p>


### 6.3 State Synchronization & Verification
ArgoCD continuously calculates structural checksums of the manifests in Git against the running pods, services, and ingress rules inside the `url-shortener-api` namespace.

- **Sync Status** (`Synced`): Indicates that the live cluster manifests match the configuration files stored on the `main` branch of the infrastructure repository.
- **Health Status** (`Healthy`): Indicates that all resource controllers managed by this application (Deployments, StatefulSets) have successfully spun up their replicas and passed all configured readiness and liveness probes.

**Execution & Validation**
To evaluate the top-level deployment tracking state and ensure that no configuration drift has left the cluster in an un-synchronized loop, execute:
```
kubectl get application -n argocd
```
<p align="center">
  <img 
    src="https://github.com/user-attachments/assets/eb90056b-1b41-4ab0-bbc5-efc17759464f"
    alt="Architecture"
    width="900"
  />
</p>

## Phase 7: Application CI/CD Pipeline Automation

This phase establishes the automation loop connecting the application source code repository directly to the GitOps deployment engine. By decoupling the application code from the infrastructure configurations, the system implements a dual-repository structure that guarantees automated testing, container building, and declarative version bumping.

---

### 7.1 Dual-Repository Topography

The platform is strictly organized into two separate Git repositories to decouple developer feature rollouts from core infrastructure management.

```
  [ Developer Push / PR ]
            │
            ▼
┌───────────────────────────────┐
│ khaledelhannat/               │
│ url-shortener-app             │ ──► Triggers CI Validation & Build
└───────────────┬───────────────┘
                │
                │ Pushes updated image tag via 'yq'
                ▼
┌───────────────────────────────┐
│ khaledelhannat/               │
│ url-shortener-infra           │ ──► Intercepted by ArgoCD (Phase 6)
└───────────────────────────────┘
```

1. Application Repository Tree (`url-shortener-app`)
Contains the application business logic, local integration configs, smoke testing frameworks, and GitHub Actions orchestration pipelines.

<p align="center">
  <img 
    src="https://github.com/user-attachments/assets/dc946cc9-c981-4700-a180-eba0c4b79684"
    alt="Architecture"
    width="300"
  />
</p>

2. Infrastructure Repository Tree (`url-shortener-infra`)
Contains the explicit, declarative Kubernetes manifests tracked and synchronized by the ArgoCD controller.

<p align="center">
  <img 
    src="https://github.com/user-attachments/assets/b3aa2e21-ea64-43a9-8f8a-b8a87f15d0fe"
    alt="Architecture"
    width="300"
  />
</p>

### 7.2 Quality Gate Pipeline (`quality_gate_pipeline.yml`)
The Quality Gate represents the code-validation boundary. It guarantees that no broken execution states or faulty database connection logic can be merged into the primary release path.

- **Pipeline Name:** `Quality gate pipeline (system-validation)`
- **Execution Hooks:** Triggers on any `pull_request` targeting the `main` branch, or direct `push` events altering the `app/` code, core manifests, dependencies, or validation runners.

#### Core Validation Stages
1. **Ephemeral Environment Bootstrapping:** Spin up an isolated, multi-container environment inside the GitHub runner using local configurations:
```
docker compose up -d
```
2. **Network Readiness Polling:** Executes a progressive polling loop to check the container endpoint readiness before starting tests, preventing race conditions:
```
for i in {1..30}; do curl -f http://localhost:8000/health && break sleep 2; done
```
3. **Smoke Test Execution:** Installs verification dependencies and triggers `ci_smoke_tests.py` against the local endpoint to assert API compliance.
4. **Deterministic Teardown:** Automatically tears down docker resources and purges anonymous testing storage volumes (`docker compose down -v`), ensuring complete execution isolation.

#### Execution & Validation
<p align="center">
  <img 
    src="https://github.com/user-attachments/assets/17e09255-e3eb-43ee-9721-fa1a7821d042"
    alt="Architecture"
    width="900"
  />
</p>


### 7.3 Release & Manifest Delivery Pipeline (`release_pipeline.yml`)
The Release Pipeline acts as the secure automation bridge. It triggers only after verification checks pass, safely packaging the code and updating the deployment state.

- **Pipeline Name:** `Release pipeline (build + push)`
- **Orchestration Hook:** `workflow_run` targeting the successful completion of the `Quality gate pipeline (system-validation)`.

#### Operational Jobs & Tasks
**Job 1:** `docker_ops` (Artifact Compilation)
- **Authentication:** Logs securely into Docker Hub via encrypted organization secrets (`DOCKER_USERNAME`, `DOCKER_PASSWORD`).
- **Compilation & Compounding:** Builds the production container artifact via the project `Dockerfile`.
- **Immutability Tagging:** Pushes the compiled container image to Docker Hub under two explicit tags:
1. `khaledelhannat/url-shortener-api:latest` (for general pointer references)
2. `khaledelhannat/url-shortener-api:${{ github.sha }}` (immutable git commit hash tag for precise tracking)

**Job 2:** `update_infra_manifest` (Manifest Mutation)
- **Cross-Repo Checkout:** Checks out the infrastructure repository (`url-shortener-infra`) using an authenticated Personal Access Token (`INFRA_REPO_PAT`).
- **Declarative Manifest Patching:** Employs the `yq` command-line processing engine to modify the infrastructure state file. It alters the exact image path value within the application deployment sheet to match the newly compiled SHA tag:

```
yq -i '.spec.template.spec.containers[0].image = "khaledelhannat/url-shortener-api:${{ github.sha }}"' environments/dev/app/deployment.yaml
```
- **GitOps Trigger Push:** Commits the configuration change acting as `github-actions[bot]`, applying the tag `[skip ci]` to prevent cyclical runner activations. It pushes the change directly back to the infrastructure repository's `main` branch, triggering ArgoCD to synchronize the cluster.

```
[ Docker Build Success ]
           │
           ▼
┌────────────────────────────────────────┐
│ Extract Workflow commit ${{github.sha}}│
└──────────┬─────────────────────────────┘
           │
           ▼ Patch Target Manifest via 'yq'
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ file: environments/dev/app/deployment.yaml                                             │
│ image: khaledelhannat/url-shortener-api:01af459fc80d4fa9a454cb87b86cd8d...             │
└──────────┬─────────────────────────────────────────────────────────────────────────────┘
           │
           ▼ Push to Remote Branch
┌──────────────────────────────────────┐
│ Git Commit: chore: bump api image... │ ──► Signals ArgoCD Reconciliation Loop
└──────────────────────────────────────┘
```
#### Execution & Validation
To confirm the automated pipeline interaction across both repositories, view the workflows directory structure and recent Git commit logs:
```
# Executed within the workflows workspace directory to monitor active runner files
ls -l .github/workflows/
```
<p align="center">
  <img 
    src="https://github.com/user-attachments/assets/40390e00-856f-41aa-8f7d-7086ba77631f"
    alt="Architecture"
    width="900"
  />
</p>
