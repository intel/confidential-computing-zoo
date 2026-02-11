#!/usr/bin/env python3
#
# Copyright 2024 Canonical Ltd.
# Authors:
# - Hector Cao <hector.cao@canonical.com>
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License version 3, as published
# by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranties of MERCHANTABILITY,
# SATISFACTORY QUALITY, or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License along with
# this program.  If not, see <http://www.gnu.org/licenses/>.
#

import os
import cpuinfo
import struct

def support_tdx():
    """
    Check whether support TDX in CPU info
    """
    return 'tdx_host_platform' in cpuinfo.get_cpu_info()['flags']


def support_sgx():
    """
    Check whether support TDX in CPU info
    """
    return 'sgx' in cpuinfo.get_cpu_info()['flags']

    """
    MSR(Model Specific Register) Class

    /dev/cpu/<num>/msr provides an interface to read and write the
    model-specific registers (MSRs) of an x86 CPU.  CPUNUM is the
    number of the CPU to access as listed in /proc/cpuinfo.

    The register access is done by opening the file and seeking to
    the MSR number as offset in the file, and then reading or writing
    in chunks of 8 bytes.  An I/O transfer of more than 8 bytes means
    multiple reads or writes of the same register.

    This file is protected so that it can be read and written only by
    the user root, or members of the group root.

    For more information about the MSR, please read https://man7.org/linux/man-pages/man4/msr.4.html
    """
class MSR:
    SGX_MCU_ERRORCODE = 0xa0
    SGX_DEBUG = 0x503
    IA32_FEATURE_CONTROL = 0x3a
    IA32_MKTME_PARTITIONING = 0x87
    IA32_TME_CAPABILITY = 0x981
    IA32_TME_ACTIVATE = 0x982

def _check_kmod():
    """
    Check whether the MSR is loaded, modprobe if not.
    """
    if not os.path.exists("/dev/cpu/0/msr"):
        os.system("modprobe msr")

def readmsr(msr, highbit=63, lowbit=0, cpu=0):
    """
    Read MSR register
    """
    assert abs(msr) < 0xffffffff
    assert os.geteuid() == 0, "need root priviledge"
    val = None
    fdobj = os.open(f'/dev/cpu/{cpu}/msr', os.O_RDONLY)
    os.lseek(fdobj, msr, os.SEEK_SET)
    val = struct.unpack('Q', os.read(fdobj, 8))[0]
    bits = highbit - lowbit + 1
    if bits < 64:
        val >>= lowbit
        val &= (1 << bits) - 1
    return val

def writemsr(msr, val):
    """
    Write MSR register
    """
    assert abs(msr) < 0xffffffff
    assert os.geteuid() == 0, "need root priviledge"

    items = glob.glob('/dev/cpu/[0-9]*/msr')
    for cpu in items:
        try:
            fdobj = os.open(cpu, os.O_WRONLY)
        except (IOError, OSError) as err:
            LOG.error("Fail to open MSR device file: %d", err.errno)
            return False

        os.lseek(fdobj, msr, os.SEEK_SET)

        try:
            os.write(fdobj, struct.pack('Q', val))
        except (IOError, OSError) as err:
            LOG.error("Fail to write MSR device file: %d", err.errno)
            os.close(fdobj)
            return False
        os.close(fdobj)
    return True

def changebit(msr, bit, val):
    n = glob.glob('/dev/cpu/[0-9]*/msr')
    for c in n:
        f = os.open(c, os.O_RDWR)
        os.lseek(f, msr, os.SEEK_SET)
        v = struct.unpack('Q', os.read(f, 8))[0]
        if val:
            v = v | (1 << bit)
        else:
            v = v & ~(1 << bit)
        os.lseek(f, msr, os.SEEK_SET)
        os.write(f, struct.pack('Q', v))
        os.close(f)
    if not n:
        raise OSError("msr module not loaded (run modprobe msr)")
