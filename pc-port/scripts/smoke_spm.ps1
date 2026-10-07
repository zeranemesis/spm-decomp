param(
    [int]$TimeoutSeconds = 20,
    [string]$ExePath = ""
)

$ErrorActionPreference = "Stop"
$PortRoot = Split-Path -Parent $PSScriptRoot
if (-not $ExePath) { $ExePath = Join-Path $PortRoot "build\native\SPM.exe" }
if (-not (Test-Path -LiteralPath $ExePath -PathType Leaf)) { throw "SPM executable is missing: $ExePath" }

$LogRoot = Join-Path $PortRoot "artifacts\smoke"
New-Item -ItemType Directory -Force -Path $LogRoot | Out-Null
$Stdout = Join-Path $LogRoot "spm-stdout.log"
$Stderr = Join-Path $LogRoot "spm-stderr.log"
$Summary = Join-Path $LogRoot "summary.txt"
Remove-Item $Stdout,$Stderr,$Summary -Force -ErrorAction SilentlyContinue

$started = Get-Date
$p = Start-Process -FilePath $ExePath -WorkingDirectory (Split-Path -Parent $ExePath) -PassThru -RedirectStandardOutput $Stdout -RedirectStandardError $Stderr
$exited = $p.WaitForExit($TimeoutSeconds * 1000)

if ($exited) {
    $p.Refresh()
    $code = $p.ExitCode
    @("result=exited","exit_code=$code","pid=$($p.Id)","runtime_seconds=$([math]::Round(((Get-Date)-$started).TotalSeconds,2))") | Set-Content -Encoding UTF8 $Summary
    Get-Content $Summary
    if ($code -ne 0) { exit $code }
    exit 0
}

@("result=survived_timeout","exit_code=running","pid=$($p.Id)","runtime_seconds=$TimeoutSeconds") | Set-Content -Encoding UTF8 $Summary
Get-Content $Summary
Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
exit 0
