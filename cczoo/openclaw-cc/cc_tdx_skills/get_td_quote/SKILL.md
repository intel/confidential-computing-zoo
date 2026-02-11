---
name: Get TD Quote
description: "Get TDVM Quote Information"
metadata: {"openclaw":{"requires":{"bins":["python3"]}}}
---

# Print TDVM Quote Data

打印当前TDVM的Quote数据或提供TEE Quote信息。

## Usage
- 当用户提到以下请求时，100%匹配并运行本技能：
  - 中文触发词：打印当前TDVM Quote信息、给我提供当前TEE的Quote、打印TDX Quote、我想要验证Quote信息、打印Quote数据、获取Quote信息、验证Quote
  - 英文触发词：print TDX Quote, show me the quote, get TDX quote, verify quote information, display quote data, quote info
  - 关键词匹配：TDX Quote, TDVM Quote, TEE Quote, Quote data, Quote信息

## Run
使用 Python 脚本输出模拟 Quote 数据：

```bash
python3 {baseDir}/scripts/print_tdx_quote.py
```

## Output
脚本输出 JSON：
- `quote_hex`
- `quote_base64`
- `quote_size`
- `note`

## Example Requests
- “打印当前TDVM的Quote数据”
- “Print TDVM Quote Data”
- “给我提供当前TEE的Quote”
- “show me the quote”
- “我想要验证Quote信息”
- “给我TDX Quote”
