from datetime import datetime
import uuid
import base64
import quote_generator
import json
import subprocess
import os

quote_data, quote_ret = quote_generator.generate_quote()
# Print hex format of quote_data and data length
#print(f"quote_data hex: {quote_data.hex()}")
#print(f"quote_data length: {len(quote_data)}")

# 2. Convert byte data to Base64 encoded string
quote_base64 = base64.b64encode(quote_data).decode('utf-8')

# 3. Package according to evidence data structure
evidence = {
            "quote": quote_base64,
            "aa_eventlog": None,
            "cc_eventlog": None
        }

# 4. Transcode evidence (URL safe Base64 without padding)
evidence_json = json.dumps(evidence)
evidencebase64 = base64.b64encode(evidence_json.encode()).decode()
evidencebase64 = evidencebase64.replace('+', '-').replace('/', '_').replace('=', '')

res=subprocess.run("./parse_tdreport", capture_output=True, text=True, shell=False)
print(res.stdout)


        # 5. Package req structure
req = {
            "verification_requests": [
                {
                    "tee": "tdx",
                    "evidence": evidencebase64
                }],
            "policy_ids": []
        }

json_file = "quote_inf.json"
if os.path.exists(json_file):
    os.remove(json_file)

with open("quote_inf.json", "w", encoding="utf-8") as f:
    json.dump(req, f, ensure_ascii=False, indent=4)

json_abs_path = os.path.abspath(json_file)
print(f"For more detailed Quote data, please refer to path:\n{json_abs_path}.")
print(f"You can use the {json_file} for further TDX Attestation request.")

