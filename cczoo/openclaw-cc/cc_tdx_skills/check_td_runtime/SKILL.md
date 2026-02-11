---
name: Check TD Runtime Environment
description: "Check TD Runtime Environment"
metadata: {"openclaw":{"requires":{"bins":["python3"]}}}
---

# Check TD Runtime Environment

检测当前操作系统是否为TDVM机密虚拟机，并提供安全证明。
Check whether the current OS is a TDVM confidential VM and provide security evidence.

## Description
This skill detects whether the current OS system is a TDVM confidential virtual machine and provides security proof if it is. The script checks for Intel TDX-specific features and artifacts to confirm the confidential computing environment.

## Usage
- When user requests to check if the system is a TDVM confidential VM
- When user wants security proof of the confidential computing environment
- When user needs to verify TDX capabilities

## Run
```bash
python3 {baseDir}/scripts/check_td_runtime.py
```

## Output
The script outputs:
- Whether the system is running in TDVM or not
- Security evidence including TDX-specific artifacts
- System configuration details that confirm confidentiality

## Example Requests
- "检测当前系统是否为TDVM机密虚拟机"
- "Check if this is a confidential VM"
- "验证系统的机密计算环境"
- "Show me security proof of TDVM"