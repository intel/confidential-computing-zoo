import base64
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class QuoteMaterial:
    quote: str
    report_data: str
    quote_format: str


class TdxQuoteAdapter:
    """Generate quote material through a local TSM/configfs interface."""

    def __init__(
        self,
        report_data_path: str | None = None,
        quote_path: str | None = None,
        quote_format: str | None = None,
    ) -> None:
        self.report_data_path = report_data_path or os.environ.get(
            "TRUCON_TSM_REPORT_DATA_PATH",
            "/sys/kernel/config/tsm/report/reportdata",
        )
        self.quote_path = quote_path or os.environ.get(
            "TRUCON_TSM_QUOTE_PATH",
            "/sys/kernel/config/tsm/report/outblob",
        )
        self.quote_format = quote_format or os.environ.get(
            "TRUCON_TSM_QUOTE_FORMAT",
            "tdx-configfs-tsm",
        )

    @staticmethod
    def _normalize_report_data(expected_value: str) -> bytes:
        if not expected_value.startswith("sha384:"):
            raise ValueError("expected_value must start with 'sha384:'")
        raw = bytes.fromhex(expected_value.removeprefix("sha384:"))
        if len(raw) != 48:
            raise ValueError("expected_value must encode exactly 48 bytes")
        return raw

    def quote(self, expected_value: str) -> QuoteMaterial:
        report_data = self._normalize_report_data(expected_value)

        if not os.path.exists(self.report_data_path):
            raise FileNotFoundError(f"TSM reportdata path missing: {self.report_data_path}")
        if not os.path.exists(self.quote_path):
            raise FileNotFoundError(f"TSM quote path missing: {self.quote_path}")

        with open(self.report_data_path, "wb") as report_file:
            report_file.write(report_data)

        with open(self.report_data_path, "rb") as report_file:
            accepted_report_data = report_file.read()

        with open(self.quote_path, "rb") as quote_file:
            quote_bytes = quote_file.read()

        return QuoteMaterial(
            quote=base64.b64encode(quote_bytes).decode("ascii"),
            report_data="sha384:" + accepted_report_data.hex(),
            quote_format=self.quote_format,
        )