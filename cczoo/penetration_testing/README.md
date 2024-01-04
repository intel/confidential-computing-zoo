# Penetration Testing

## Introduction

This penetration testing aims to show how SGX protects the runtime confidentiality of applications while facing privileged malware memory attacks.

CCZoo penetration tests case include two parts: unauthorized access and data theft.

unauthorized access is to gain server privileges through unauthorized access, such as implanting privileged backdoors and obtaining privileged shells.

Data theft is to verify the memory confidentiality of SGX runtime, memory attacks will be performed on high-value data applications through privileged applications or shells to steal their runtime memory data.

## Tests overview

1. Unauthorized Access:
    - Redis

        Please refer to [unauthorized_access/redis/README.md](unauthorized_access/redis/README.md) for detail.

2. Memory Attack:
    - Key generator

        This application is generating keys in memory and implemented based on the Intel SGX SDK.

        It will use the same source code to compile SGX applications and non-SGX applications, and perform memory attacks on them to verify the confidentiality of SGX runtime memory.

        Please refer to [memory_attack/sgx/key_generator/README.md](memory_attack/sgx/key_generator/README.md) for detail.
