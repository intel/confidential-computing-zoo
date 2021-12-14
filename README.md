# Confidential Computing Zoo

Confidential Computing Zoo (CCZoo) is an open source to provide confidential computiong
solutions based on Intel technologies below:
- Intel® Trusted Execution Environment (TEE) technology
  - Intel® Software Guard Extensions (Intel® SGX).
    Intel® SGX 1/2 offers hardware-based memory encryption that isolates specific
    application code and data in memory. Intel® SGX allows user-level code to
    allocate private regions of memory, called enclaves, which are designed to
    be protected from processes running at higher privilege levels. Only Intel®
    SGX offers such a granular level of control and protection.
    For more information, please refer to [Intel® SGX](https://www.intel.com/content/www/us/en/architecture-and-technology/software-guard-extensions.html).
  - Intel® Trust Domain Extensions (Intel® TDX).
    Intel® TDX is introducing new, architectural elements to help deploy hardware-isolated,
    virtual machines (VMs) called trust domains (TDs). Intel TDX is designed to isolate
    VMs from the virtual-machine manager (VMM)/hypervisor and any other non-TD software
    on the platform to protect TDs from a broad range of software. For more infermation,
    please refer to [Intel® TDX](https://www.intel.com/content/www/us/en/developer/articles/technical/intel-trust-domain-extensions.html).
- Intel Homomorphic Encryption Acceleration Library (HEXL) (In Planning)


CCZoo is not limited to provide various reference implementation based on Intel® TEE technology,
but also provide the solution driven, easy adoption, scalable best pactices to help users in:
- Having an overall understaning of an End-to-End solution based on Intel® TEE.
- Quick adoption or reference under similar senarios in CCZoo with security design based on Intel® TEE.

CCZoo provides confidential computing best practices with below features:
- Whole Flow Data Security
  - Runtime Security
  - In-Transit Security
  - At-Rest Security
- Application Integrity
  - Remote Attestation
- Full Coverage Data Security
  - Input query, output score, model
- Elasticity(Optional)
  - Kubernets

To let users reproduce the solutions easily with mninal porting effoert, CCZoo adopts LibOS
to protect applications from a malicious system stack. The main LibOS we adopted is [Gramine](https://github.com/gramineproject/gramine)
and [Occlum](https://github.com/occlum/occlum). CCZoo also deloy the each solutions
with containerization dockerfile. Users can follow each documents of the solutions to reproduce
it.

CCZoo is a growing project and we have a growing contributor and maintainer community.
Our goal is to continue this growth in both contributions and community adoption.

---

# Confidential Computing Zoo Documentation

The official confidential computing zoo documentation can be found at https://cczoo.readthedocs.io.
Bolow are quick links to some of the most important papes:
- [TensorFlow Serving Cluster PPML based on SGX](https://cczoo.readthedocs.io/en/latest/Solutions/tf_serving_cluster.html)

---

# Confidential Computing Zoo Solution Table

|  Solutions    |  TEE    | Application    |  LibOS    |   Remote Attestation   |   Encryption/Decryption    |TLS    |
| ----          | ----            |----            | ----      |----             |----      |----      |
|   [TensorFlow Serving Cluster PPML based on SGX](https://cczoo.readthedocs.io/en/latest/Solutions/tensorflow-serving-cluster/index.html)   |  SGX |TensorFlow Serving   |  Gramine    |  [Secret Provinsion Service](https://cczoo.readthedocs.io/en/latest/Solutions/tensorflow-serving-cluster/index.html#start-secret-provision-service)| Yes |  gRPC  |


---

# Community Involvement

- Please submit issues in this project if there is any question or request.
- Welcome PRs for contributions.

---


