<div align="right">
  <a href="./README_CN.md">中文版</a>
</div>

# Agentic AI System in Confidential Computing (Agent-CC)

---

## 🎯 Overview

Agent-CC is a **deployment architecture and reference implementation** for running agentic AI workloads on Intel Xeon processors with Intel TDX (Trust Domain Extensions): it is designed to be agnostic for agent-framework and services, and combines runtime isolation, trusted execution controls, and service-to-service trust verification as one coherent system.

Agent-CC addresses this through three interconnected pillars: 
  - **Lifecycle Data Protection** (hardware memory encryption, attestation-gated encrypted storage, immutable audit log)

  - **Build-to-Runtime Integrity** (supply chain verification connected to runtime measurements via TC API)

  - **Trusted Service Composition** (mutual attestation before sensitive data is exchanged with external services).

Agent frameworks (OpenClaw, Hermes-Agent, etc.) and their dependent services run **unmodified**.
Agent-CC introduces confidential computing through deployment-side plugins or service sidecars, requiring only minimal changes to the frameworks and services themselves. This low-intrusion, and in some cases near-zero-intrusion, approach preserves existing agent and service deployments while significantly reducing adoption cost and operational complexity. 

Confidential Computing, or Intel TDX-based deployment here, is an enabling foundation layer: it is designed to augment existing agent deployment and security mechanisms for working alongside existing sandboxing, policy enforcement, supply-chain controls, and service authorization, extending those mechanisms with hardware-rooted isolation, verifiable runtime evidence, and attestation-bound access control to collectively meet the higher security demands of confidential agent deployments.

## 🏗️ Agentic AI Architecture & Security Threats

### Agent System Architecture

AI agents operate across three functional domains:

- **Control Plane**: Gateway, orchestration, context & memory management, policy & secrets management
- **Execution Plane**: Code interpretation and tool execution (the zone requiring strongest isolation)
- **External Services**: LLM APIs, knowledge bases, tool services, and persistent stores


### Security Threats & TEE Mitigation

