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
$CrashFiles = Join-Path $LogRoot "crash-files.txt"
Remove-Item $Stdout,$Stderr,$Summary,$CrashFiles -Force -ErrorAction SilentlyContinue

$started = Get-Date
$p = Start-Process -FilePath $ExePath -WorkingDirectory (Split-Path -Parent $ExePath) -PassThru -RedirectStandardOutput $Stdout -RedirectStandardError $Stderr
$exited = $p.WaitForExit($TimeoutSeconds * 1000)

if ($exited) {
    $p.Refresh()
    $code = $p.ExitCode
    @("result=exited","exit_code=$code","pid=$($p.Id)","runtime_seconds=$([math]::Round(((Get-Date)-$started).TotalSeconds,2))") | Set-Content -Encoding UTF8 $Summary
} else {
    @("result=survived_timeout","exit_code=running","pid=$($p.Id)","runtime_seconds=$TimeoutSeconds") | Set-Content -Encoding UTF8 $Summary
    Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
}

$native = Split-Path -Parent $ExePath
Get-ChildItem -LiteralPath $native -File -ErrorAction SilentlyContinue |
    Where-Object { $_.Extension -in ".dmp",".log",".txt" -and $_.LastWriteTime -ge $started.AddSeconds(-2) } |
    Select-Object -ExpandProperty FullName |
    Set-Content -Encoding UTF8 $CrashFiles

Get-Content $Summary
if (Test-Path $Stderr) {
    $fatal = Select-String -Path $Stderr -Pattern "AccessViolation|MMIO|abort|assert|fatal|unhandled|exception" -CaseSensitive:$false -ErrorAction SilentlyContinue
    if ($fatal) {
        Write-Host "Potential bootstrap blocker(s):"
        $fatal | Select-Object -Last 30 | ForEach-Object { Write-Host $_.Line }
    }
}

if ($exited -and $code -ne 0) { exit $code }
exit 0
