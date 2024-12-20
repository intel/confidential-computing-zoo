"""
Dump command line
"""

from abc import abstractmethod
import logging
import logging.config
from .actor import VerifyActor, TDEventLogActor
from .tdreport import TdReport
from .rtmr import RTMR
from .ccel import CCEL

__author__ = "cpio"

LOG = logging.getLogger(__name__)


class TDXMeasurementCmdBase:
    """
    Base class for TDX measurements commands.
    """

    def __init__(self):
        logging.basicConfig(level=logging.DEBUG, format='%(message)s')

    @abstractmethod
    def run(self):
        """
        Interface to be impelemented by child classes
        """
        raise NotImplementedError


class TDXEventLogsCmd(TDXMeasurementCmdBase):
    """
    Cmd executor for dump TDX event logs.
    """

    def run(self):
        """
        Run cmd
        """

        LOG.info("=> Read CCEL ACPI Table")
        ccelobj = CCEL.create_from_acpi_file()
        if ccelobj is None:
            return
        ccelobj.dump()

        actor = TDEventLogActor(ccelobj.log_area_start_address,
            ccelobj.log_area_minimum_length)

        LOG.info("")
        LOG.info("=> Read Event Log Data - Address: 0x%X(0x%X)",
                 ccelobj.log_area_start_address,
                 ccelobj.log_area_minimum_length)
        actor.dump_td_event_logs()

        LOG.info("")
        LOG.info("=> Replay Rolling Hash - RTMR")
        actor.dump_rtmrs()


class TDXVerifyCmd(TDXMeasurementCmdBase):
    """
    Cmd executor for verify RTMR
    """

    def run(self):
        """
        Run cmd
        """
        LOG.info("=> Verify RTMR")
        VerifyActor().verify_rtmr()


class TDXTDReportCmd(TDXMeasurementCmdBase):
    """
    Cmd executor to dump TD report.
    """

    def run(self):
        """
        Run cmd
        """

        LOG.info("=> Dump TD Report")
        TdReport.get_td_report().dump()

class TDXRTMRExtendCmd():
    """
    Cmd executor to extend RTMR register
    """

    def __init__(self):
        logging.basicConfig(level=logging.DEBUG, format='%(message)s')

    @staticmethod
    def run(extend_raw_data, extend_rtmr_index):
        """
        Run cmd
        """

        LOG.info("=> Extend RTMR")
        res = RTMR.extend_rtmr(extend_raw_data, extend_rtmr_index)
        if res == RTMR.EXTEND_SUCCESS:
            LOG.info("Changed RTMR value in TD Report")
            TdReport.get_td_report().dump()
