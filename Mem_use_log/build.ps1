<#
.SYNOPSIS
    Builds dist\Mem_use_log\Mem_use_log.exe from source.

.DESCRIPTION
    Wraps `pyinstaller Mem_use_log.spec` with the two things that are easy
    to get wrong by hand:

      1. PyInstaller empties dist\Mem_use_log before it rebuilds. The running
         app keeps its database, logs and config.json in exactly that folder
         (see _resolve_project_root in app/config/settings.py), so a plain
         rebuild silently destroys every recording made so far. This script
         moves that data aside and puts it back.

      2. A running instance holds Mem_use_log.exe open and the build fails
         halfway through, after the folder has already been emptied. The app
         starts with Windows, so it is usually running. This checks first.

.EXAMPLE
    .\build.ps1
    Build using the packages already installed.

.EXAMPLE
    .\build.ps1 -InstallDeps
    Install/refresh requirements.txt and PyInstaller first, then build.

.EXAMPLE
    .\build.ps1 -Clean
    Discard PyInstaller's cache and the build\ folder first. Use this when a
    build misbehaves in a way that a normal rebuild doesn't fix.
#>
[CmdletBinding()]
param(
    [switch]$InstallDeps,
    [switch]$Clean
)

$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

$AppName  = 'Mem_use_log'
$SpecFile = Join-Path $PSScriptRoot "$AppName.spec"
$OutDir   = Join-Path $PSScriptRoot "dist\$AppName"
$HoldDir  = Join-Path $PSScriptRoot 'build\_userdata_hold'

# Everything the app writes next to its executable. These are user data, not
# build output — they must survive a rebuild.
$UserData = @('config.json', 'data', 'logs')

function Write-Step($Message) { Write-Host "==> $Message" -ForegroundColor Cyan }
function Write-Ok($Message)   { Write-Host "    $Message" -ForegroundColor Green }
function Write-Warn($Message) { Write-Host "    $Message" -ForegroundColor Yellow }

# --------------------------------------------------------------------------
# Preflight
# --------------------------------------------------------------------------
Write-Step 'Checking the build environment'

if (-not (Test-Path -LiteralPath $SpecFile)) {
    throw "Mem_use_log.spec not found. Run this script from the folder that contains it."
}

$python = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $python) { $python = (Get-Command py -ErrorAction SilentlyContinue).Source }
if (-not $python) {
    throw "Python not found on PATH. Install Python 3.12 and tick 'Add python.exe to PATH'."
}
Write-Ok "Python: $python  ($(& $python --version 2>&1))"

# The exe is locked while the app runs, and PyInstaller only discovers that
# after it has already emptied the output folder.
$running = Get-Process -Name $AppName -ErrorAction SilentlyContinue
if ($running) {
    throw "$AppName.exe is running (PID $($running.Id -join ', ')). Close it and run this again, or: Stop-Process -Name $AppName"
}

if ($InstallDeps) {
    Write-Step 'Installing dependencies'
    & $python -m pip install --upgrade pip
    & $python -m pip install -r (Join-Path $PSScriptRoot 'requirements.txt')
    & $python -m pip install 'pyinstaller==6.21.0'
    if ($LASTEXITCODE -ne 0) { throw "Dependency install failed (exit $LASTEXITCODE)." }
}

& $python -c "import PyInstaller" 2>$null
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller is not installed. Run:  .\build.ps1 -InstallDeps"
}
Write-Ok "PyInstaller: $(& $python -c 'import PyInstaller; print(PyInstaller.__version__)')"

# --------------------------------------------------------------------------
# Move recorded data out of the blast radius
# --------------------------------------------------------------------------
$held = @()
if (Test-Path -LiteralPath $OutDir) {
    Write-Step 'Setting aside recorded data from the previous build'
    foreach ($item in $UserData) {
        $src = Join-Path $OutDir $item
        if (-not (Test-Path -LiteralPath $src)) { continue }

        if (-not (Test-Path -LiteralPath $HoldDir)) {
            New-Item -ItemType Directory -Path $HoldDir -Force | Out-Null
        }
        $dst = Join-Path $HoldDir $item
        if (Test-Path -LiteralPath $dst) { Remove-Item -LiteralPath $dst -Recurse -Force }

        Move-Item -LiteralPath $src -Destination $dst -Force
        $held += $item
        Write-Ok "held  $item"
    }
    if (-not $held) { Write-Ok 'nothing to keep (no data recorded there yet)' }
}

# --------------------------------------------------------------------------
# Build
# --------------------------------------------------------------------------
$restored = $false
try {
    Write-Step 'Running PyInstaller'

    $pyiArgs = @($SpecFile, '--noconfirm')
    if ($Clean) { $pyiArgs += '--clean' }

    & $python -m PyInstaller @pyiArgs
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed (exit $LASTEXITCODE)." }
}
finally {
    # Runs on success and on failure alike: data left in the hold folder is
    # data the user cannot see and will assume is gone.
    if ($held) {
        if (Test-Path -LiteralPath $OutDir) {
            Write-Step 'Restoring recorded data'
            foreach ($item in $held) {
                Move-Item -LiteralPath (Join-Path $HoldDir $item) -Destination (Join-Path $OutDir $item) -Force
                Write-Ok "restored  $item"
            }
            Remove-Item -LiteralPath $HoldDir -Recurse -Force -ErrorAction SilentlyContinue
            $restored = $true
        }
        else {
            Write-Warn "Build produced no output folder. Your data is safe in:"
            Write-Warn "  $HoldDir"
        }
    }
}

# --------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------
$exe = Join-Path $OutDir "$AppName.exe"
if (-not (Test-Path -LiteralPath $exe)) { throw "Build finished but $exe is missing." }

$size = (Get-ChildItem -LiteralPath $OutDir -Recurse -File | Measure-Object -Property Length -Sum).Sum
Write-Host ''
Write-Step 'Build complete'
Write-Ok "exe    $exe"
Write-Ok ("total  {0:N1} MB across the folder" -f ($size / 1MB))
if ($restored) { Write-Ok "kept   $($held -join ', ')" }
Write-Host ''
Write-Host 'This is a onedir build: ship the whole dist\Mem_use_log folder, not just the .exe.' -ForegroundColor DarkGray
