param(
    [Parameter(Mandatory = $true)][string]$RuntimeRoot,
    [Parameter(Mandatory = $true)][string]$RunDirectory,
    [Parameter(Mandatory = $true)][string]$ProtectedEnvFile,
    [string]$PythonExecutable = "python3"
)

$ErrorActionPreference = "Stop"
function Convert-ToWslPath([string]$Path) {
    $value = (wsl.exe -d Ubuntu -- wslpath -a $Path).Trim()
    if (-not $value.StartsWith('/')) { throw "wslpath did not return an absolute path" }
    return $value
}

$runtime = Convert-ToWslPath $RuntimeRoot
$run = Convert-ToWslPath $RunDirectory
$launcher = "$runtime/scripts/launch_reasoningbank_appworld_engineering_detached_wsl.sh"
$runner = "$runtime/scripts/run_reasoningbank_appworld_engineering.py"
$stage = "$run/launcher-stages"
$arguments = @('-d', 'Ubuntu', '--', 'env', "REASONINGBANK_PROTECTED_ENV_FILE=$ProtectedEnvFile", $launcher,
    '--run', $run, '--stage-dir', $stage, '--', $PythonExecutable, $runner, 'run', '--run', $run)
$process = Start-Process -FilePath 'wsl.exe' -ArgumentList $arguments -WindowStyle Hidden -PassThru -Wait
if ($process.ExitCode -ne 0) { throw "detached WSL dispatcher failed with exit code $($process.ExitCode)" }
[pscustomobject]@{ dispatcher_pid = $process.Id; stage_directory = $stage } | ConvertTo-Json -Compress
