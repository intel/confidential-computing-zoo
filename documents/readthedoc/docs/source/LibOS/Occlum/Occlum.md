# What is Occlum?

Occlum is a *memory-safe*, *multi-process* library OS (LibOS) for [Intel SGX](https://software.intel.com/en-us/sgx).
As a LibOS, it enables *legacy* applications to run on SGX with *little or even no modifications*
of source code, thus protecting the confidentiality and integrity of user workloads
transparently.

<div align="center">

<p align="center"> <img src="arch_overview.png" height="140px"><br></p>

</div>


Occlum has the following salient features:

  * **Efficient multitasking.**
  Occlum offers _light-weight_ LibOS processes: they are light-weight in the sense
  that all LibOS processes share the same SGX enclave. Compared to the heavy-weight,
  per-enclave LibOS processes, Occlum's light-weight LibOS processes is up to
  _1,000X faster_ on startup and _3X faster_ on IPC. In addition, Occlum offers
  an optional _multi-domain [Software Fault Isolation](http://www.cse.psu.edu/~gxt29/papers/sfi-final.pdf) scheme_
  to isolate the Occlum LibOS processes if needed.
  * **Multiple file system support.**
  Occlum supports various types of file systems, e.g., _read-only hashed FS_ (for integrity protection),
  _writable encrypted FS_ (for confidentiality protection), _untrusted host FS_
  (for convenient data exchange between the LibOS and the host OS).
  * **Memory safety.**
  Occlum is the _first_ SGX LibOS written in a memory-safe programming language ([Rust](https://www.rust-lang.org/)).
  Thus, Occlum is much less likely to contain low-level, memory-safety bugs and
  is more trustworthy to host security-critical applications.
  * **Ease-of-use.**
  Occlum provides user-friendly build and command-line tools. Running applications
  on Occlum inside SGX enclaves can be as simple as only typing several shell
  commands (see the next section).

# Quick Start

To build Occlum from the latest source code, do the following steps in an Occlum
Docker container (which can be prepared as shown in the last section):

1. Download the latest source code of Occlum
    ```
    mkdir occlum && cd occlum
    git clone https://github.com/occlum/occlum .
    ```
2. Prepare the submodules and tools required by Occlum.
    ```
    make submodule
    ```
3. Compile and test Occlum
    ```
    make

    # test musl based binary
    make test

    # test glibc based binary
    make test-glibc

    # stress test
    make test times=100
    ```

    For platforms that don't support SGX
    ```
    SGX_MODE=SIM make
    SGX_MODE=SIM make test
    ```
4. Install Occlum
    ```
    make install
    ```
   which will install the `occlum` command-line tool and other files at `/opt/occlum`.


# Occlum Helloworld

If you were to write an SGX Hello World project using some SGX SDK, the project
would consist of hundreds of lines of code. And to do that, you have to spend a
great deal of time to learn the APIs, the programming model, and the build system
of the SGX SDK.

Thanks to Occlum, you can be freed from writing any extra SGX-aware code and only
need to type some simple commands to protect your application with SGX transparently---in four easy steps.

**Step 1. Compile the user program with the Occlum toolchain (e.g., `occlum-gcc`)**
```
$ occlum-gcc -o hello_world hello_world.c
$ ./hello_world
Hello World
```
Note that the Occlum toolchain is not cross-compiling in the traditional sense:
the binaries built by the Occlum toolchain is also runnable on Linux. This property
makes it convenient to compile, debug, and test user programs intended for Occlum.

**Step 2. Initialize a directory as the Occlum instance via `occlum init` or `occlum new`**
```
$ mkdir occlum_instance && cd occlum_instance
$ occlum init
```
or
```
$ occlum new occlum_instance
```
The `occlum init` command creates the compile-time and run-time state of Occlum
in the current working directory. The `occlum new` command does basically the same
thing but in a new instance diretory. Each Occlum instance directory should be used
for a single instance of an application; multiple applications or different instances
of a single application should use different Occlum instances.

**Step 3. Generate a secure Occlum FS image and Occlum SGX enclave via `occlum build`**
```
$ cp ../hello_world image/bin/
$ occlum build
```
The content of the `image` directory is initialized by the `occlum init` command.
The structure of the `image` directory mimics that of an ordinary UNIX FS, containing
directories like `/bin`, `/lib`, `/root`, `/tmp`, etc. After copying the user program
`hello_world` into `image/bin/`, the `image` directory is packaged by the `occlum build`
command to generate a secure Occlum FS image as well as the Occlum SGX enclave.
The FS image is integrity protected by default, if you want to protect the confidentiality
and integrity with your own key, please check out [here](docs/encrypted_image.md).

For platforms that don't support SGX, it is also possible to run Occlum in SGX
simulation mode. To switch to the simulation mode, `occlum build` command must be
given an extra argument or an environment variable as shown below:
```
$ occlum build --sgx-mode SIM
```
or
```
$ SGX_MODE=SIM occlum build
```

**Step 4. Run the user program inside an SGX enclave via `occlum run`**
```
$ occlum run /bin/hello_world
Hello World!
```
The `occlum run` command starts up an Occlum SGX enclave, which, behind the scene,
verifies and loads the associated Occlum FS image, spawns a new LibOS process to
execute `/bin/hello_world`, and eventually prints the message.

# Occlum offical link
The official Occlum can be found at https://occlum.io/.
Occlum opensource GitHub can be found at https://github.com/gramineproject/gramine.