Recent OWASP references ([Agentic AI - Threats and Mitigations](https://genai.owasp.org/resource/agentic-ai-threats-and-mitigations/) and [OWASP Top 10 for Agentic Applications 2026](https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/)) and EU compliance analysis ([AI AGENTS UNDER EU LAW: A COMPLIANCE ARCHITECTURE FOR AI PROVIDERS](https://arxiv.org/pdf/2604.04604)) together highlight both security exposure and governance expectations for agent systems.

For deployment analysis, we summarize these concerns into six operational categories:

1. **Cognitive & Decision Integrity**: resistance to context poisoning, goal manipulation, and reasoning failure
2. **Runtime Compromise**: prevention of unsafe execution paths, tool misuse, and runtime breakout
3. **Secret & Memory Exposure**: protection against prompt, credential, and context leakage
4. **Identity & Access Trust**: strong authentication, authorization, and auditable identity binding
5. **System & Supply Chain Integrity**: build-to-runtime integrity for models, tools, dependencies, and images
6. **Untrusted Service Interaction**: secure agent-to-agent and agent-to-service communication

Category 1 is primarily AI-native. Categories 2 to 6 are deployment-facing and map directly to runtime trust architecture. In this scope, Confidential Computing, especially Intel TDX, serves as an enabling layer that strengthens containment, confidentiality, attestation, integrity, and trusted service interaction.

In practice, TD (Trust Domain) deployment provides a stronger trust foundation when combined with sandboxing, policy enforcement, signed artifacts, encryption at rest, and TLS.

| Security concern | What TD helps do directly | What it should be combined with |
| --- | --- | --- |
| Runtime Compromise | Reduces host-side exposure and strengthens isolation for control-plane and task execution | Task sandboxing, least privilege, policy enforcement, syscall filtering |
| Secret & Memory Exposure | Protects in-use memory from host, hypervisor, and operator-level inspection | Secret scoping, short-lived credentials, output filtering, data minimization |
| Identity & Access Trust | Provides hardware-backed runtime identity evidence and stronger attestation-based trust establishment | Strong authentication, IAM policy, identity binding, verifier infrastructure, key-release policy |
| System & Supply Chain Integrity | Extends trust from signed artifacts to measured boot and launch | Image signing, SBOMs, dependency governance, reproducible builds, CI/CD admission |
| Untrusted Service Interaction | Enables attested channels that verify peer identity and runtime state | TLS, service authorization, trust policy, secure session setup, key management |



## 📐 Architecture Overview

### Three Pillars of Agent-CC

Agent-CC addresses the security challenges of AI agents through a coherent architecture built on three interconnected capabilities. These three pillars work together to create a verifiable trust model from build time through runtime and across service boundaries.

Agent-CC combines confidential execution, trusted build-to-runtime continuity, and attestation-aware service access into one unified security architecture. Rather than treating TEE-based deployment as a standalone protection, Agent-CC views it as an enabling foundation that, combined with policy, isolation, verification, and secure service interaction, can materially reduce each of the five deployment-facing threat categories facing AI agents.

The following three pillars form the foundation of Agent-CC:

- **Lifecycle Data Protection**: Protects sensitive agent data across its full lifecycle—from active runtime memory through persistent storage and back to authorized access.

- **Build-to-Runtime Integrity**: Connects build-time intent (images, configuration, policy) to runtime evidence (measurements, launch state, workload binding) into a single enforceable trust chain.

- **Trusted Service Composition**: Extends trust from the local agent runtime to policy-approved external services through identity verification combined with runtime attestation evidence.

#### Lifecycle Data Protection

TD is the trust foundation for lifecycle data protection. Agent processes run inside a hardware-isolated TD where memory is encrypted by default, runtime identity and launch measurements are verified through attestation, and secrets are released only to attested environments. The same trust boundary extends to persisted data: encrypted state is decrypted only inside verified TD runtimes.

This model protects three critical data surfaces:

- **Runtime Context and Memory (Data in use)**: Active context, intermediate reasoning state, and tool outputs remain in encrypted TD memory, reducing exposure from host- or hypervisor-level observation.
- **Secrets and Permissions (Data in use)**: API keys, tokens, and credentials are provisioned through attestation-gated release, shifting the model from post-release protection to trust-before-release.
- **Long-Term Memory and Persisted Data (Data at rest)**: Stored data remains encrypted across persistence boundaries and is released only to approved runtimes that pass attestation checks.

Together, these controls provide a coherent protection path: sensitive data is encrypted by default, decrypted only inside verified TD boundaries, and shared only after trust verification succeeds.

![Full data lifecycle protection](./images/full-data-lifecycle-protection.png)

<div align="center">Figure 1: Full data lifecycle protection - OpenClaw as example</div>

#### Build-to-Runtime Integrity

In agent systems, build-time intent and deployment policy are not sufficient on their own: the system must prove what is actually running, detect runtime deviation from approved software and policy, and provide verifiable execution claims to verifiers and peer services. Through **TC API**, Agent-CC connects supply chain evidence to attested runtime state so trust decisions are enforced in execution, not only in design.


- **End-to-end trust chain**: Connects build artifacts to attested runtime execution, ensuring workloads are verified before execution.
- **Trusted build**: Produces signed artifacts with SBOM and immutable provenance for supply chain integrity.
- **Pre-execution verification**: Enforces signature and SBOM checks, then binds workload identity to attested hardware TCB evidence.
- **Trusted launch**: Runs workloads inside isolated TDVM environments with hardware-backed guarantees.
- **Attestation-driven execution**: Governs runtime execution and secret provisioning with attestation-based trust decisions.

![Build to runtime](./images/build-2-runtime.png)

<div align="center">Figure 2: From Build Artifacts to Attested Runtime</div>

## Key components

**Core Services**

[Core Services](core/README.md) implement the three architecture requirements described above:

- **[TC API](core/tc_api)**: Trusted build/publish/launch control path (for build-to-runtime verification and policy enforcement).

- **[Trusted Log (TLog)](core/tlog)**: Immutable, signed runtime evidence and audit trail.
- **Argus (Trusted Service Composition)**: Cross-service trust architecture for attested service admission and trusted interaction. Detailed design will be added in the next version.

**Adapters** 

 - **[OpenClaw](./adapters/OpenClaw/README.md)** : povides a way to independently build the openclaw-gateway image and customize relevant configurations.This allows OpenClaw to run in a secure/isolated environment, avoiding any unnecessary impact on the host machine.


