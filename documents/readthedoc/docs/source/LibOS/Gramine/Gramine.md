# What is Gramine?

Gramine (formerly called Graphene) is a lightweight library OS, designed to run
a single application with minimal host requirements. Gramine can run applications
in an isolated environment with benefits comparable to running a complete OS in
a virtual machine -- including guest customization, ease of porting to different
OSes, and process migration.

Applications can benefit from confidentiality and integrity guarantees of Intel SGX,
but developers need to be very skilled for effective partitioning and code modification
for Intel SGX environment.

Gramine runs unmodified applications inside Intel SGX. It supports dynamically
loaded libraries, runtime linking, multi-process abstractions, and file authentication.
For additional security, Gramine performs cryptographic and semantic checks at
untrusted host interface. Developers provide a manifest file to configure the
application environment and isolation policies, Gramine automatically does the rest.

In untrusted cloud and edge deployments, there is a strong desire to shield the
whole application from rest of the infrastructure. Gramine supports this “lift
and shift” paradigm for bringing unmodified applications into Confidential Computing
with Intel SGX. Gramine can protect applications from a malicious system stack
with minimal porting effort.


# Quick start

Gramine without SGX has no special requirements.
Gramine with SGX support requires several features from your system:

- the FSGSBASE feature of recent processors must be enabled in the Linux kernel;
- the Intel SGX driver must be built in the Linux kernel;
- Intel SGX SDK/PSW and (optionally) Intel DCAP must be installed.

On Ubuntu 18.04 or 20.04:

```
   sudo curl -fsSLo /usr/share/keyrings/gramine-keyring.gpg https://packages.gramineproject.io/gramine-keyring.gpg
   echo 'deb [arch=amd64 signed-by=/usr/share/keyrings/gramine-keyring.gpg] https://packages.gramineproject.io/ stable main' | sudo tee /etc/apt/sources.list.d/gramine.list
   sudo apt-get update

   sudo apt-get install gramine      # for 5.11+ upstream, in-kernel driver
   sudo apt-get install gramine-oot  # for out-of-tree SDK driver
   sudo apt-get install gramine-dcap # for out-of-tree DCAP driver
```

On RHEL-8-like distribution (like AlmaLinux 8, CentOS 8, Rocky Linux 8, ...):

```
   sudo curl -fsSLo /etc/yum.repos.d/gramine.repo https://packages.gramineproject.io/rpm/gramine.repo
   sudo dnf install gramine          # only the default, distro-provided kernel is supported
```

Prepare a signing key,only for SGX, and if you haven't already:

```
   openssl genrsa -3 -out "$HOME"/.config/gramine/enclave-key.pem 3072
```

# Gramine Helloworld

```
   git clone --depth 1 https://github.com/gramineproject/gramine.git
   cd gramine/CI-Examples/helloworld
```

Without SGX:

```
   make
   gramine-direct helloworld
```

With SGX:

```
   make SGX=1 SGX_SIGNER_KEY="$HOME"/.config/gramine/enclave-key.pem
   gramine-sgx helloworld
```

# Gramine offical link

The official Gramine documentation can be found at https://gramine.readthedocs.io.
Gramine opensource GitHub can be found at https://github.com/gramineproject/gramine.

Below are quick links to some of the most important pages:

- [Quick start and how to run applications](https://gramine.readthedocs.io/en/latest/quickstart.html)
- [Complete building instructions](https://gramine.readthedocs.io/en/latest/devel/building.html)
- [Gramine manifest file syntax](https://gramine.readthedocs.io/en/latest/manifest-syntax.html)
- [Performance tuning & analysis of SGX applications in Gramine](https://gramine.readthedocs.io/en/latest/devel/performance.html)
- [Remote attestation in Gramine](https://gramine.readthedocs.io/en/latest/attestation.html)

