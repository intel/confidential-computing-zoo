# Encrypted virtual File System with TDX-RA

[Intel TDX (Trust Domain Extensions)](https://www.intel.com/content/www/us/en/developer/articles/technical/intel-trust-domain-extensions.html) technology provides `runtime` security for VMs through hardware encryption. This solution aims to provide `storage security` (via [LUKS](https://en.wikipedia.org/wiki/Linux_Unified_Key_Setup)) and `remote attestation` (via [gRPC-RA-TLS](https://github.com/intel/confidential-computing-zoo/tree/main/cczoo/grpc-ra-tls)) enhancements for `Intel TDX`.

## Introduction

Intel TDX is a CPU hardware-based isolation and encryption technology that provides runtime data security (such as CPU registers, memory data, and interrupt injection) for services within a TDX VM instance. Intel® TDX provides default out-of-the-box protection for your instances and applications. You can migrate existing applications to TDX instances to secure them without modifying application code.

The `LUKS` (Linux Unified Key Setup) is a disk encryption specification created by Clemens Fruhwirth in 2004 and was originally intended for Linux. LUKS is used to encrypt a block device. The contents of the encrypted device are arbitrary, and therefore any filesystem can be encrypted, including swap partitions. The `LUKS` implements a platform-independent standard on-disk format for use in various tools. This not only facilitates compatibility and interoperability among different programs, but also assures that they all implement password management in a secure and documented manner.

The `gRPC-RA-TLS` technology provide identity authentication and key transmission support for LUKS, which simplifies the process of decrypting and mounting, and allow it to be safely and automatically deployed.

## Architecture

![](tdx-encrypted-vfs.svg)

On the trusted side, users use secret keys to create encrypted block files, store secret data into it, and then deploy the `get secret` service to manage the keys.

The user copies the encrypted block file from the trusted end to the non-trusted end.

On the untrustworthy side, the `LUKS storage service` communicates with the trusted side for attestation and getting the key, then decrypts and mounts the block file through the key, so that the application can safely read the data from the mounting path.

## Deployment

### Setup LUKS environment

```
# for centos
yum install cryptsetup

# for ubuntu
apt install cryptsetup
```

### Create encrypted block file

This command will create luks block file and bind it to a idle loop device.

```
VIRTUAL_FS=/root/vfs
./create_encrypted_vfs.sh ${VIRTUAL_FS}
```

After above, user need to create env `LOOP_DEVICE` to bind to the loop device manually.

```
export LOOP_DEVICE=<the binded loop device in outputs>
```

### Mount encrypted block file

- Mount and format via password

    The block loop device needs to be formatted as `ext4` on first mount.

    ```
    FS_DIR=luks_fs
    ./mount_encrypted_vfs.sh ${LOOP_DEVICE} ${FS_DIR} format
    ```

    `Note`: only need to format device on first mount.

- Mount without format via password

    ```
    FS_DIR=luks_fs
    ./unmount_encrypted_vfs.sh ${VIRTUAL_FS} ${FS_DIR}
    ./mount_encrypted_vfs.sh ${LOOP_DEVICE} ${FS_DIR} notformat
    ```

- Mount without format via `gRPC-ra-tls`

    1. build `get_secret` service and copy runtime.

        refer to [get_secret/README.md](https://github.com/intel/confidential-computing-zoo/tree/main/cczoo/tdx-encrypted-vfs/get_secret/README.md) for detail.

    2. start `get_secret` service.

        refer to [get_secret/README.md](https://github.com/intel/confidential-computing-zoo/tree/main/cczoo/tdx-encrypted-vfs/get_secret/README.md) for detail.

    3. mount with `get_secret` service.

        ```
        FS_DIR=luks_fs
        ./unmount_encrypted_vfs.sh ${VIRTUAL_FS} ${FS_DIR}

        export hostname=localhost:50051
        ./mount_encrypted_vfs.sh ${LOOP_DEVICE} ${FS_DIR} notformat get_secret
        ```

## Cloud Practice

1. Aliyun ECS

    Aliyun ECS (Elastic Compute Service) is an IaaS (Infrastructure as a Service) level cloud computing service provided by Alibaba Cloud. It builds eighth generation security-enhanced instance families based on Intel® TDX technology to provide a trusted and confidential environment with a higher security level.

    About how to build TDX confidential computing instance, please refer to the below links:

    Chinese version: https://www.alibabacloud.com/help/zh/elastic-compute-service/latest/build-a-tdx-confidential-computing-environment

    English version：https://www.alibabacloud.com/help/en/elastic-compute-service/latest/build-a-tdx-confidential-computing-environment

    Notice: Ali TDX instance is under external public preview.
