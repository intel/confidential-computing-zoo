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
import logging
from pathlib import Path

LOG = logging.getLogger(__name__)

class QuoteConfigTsm:
    """
    Quote generation through ConfigFs-Tsm

    report=/sys/kernel/config/tsm/report/report0
    mkdir $report
    dd if=/dev/urandom of=userdata bs=64B count=1
    dd if=userdata > $report/inblob
    hexdump $report/outblob

    userdata_nonce :
      Up to 64 bytes of user specified binary data.
      For replay protection this should include a nonce,
      but the kernel does not place any restrictions on the content.
    """

    def __init__(self):
        self._read()
        
    def _read(self, tsm_dir : Path = Path('/sys/kernel/config/tsm/report/')):
        assert os.path.exists(tsm_dir), f"Could not find the TSM dir {tsm_dir}"
        report_dir='report0'
        if not os.path.exists(tsm_dir / report_dir):
            os.makedirs(tsm_dir / report_dir)
        with open(tsm_dir / report_dir / 'provider') as pf:
            self.provider = pf.readline().strip('\n')

def verify_tsm():
    logging.basicConfig(level=logging.DEBUG, format='%(message)s')

    tsm = QuoteConfigTsm()
    assert tsm.provider == 'tdx_guest'
