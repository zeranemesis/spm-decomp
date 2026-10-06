param(
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"

$PortRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Vendor = Join-Path $PortRoot "vendor"
$WiiCompiled = Join-Path $Vendor "Wiicompiled"
$PinnedRef = "6fa24737d3362b6cba8162671745262751f457b8"

New-Item -ItemType Directory -Force -Path $Vendor | Out-Null

if (-not (Test-Path (Join-Path $WiiCompiled ".git"))) {
    git clone https://github.com/patchzyy/Wiicompiled.git $WiiCompiled
}

Push-Location $WiiCompiled
try {
    git fetch origin
    git checkout $PinnedRef

    dotnet build translator/Translator.sln -c Release
    if (-not $SkipTests) {
        dotnet test translator/Translator.sln -c Release --no-build
    }
}
finally {
    Pop-Location
}

Write-Host ""
Write-Host "WiiCompiled translator is ready at:"
Write-Host "  $WiiCompiled"
Write-Host "Pinned revision: $PinnedRef"
if ($SkipTests) { Write-Host "Tests skipped." }
