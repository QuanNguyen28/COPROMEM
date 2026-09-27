$ErrorActionPreference = 'Stop'
$root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$run = Join-Path $root 'artifacts\research\official_reme_copromem_pilot\fixed_dynamic_v4'
New-Item -ItemType Directory -Force -Path (Join-Path $run 'logs') | Out-Null
$stdout = Join-Path $run 'logs\runner.stdout.log'
$stderr = Join-Path $run 'logs\runner.stderr.log'
$linuxScript = (wsl.exe -d Ubuntu -- wslpath -a ($PSScriptRoot.Replace('\','/'))).Trim() + '/run_fixed_dynamic.sh'
$proc = Start-Process -FilePath 'wsl.exe' -ArgumentList @('-d','Ubuntu','--','bash',$linuxScript) -RedirectStandardOutput $stdout -RedirectStandardError $stderr -WindowStyle Hidden -PassThru
$proc.Id | Set-Content -NoNewline (Join-Path $run 'windows-runner.pid')
Write-Output $proc.Id
