# Cross language framework Java example

This directory contains an example for running a Java example in cross language
framework, including the Makefile and a template for generating the manifest.

## Installing prerequisites

For generating the manifest and running the example, run the following command
to install the required packages (Ubuntu-specific):

    sudo apt-get install openjdk-11-jdk

## Building for gramine-sgx

Run `make SGX=1` (non-debug) or `make SGX=1 DEBUG=1` (debug) in the directory.

## Run example with Gramine

With SGX:

    gramine-sgx java -Xmx8G clf_test

Note: If using 64G or greater enclave sizes, the JVM flag `-Xmx8G` can be omitted in gramine-sgx.
