## TDX Measurement Tool

The measurement tool runs within TD guest to get `RTMR` value from TDREPORT via
Linux attestion driver, and gets the full TD event log from CCEL ACPI table.
Then it uses the TD event log to verify the RTMR value or change.

CSP or tenant developer could use it to analyze and debug the TDX measurement
before providing the TDX guest VM.

![](https://github.com/intel/tdx-tools/blob/main/doc/tdx_measurement.png)

### Overview

The `RTMR` stands for Run-time Measurement Register, recording measurement for the component participating in the booting process.
TDX supports four RTMRs, including RTMR[0], RTMR[1], RTMR[2] and RTMR[3]. 

The same RTMR may store measurement for different section in `direct boot` or `grub boot`.

1. Direct boot
  - RTMR[0]: It stores the measurement for the TDVF configuration. Changes on a part of the tdvm launch parameters, such memory size, will affect the final measurement.
  - RTMR[1]: It stores the measurement for the kernel and cmdline passed to the kernel.
  - RTMR[2] and RTMR[3]: They are reserved and can be used by the guest software to extend the measurement.

2. Grub boot
  - RTMR[0]: It works as it does in the direct boot.
  - RTMR[1]: It stores the measurement for the OS loader,  such as grub.
  - RTMR[2]: It works as it does in the direct boot.
  - RTMR[3]: It is reserved and can be used by the guest software to extend the measurement.

More details can be found in the [Articles-906357](https://lwn.net/Articles/906357/) and [Commit 9d2b64a](https://github.com/intel/tdx/commit/9d2b64a6b798668f9cc069992e3926bccffd0cfa#)

### Prerequisites

The Log Area Start Address (LASA) is from ACPI CCEL table. Please see [GHCI specification](https://cdrdv2.intel.com/v1/dl/getContent/726790).

### Run

1. Get Event Log

    ```
    ./tdx_eventlogs
    ```

2. Get TD Report

    ```
    ./tdx_tdreport
    ```

3. Verify the RTMR

    ```
    ./tdx_verify_rtmr
    ```

### Installation

Build and install TDX Measurement Tool:

```sh
python3 setup.py bdist_wheel
pip3 install dist/*.whl --force-reinstall
```
