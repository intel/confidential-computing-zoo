# Occlum-SGX-Dev Image

## What is Occlum?

[Occlum](https://arxiv.org/abs/2001.07450) is a memory-safe, multi-process library OS (LibOS) for
 Intel SGX. As a LibOS, it enables legacy applications to run on SGX with little or even no 
 modifications of source code, thus protecting the confidentiality and integrity of user workloads 
 transparently.

## What is the occlum-sgx-dev image?

The Occlum-SGX-Dev image is a LibOS basic image which provide a TEE(trusted execution environment) 
to do software development.

## How to build it?

Execute the following command to build this docker image:
```
base_image=ubuntu:18.04
image_tag=occlum-sgx-dev:latest
./build_docker_image.sh ${base_image} ${image_tag}
```

`ubuntu:18.04` and `ubuntu:20.04` could be selected as base_image.
