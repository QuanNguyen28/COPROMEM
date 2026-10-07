param(
    [switch]$Check,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ExtraArgs
)

$python = "/mnt/d/aamas/COPROMEM/alfworld-env-wsl/bin/python"
$runner = "/mnt/d/aamas/COPROMEM/COPROMEM/benchmarks/alfworld-copromem/run_reasoningbank_experiment.py"
$arguments = @("-e", $python, $runner)
if ($Check) {
    $arguments += "--check"
}
if ($ExtraArgs) {
    $arguments += $ExtraArgs
}

& wsl.exe @arguments
exit $LASTEXITCODE
