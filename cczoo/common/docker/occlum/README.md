# Occlum-SGX-Dev Image

## What is Occlum?

[Occlum](https://github.com/occlum/occlum) is a memory-safe, multi-process library OS (LibOS) for
 Intel SGX. As a LibOS, it enables legacy applications to run on SGX with little or even no 
 modifications of source code, thus protecting the confidentiality and integrity of user workloads 
 transparently.

## What is the occlum-sgx-dev image?

The Occlum-SGX-Dev image is a LibOS basic image which provide a TEE(trusted execution environment) 
to do software development.

## How to build it?

Execute the following command to build this docker image:
```
base_image=occlum/occlum:0.26.3-ubuntu18.04
image_tag=occlum-sgx-dev:ubuntu18.04-latest
./build_docker_image.sh ${base_image} ${image_tag}
```

`occlum/occlum:0.26.3-ubuntu18.04` and `occlum/occlum:0.26.3-ubuntu20.04` could be selected as base_image.
