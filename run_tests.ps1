# Backward-compatible wrapper for the single Python test entrypoint.

param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Args
)

if (Test-Path "venv") {
    & .\venv\Scripts\Activate.ps1
}

python test_runner.py @Args
exit $LASTEXITCODE
