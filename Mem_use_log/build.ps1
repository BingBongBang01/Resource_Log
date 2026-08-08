<#
.SYNOPSIS
    Builds dist\Mem_use_log.exe — a single self-contained executable.

.DESCRIPTION
    Wraps `pyinstaller Mem_use_log.spec` with the things that are easy to
    get wrong by hand:

      1. A running instance holds the .exe open and the build fails. This
         app starts with Windows, so it is usually running. Checked first.

      2. The app keeps config.json, data\ and logs\ *next to the .exe*.
         Earlier onedir builds put the .exe one level down, in
         dist\Mem_use_log\, so that is where existing recordings live. The
         onefile .exe sits in dist\ and would start from an empty database.
         Anything found down there is moved up, never overwritten.

    The output is one file. Copy dist\Mem_use_log.exe anywhere and run it;
    it creates its config, database and logs beside itself on first run.

.EXAMPLE
    .\build.ps1
    Build using the packages already installed.

.EXAMPLE
    .\build.ps1 -InstallDeps
    Install/refresh requirements.txt and PyInstaller first, then build.

.EXAMPLE
    .\build.ps1 -Clean
    Discard PyInstaller's cache and the build\ folder first. Use this when
    a build misbehaves in a way that a normal rebuild doesn't fix.
#>
[CmdletBinding()]
param(
    [switch]$InstallDeps,
    [switch]$Clean
)

$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

$AppName   = 'Mem_use_log'
$SpecFile  = Join-Path $PSScriptRoot "$AppName.spec"
$DistDir   = Join-Path $PSScriptRoot 'dist'
$ExePath   = Join-Path $DistDir "$AppName.exe"
$LegacyDir = Join-Path $DistDir $AppName      # where onedir builds used to land

# Everything the app writes beside its executable. User data, not build output.
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

# A onefile build runs as two processes (bootloader + app); either one holds
# the file open.
$running = Get-Process -Name $AppName -ErrorAction SilentlyContinue
if ($running) {
    throw "$AppName.exe is running (PID $($running.Id -join ', ')). Quit it from the tray icon and run this again, or: Stop-Process -Name $AppName"
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
# Carry recordings over from an earlier onedir build
# --------------------------------------------------------------------------
if (Test-Path -LiteralPath $LegacyDir) {
    Write-Step 'Found a previous onedir build; moving its recordings up beside the new .exe'
    $moved = @()
    foreach ($item in $UserData) {
        $src = Join-Path $LegacyDir $item
        $dst = Join-Path $DistDir $item
        if (-not (Test-Path -LiteralPath $src)) { continue }
        if (Test-Path -LiteralPath $dst) {
            Write-Warn "kept both: $item already exists in dist\, left the old copy in $AppName\"
            continue
        }
        New-Item -ItemType Directory -Force -Path $DistDir | Out-Null
        Move-Item -LiteralPath $src -Destination $dst
        $moved += $item
        Write-Ok "moved  $item"
    }
    if (-not $moved) { Write-Ok 'nothing to move' }
    Write-Warn "The old dist\$AppName\ folder (.exe + _internal) is no longer used; delete it when you're ready."
}

# --------------------------------------------------------------------------
# Build
# --------------------------------------------------------------------------
# Plain ASCII in console output: cmd.exe's default code page turns dashes
# and quotes into mojibake when build.bat is double-clicked.
Write-Step 'Running PyInstaller (onefile - this takes longer than onedir)'

$pyiArgs = @($SpecFile, '--noconfirm')
if ($Clean) { $pyiArgs += '--clean' }

& $python -m PyInstaller @pyiArgs
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed (exit $LASTEXITCODE)." }

# --------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------
if (-not (Test-Path -LiteralPath $ExePath)) { throw "Build finished but $ExePath is missing." }

$exe = Get-Item -LiteralPath $ExePath
Write-Host ''
Write-Step 'Build complete'
Write-Ok ("exe    {0}  ({1:N1} MB)" -f $exe.FullName, ($exe.Length / 1MB))
foreach ($item in $UserData) {
    $p = Join-Path $DistDir $item
    if (Test-Path -LiteralPath $p) { Write-Ok "data   $p" }
}
Write-Host ''
Write-Host 'Single file: copy Mem_use_log.exe anywhere. It creates config.json, data\ and' -ForegroundColor DarkGray
Write-Host 'logs\ beside itself — move those along with it to keep your recordings.'      -ForegroundColor DarkGray
