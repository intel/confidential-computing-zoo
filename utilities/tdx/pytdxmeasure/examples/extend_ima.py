#!/usr/bin/python
"""
The Linux Integrity Measurement Architecture (IMA) subsystem is part of the Linux\
    Integrity subsystem and it is responsible for calculating the hashes of files\
    and programs before they are loaded, and supports reporting on the hashes and\
    validate if they adhere to a predefined list.

Most Debian distros enables IMA by default and the measurement can be found at \
    /sys/kernel/security/ima/ascii_runtime_measurements
To enable IMA in kernel for TDs, please set the kernel configs like this:
    CONFIG_INTEGRITY=y
    CONFIG_IMA=y
    CONFIG_IMA_MEASURE_PCR_IDX=10
    CONFIG_IMA_LSM_RULES=y
Also additional kernel command needed to be added for IMA enablement
    ima=on, ima_policy=tcb, ima_hash=sha384

Traditionally IMA measurements are anchored in Trusted Platform Module (TPM),\
    since vTPM is not available in TD guest. This utility can be used to anchor\
    IMA measurements into RTMR registers. Note that RTMR could only accept SHA384\
    digests.
"""

import os
import logging
import argparse
import codecs
from pytdxmeasure.rtmr import RTMR

DEFAULT_PATH_FOR_MEASUREMENT = '/sys/kernel/security/ima/ascii_runtime_measurements'
EXCEPTION_KEY_WORD = 'boot_aggregate'
DEFAULT_RTMR_INDEX = 3

LOG = logging.getLogger(__name__)

def fetch_ima_measurements():
    """
    Fetch IMA measurements in ascii mode from file system
    """

    measurements = []
    if not os.path.exists(DEFAULT_PATH_FOR_MEASUREMENT):
        LOG.error("Could not find ascii measurements in %s",
                  DEFAULT_PATH_FOR_MEASUREMENT)
        return None

    with open(DEFAULT_PATH_FOR_MEASUREMENT, mode='r', encoding='utf-8') as measurement_file:
        measurement_lines = measurement_file.readlines()
        for line in measurement_lines:
            if EXCEPTION_KEY_WORD in line:
                continue
            content = line.split(" ")
            measurements.append(content[3])

    return measurements

def extend_measurements_to_rtmr(contents, rtmr_index):
    """
    Extend the measurements collected into RTMR registers
    """
    if not contents:
        LOG.error("No content provided for RTMR extend")
        return None

    if int(rtmr_index) < 2:
        LOG.error("Invalid RTMR index %d provided", int(rtmr_index))
        return None

    for content in contents:
        # currently RTMR only supports hash with sha384
        if 'sha384' not in content:
            LOG.info("Skip measurements not using sha384")
            continue
        content = content.split(":")
        res = RTMR.extend_rtmr(str(codecs.decode(content[1],"hex")), rtmr_index)
        if res != RTMR.EXTEND_SUCCESS:
            LOG.error("Failed to extend %s", content[1])

    return None

if __name__ == "__main__":
    LOG.info("Extending IMA measurements into RTMR")

    parser = argparse.ArgumentParser(
        description="The utility to extend IMA measurements into RTMR register")
    parser.add_argument('-i', type=int, default=DEFAULT_RTMR_INDEX,
                        help='index of RTMR register to extend', dest='rtmr_index')
    args = parser.parse_args()

    m = fetch_ima_measurements()
    extend_measurements_to_rtmr(m, args.rtmr_index)
