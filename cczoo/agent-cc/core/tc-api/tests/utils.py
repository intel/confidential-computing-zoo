# Copyright (c) 2026 Intel Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from dataclasses import dataclass
from typing import Any, Callable, Iterable


def make_db_patches(db_module: Any, db_path: str, names: Iterable[str]) -> dict[str, Callable[..., Any]]:
    originals = {name: getattr(db_module, name) for name in names}

    def _wrap(name: str) -> Callable[..., Any]:
        original = originals[name]

        def wrapped(*args: Any, **kwargs: Any) -> Any:
            kwargs.setdefault("db_path", db_path)
            return original(*args, **kwargs)

        return wrapped

    return {name: _wrap(name) for name in names}


@dataclass
class MockQuoteMaterial:
    quote: str
    report_data: str
    quote_format: str = "tdx-configfs-tsm"


class EchoQuoteAdapter:
    def __init__(self, quote: str = "base64-quote", quote_format: str = "tdx-configfs-tsm") -> None:
        self._quote = quote
        self._quote_format = quote_format

    def quote(self, expected_value: str) -> MockQuoteMaterial:
        return MockQuoteMaterial(
            quote=self._quote,
            report_data=expected_value,
            quote_format=self._quote_format,
        )


class StaticQuoteAdapter:
    def __init__(
        self,
        report_data: str,
        *,
        should_fail: bool = False,
        quote: str = "base64-quote",
        quote_format: str = "tdx-configfs-tsm",
    ) -> None:
        self._report_data = report_data
        self._should_fail = should_fail
        self._quote = quote
        self._quote_format = quote_format

    def quote(self, expected_value: str) -> MockQuoteMaterial:
        if self._should_fail:
            raise RuntimeError("mock quote failure")
        return MockQuoteMaterial(
            quote=self._quote,
            report_data=self._report_data,
            quote_format=self._quote_format,
        )