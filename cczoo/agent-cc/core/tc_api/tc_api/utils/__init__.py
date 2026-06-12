"""Shared low-level utilities for the tc-api service layer."""

import logging
import subprocess
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from tlog.types import Entry
from ..transparency.commit_client import TrustedLogAPI

logger = logging.getLogger(__name__)


@dataclass
class ToolResult:
    """Structured result from a subprocess execution."""
    ok: bool
    returncode: int
    stdout: str
    stderr: str
    command: str
    status: str  # "success" | "failed" | "timeout"
    error: Optional[Dict[str, str]] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    def as_log(self) -> Dict[str, Any]:
        """Return a dict suitable for tlog recording."""
        log: Dict[str, Any] = {
            "command": self.command,
            "exit_code": self.returncode,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "status": self.status,
        }
        if self.error:
            log["error"] = self.error
        if self.extra:
            log.update(self.extra)
        return log


def run_tool(
    cmd: list[str],
    *,
    tlog: Optional[TrustedLogAPI] = None,
    record_id: Optional[str] = None,
    entry_key: Optional[str] = None,
    timeout: int = 600,
    env: Optional[Dict[str, str]] = None,
    extra_log: Optional[Dict[str, Any]] = None,
) -> ToolResult:
    """Run an external tool, log the result to tlog, and return a structured ToolResult.

    Parameters
    ----------
    cmd : list[str]
        The command to execute.
    tlog, record_id, entry_key : optional
        If all three are given the result is automatically recorded as a tlog entry.
    timeout : int
        Subprocess timeout in seconds (default 600).
    env : dict, optional
        Custom environment variables.  ``None`` inherits the current env.
    extra_log : dict, optional
        Extra fields merged into the tlog entry dict.
    """
    command_str = " ".join(cmd)
    extra = dict(extra_log) if extra_log else {}

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env)
        ok = result.returncode == 0
        status = "success" if ok else "failed"
        error = None if ok else {
            "type": "subprocess.CalledProcessError",
            "message": result.stderr.strip() or result.stdout.strip() or "command failed",
        }
        tr = ToolResult(
            ok=ok,
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            command=command_str,
            status=status,
            error=error,
            extra=extra,
        )
    except subprocess.TimeoutExpired:
        tr = ToolResult(
            ok=False,
            returncode=-1,
            stdout="",
            stderr="",
            command=command_str,
            status="timeout",
            error={"type": "subprocess.TimeoutExpired", "message": f"Command timed out after {timeout}s"},
            extra=extra,
        )
    except FileNotFoundError:
        tr = ToolResult(
            ok=False,
            returncode=-1,
            stdout="",
            stderr="",
            command=command_str,
            status="failed",
            error={"type": "FileNotFoundError", "message": f"Command not found: {cmd[0]}"},
            extra=extra,
        )
    except Exception as exc:
        tr = ToolResult(
            ok=False,
            returncode=-1,
            stdout="",
            stderr="",
            command=command_str,
            status="failed",
            error={"type": type(exc).__name__, "message": str(exc)},
            extra=extra,
        )

    if not tr.ok:
        logger.error("Tool failed: %s — %s", cmd[0], tr.error)
    else:
        logger.info("Tool succeeded: %s", cmd[0])

    if tlog is not None and record_id is not None and entry_key is not None:
        tlog.add_entry(record_id, Entry(key=entry_key, value=tr.as_log()))

    return tr
