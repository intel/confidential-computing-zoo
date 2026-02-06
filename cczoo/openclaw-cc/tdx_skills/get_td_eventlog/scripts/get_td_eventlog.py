#!/usr/bin/env python3
"""
get_td_eventlog.py
"""

import subprocess
from pathlib import Path


def main():
    print("Fetching TDVM event log...")

    try:
        # Run tdeventlog and capture stdout/stderr as text
        result = subprocess.run(
            ['tdeventlog'],
            capture_output=True,
            text=True,
            check=True  # Raise CalledProcessError on non-zero exit
        )
        # Use the script directory to avoid cwd-dependent paths
        current_dir = Path(__file__).parent
        output_file = current_dir / "td_eventlog.txt"

        if output_file.exists():
            output_file.unlink()

        # Write both stdout and stderr to avoid losing diagnostics
        with open(output_file, 'w', encoding='utf-8') as f:
            output_content = result.stdout + (result.stderr if result.stderr else "")
            f.write(output_content)

        print(f"Success. Log saved to: {output_file.absolute()}")
        print(f"Output length: {len(output_content)} characters")

        try:
            rtmr_result = subprocess.run(
                ['tdrtmrcheck'],
                capture_output=True,
                text=True,
                check=True
            )
            if rtmr_result.returncode != 0:
                print(f"WARN: tdrtmrcheck returned {rtmr_result.returncode}")
            if rtmr_result.stderr:
                print(f"tdrtmrcheck error output: {rtmr_result.stderr}")
        except subprocess.CalledProcessError as e:
            print(f"WARN: tdrtmrcheck failed with return code {e.returncode}")
            if e.stderr:
                print(f"tdrtmrcheck error output: {e.stderr}")

    except subprocess.CalledProcessError as e:
        print(f"WARN: tdeventlog failed with return code {e.returncode}")
        print(f"Error output: {e.stderr}")
    except FileNotFoundError:
        print("WARN: tdeventlog not found. Install tdx-tools and try again.")



if __name__ == "__main__":
    main()

