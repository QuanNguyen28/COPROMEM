param(
    [Parameter(Mandatory = $true)][string]$RuntimeRoot,
    [Parameter(Mandatory = $true)][string]$RunDirectory,
    [Parameter(Mandatory = $true)][string]$ProtectedEnvFile,
    [string]$PythonExecutable = "python3"
)

$ErrorActionPreference = "Stop"
$PSNativeCommandArgumentPassing = 'Standard'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [Console]::OutputEncoding
function Convert-ToWslPath([string]$Path) {
    # Do not interpolate a Windows path into a Bash command.  WSLENV `/p`
    # transports it as one path-valued environment element before the fixed
    # WSL shell command runs, preserving backslashes, spaces, apostrophes,
    # parentheses, and Unicode.
    $name = 'COPROMEM_WSL_TRANSPORT_PATH'
    $priorPath = [Environment]::GetEnvironmentVariable($name, 'Process')
    $priorWslEnv = [Environment]::GetEnvironmentVariable('WSLENV', 'Process')
    try {
        [Environment]::SetEnvironmentVariable($name, $Path, 'Process')
        [Environment]::SetEnvironmentVariable('WSLENV', $(if ($priorWslEnv) { "$priorWslEnv`:$name/p" } else { "$name/p" }), 'Process')
        $raw = @(& wsl.exe -d Ubuntu -- sh -c 'test -e -- "$COPROMEM_WSL_TRANSPORT_PATH" && printf "%s\n" "$COPROMEM_WSL_TRANSPORT_PATH"')
    } finally {
        [Environment]::SetEnvironmentVariable($name, $priorPath, 'Process')
        [Environment]::SetEnvironmentVariable('WSLENV', $priorWslEnv, 'Process')
    }
    if ($LASTEXITCODE -ne 0 -or $raw.Count -ne 1) { throw "WSLENV path conversion failed" }
    $value = ([string]$raw[0]).Trim()
    if ([string]::IsNullOrWhiteSpace($value) -or $value -notmatch '^/[^\\\r\n]+$' -or $value.Contains('..')) {
        throw "WSLENV returned a malformed absolute path"
    }
    return $value
}

$runtime = Convert-ToWslPath $RuntimeRoot
$run = Convert-ToWslPath $RunDirectory
$launcher = "$runtime/scripts/launch_reasoningbank_appworld_engineering_detached_wsl.sh"
$runner = "$runtime/scripts/run_reasoningbank_appworld_engineering.py"
$stage = "$run/launcher-stages"
$arguments = @('-d', 'Ubuntu', '--', 'env', "REASONINGBANK_PROTECTED_ENV_FILE=$ProtectedEnvFile", $launcher,
    '--run', $run, '--stage-dir', $stage, '--', $PythonExecutable, $runner, 'run', '--run', $run)
& wsl.exe @arguments
if ($LASTEXITCODE -ne 0) { throw "detached WSL dispatcher failed with exit code $LASTEXITCODE" }
[pscustomobject]@{ dispatcher_exit_code = 0; stage_directory = $stage } | ConvertTo-Json -Compress
