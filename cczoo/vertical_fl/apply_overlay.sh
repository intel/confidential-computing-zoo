#!/bin/bash

cp overlay/fedlearner-sgx-dev.dockerfile vertical_fl/
cp overlay/build_dev_docker_image.sh vertical_fl/sgx/
cp overlay/test-ps-sgx.sh vertical_fl/sgx/gramine/CI-Examples/wide_n_deep/
