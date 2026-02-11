"""
Actors package, the bussiness logic layer.
"""

import os
import logging
from typing import Dict, List
from hashlib import sha384

from .rtmr import RTMR
from .tdreport import TdReport
from .tdeventlog import TDEventLogEntry, TDEventLogType, TDEventLogSpecIdHeader
from .ccel import CCEL
from .binaryblob import BinaryBlob

__author__ = "cpio"

LOG = logging.getLogger(__name__)


# pylint: disable=too-few-public-methods
class VerifyActor:
    """
    Actor to verify the RTMR
    """

    def _verify_single_rtmr(self, rtmr_index: int, rtmr_value_1: RTMR,
        rtmr_value_2: RTMR) -> None:

        if rtmr_value_1 == rtmr_value_2:
            LOG.info("RTMR[%d] passed the verification.", rtmr_index)
        else:
            LOG.error("RTMR[%d] did not pass the verification", rtmr_index)

    def verify_rtmr(self) -> None:
        """
        Get TD report and RTMR replayed by event log to do verification.
        """
        # 1. Read CCEL from ACPI table at /sys/firmware/acpi/tables/CCEL
        ccelobj = CCEL.create_from_acpi_file()
        if ccelobj is None:
            return

        # 2. Get the start address and length for event log area
        td_event_log_actor = TDEventLogActor(
            ccelobj.log_area_start_address,
            ccelobj.log_area_minimum_length)

        # 3. Collect event log and replay the RTMR value according to event log
        td_event_log_actor.replay()

        # 4. Read TD REPORT via TDCALL.GET_TDREPORT
        td_report = TdReport.get_td_report()

        # 5. Verify individual RTMR value from TDREPORT and recalculated from
        #    event log
        self._verify_single_rtmr(
            0,
            td_event_log_actor.get_rtmr_by_index(0),
            RTMR(bytearray(td_report.td_info.rtmr_0)))

        self._verify_single_rtmr(
            1,
            td_event_log_actor.get_rtmr_by_index(1),
            RTMR(bytearray(td_report.td_info.rtmr_1)))

        self._verify_single_rtmr(
            2,
            td_event_log_actor.get_rtmr_by_index(2),
            RTMR(bytearray(td_report.td_info.rtmr_2)))

        self._verify_single_rtmr(
            3,
            td_event_log_actor.get_rtmr_by_index(3),
            RTMR(bytearray(td_report.td_info.rtmr_3)))


