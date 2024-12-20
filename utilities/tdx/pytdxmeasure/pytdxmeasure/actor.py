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


# pylint: disable=too-few-public-methods
class TDEventLogActor:
    """
    Event log actor
    """

    def __init__(self, base, length):
        self._data = None
        self._log_base = base
        self._log_length = length
        self._specid_header = None
        self._event_logs = []
        self._rtmrs = {}

    def _read(self, ccel_file="/sys/firmware/acpi/tables/data/CCEL"):
        assert os.path.exists(ccel_file), f"Could not find the CCEL file {ccel_file}"
        try:
            with open(ccel_file, "rb") as fobj:
                self._data = fobj.read()
                assert len(self._data) > 0
                return self._data
        except (PermissionError, OSError):
            LOG.error("Need root permission to open file %s", ccel_file)
            return None

    @staticmethod
    def _replay_single_rtmr(event_logs: List[TDEventLogEntry]) -> RTMR:
        rtmr = bytearray(RTMR.RTMR_LENGTH_BY_BYTES)

        for event_log in event_logs:
            digest = event_log.digests[0]
            sha384_algo = sha384()
            sha384_algo.update(rtmr + digest)
            rtmr = sha384_algo.digest()

        return RTMR(rtmr)

    def get_rtmr_by_index(self, index: int) -> RTMR:
        """
        Get RTMR by TD register index
        """
        return self._rtmrs[index]

    def process(self) -> None:
        """
        Factory process raw data and generate entries
        """
        if self._specid_header is not None:
            return

        if self._read() is None:
            return

        index = 0
        count = 0
        blob = BinaryBlob(self._data, self._log_base)

        while index < self._log_length:
            start = index
            rtmr, index = blob.get_uint32(index)
            etype, index = blob.get_uint32(index)

            if rtmr == 0xFFFFFFFF:
                break

            if etype == TDEventLogType.EV_NO_ACTION:
                self._specid_header = TDEventLogSpecIdHeader(
                    self._log_base + start)
                self._specid_header.parse(self._data[start:])
                index = start + self._specid_header.length
            else:
                event_log_obj = TDEventLogEntry(self._log_base + start,
                    self._specid_header)
                event_log_obj.parse(self._data[start:])
                index = start + event_log_obj.length
                self._event_logs.append(event_log_obj)

            count += 1

    def replay(self) -> Dict[int, RTMR]:
        """
        Replay event logs to generate RTMR value, which will be used during
        verification
        """
        self.process()

        # result dictionary for classifying event logs by rtmr index
        # the key is a integer, which represents rtmr index
        # the value is a list of event log entries whose rtmr index is equal to
        # its related key
        event_logs_by_index = {}
        for index in range(RTMR.RTMR_COUNT):
            event_logs_by_index[index] = []

        for event_log in self._event_logs:
            event_logs_by_index[event_log.rtmr].append(event_log)

        rtmr_by_index = {}
        for rtmr_index, event_logs in event_logs_by_index.items():
            rtmr_value = TDEventLogActor._replay_single_rtmr(event_logs)
            rtmr_by_index[rtmr_index] = rtmr_value

        self._rtmrs = rtmr_by_index

    def dump_td_event_logs(self) -> None:
        """
        Dump all TD event logs.
        """
        self.process()

        count, start = 0, 0

        LOG.info("==== TDX Event Log Entry - %d [0x%X] ====",
            count, self._log_base + start)
        self._specid_header.dump()
        count += 1
        start += self._specid_header.length

        for event_log in self._event_logs:
            LOG.info("==== TDX Event Log Entry - %d [0x%X] ====",
            count, self._log_base + start)
            event_log.dump()
            count += 1
            start += event_log.length

    def dump_rtmrs(self) -> None:
        """
        Dump RTMRs replayed by event log.
        """
        self.replay()

        for rtmr_index, rtmr in self._rtmrs.items():
            LOG.info("==== RTMR[%d] ====", rtmr_index)
            rtmr.dump()
            LOG.info("")
