param()

$ErrorActionPreference = "Stop"

$PortRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Vendor = Join-Path $PortRoot "vendor"
$DtkDir = Join-Path $Vendor "dtk"
$DtkExe = Join-Path $DtkDir "dtk.exe"

$Version = "v1.8.4"
$Url = "https://github.com/encounter/decomp-toolkit/releases/download/$Version/dtk-windows-x86_64.exe"
$ExpectedSha256 = "6a693e95aa4d30acccc673343302a4abdfa3146bd0fb15cb1a2bce924cbc782a"

New-Item -ItemType Directory -Force -Path $DtkDir | Out-Null

$NeedDownload = $true
if (Test-Path $DtkExe) {
    $Actual = (Get-FileHash -Algorithm SHA256 $DtkExe).Hash.ToLowerInvariant()
    if ($Actual -eq $ExpectedSha256) {
        $NeedDownload = $false
    }
    else {
        Remove-Item -Force $DtkExe
    }
}

if ($NeedDownload) {
    Write-Host "Downloading decomp-toolkit $Version..."
    Invoke-WebRequest -Uri $Url -OutFile $DtkExe

    $Actual = (Get-FileHash -Algorithm SHA256 $DtkExe).Hash.ToLowerInvariant()
    if ($Actual -ne $ExpectedSha256) {
        Remove-Item -Force $DtkExe -ErrorAction SilentlyContinue
        throw "decomp-toolkit SHA-256 mismatch. Expected $ExpectedSha256, got $Actual"
    }
}

Write-Output $DtkExe
