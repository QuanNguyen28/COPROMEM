$ErrorActionPreference = 'Stop'
$root = 'E:\Project\AAMAS\COPROMEM'
$out = Join-Path $root 'artifacts\research\official_reme_copromem_pilot\reduced_v1'
New-Item -ItemType Directory -Force -Path $out | Out-Null
$stdout = Join-Path $out 'runner.stdout.log'
$stderr = Join-Path $out 'runner.stderr.log'
$args = @(
    '-d', 'Ubuntu', '--',
    '/mnt/e/Project/AAMAS/reme-official-service-v3/bin/python',
    '/mnt/e/Project/AAMAS/COPROMEM/scripts/run_official_reme_copromem_pilot.py'
)
$process = Start-Process -FilePath 'wsl.exe' -ArgumentList $args -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput $stdout -RedirectStandardError $stderr
Set-Content -NoNewline -Encoding ascii -Path (Join-Path $out 'launcher-windows.pid') -Value $process.Id
Write-Output "windows_launcher_pid=$($process.Id) status=$out\runner-status.json progress=$root\artifacts\research\official_reme_copromem_pilot\progress.jsonl report=$out\FINAL_REPORT.md"
