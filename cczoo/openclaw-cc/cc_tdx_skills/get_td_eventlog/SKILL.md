---
name: Get TD Event Log
description: "Get TDVM event log"
metadata: {"openclaw":{"requires":{"bins":["python3"]}}}
---


# Get TD Event Log

获取TDVM的事件日志并保存到文件中。
Get the TDVM event log and save it to a file.


## Description
Retrieve the TDVM event log and saves the output to a file named 'td_eventlog.txt' in the current directory. This provides visibility into the trusted execution environment events.

## Usage
- When user requests to get TDVM event logs
- When user needs to analyze TDVM boot events or measurements
- When user wants to inspect the trusted computing events

## Run
```bash
python {baseDir}/scripts/get_td_eventlog.py
```

## Output
The script outputs:
- Path to the saved event log file (td_eventlog.txt)
- Confirmation that the event log has been captured

## Example Requests
- "获取TD eventlog"
- "Get TD event log"
- "导出TD事件日志"
- "Show me TD event log"
