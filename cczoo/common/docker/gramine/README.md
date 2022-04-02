# Gramine-SGX-Dev Image

## What is Gramine?

Gramine (formerly called Graphene) is a lightweight library OS, designed to run a single application 
with minimal host requirements. Gramine can run applications in an isolated environment with benefits
 comparable to running a complete OS in a virtual machine -- including guest customization, ease of 
 porting to different OSes, and process migration.

Gramine supports native, unmodified Linux binaries on any platform. Currently, Gramine runs on Linux 
and Intel SGX enclaves on Linux platforms.

In untrusted cloud and edge deployments, there is a strong desire to shield the whole application 
from rest of the infrastructure. Gramine supports this “lift and shift” paradigm for bringing 
unmodified applications into Confidential Computing with Intel SGX. Gramine can protect applications 
from a malicious system stack with minimal porting effort.

## What is the gramine-sgx-dev image?

The Gramine-SGX-Dev image is a LibOS basic image which provide a TEE(trusted execution environment) 
to do software development.

## How to build it?

Execute the following command to build this docker image:
```
./build_docker_image.sh
```
