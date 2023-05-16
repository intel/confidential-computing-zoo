# TDX-Dev Image

## What is TDX?

Intel® Trust Domain Extensions ([Intel® TDX](https://www.intel.com/content/www/us/en/developer/articles/technical/intel-trust-domain-extensions.html)) is introducing new, architectural elements to help deploy hardware-isolated, virtual machines (VMs) called trust domains (TDs).

## What is the tdx-dev image?

The TDX-Dev image is a Dev image which provide a TEE(trusted execution environment) 
to do software development.

## How to build it?

Execute the following command to build this docker image:
```
base_image=centos:8
image_tag=tdx-dev:dcap1.15-centos8-latest
./build_docker_image.sh ${base_image} ${image_tag}
```

`centos:8` could be selected as base_image.
