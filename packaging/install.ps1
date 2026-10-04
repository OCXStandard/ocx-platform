<#
.SYNOPSIS
    Installs the ocx-validator CLI from a dist zip.

.DESCRIPTION
    Extracts a zip of the PyInstaller one-dir build (dist\ocx-validator) to a
    user-defined folder and adds that folder to the user's PATH so
    `ocx-validator` can be run from any terminal.

    Create the zip from the repo root with:

        Compress-Archive -Path dist\ocx-validator\* -DestinationPath ocx-validator.zip

.PARAMETER ZipPath
    Path to the dist zip. Defaults to ocx-validator.zip next to this script.

.PARAMETER InstallDir
    Target install folder. If omitted, you are prompted
    (default: %LOCALAPPDATA%\Programs\ocx-validator).

.EXAMPLE
    .\install.ps1
    .\install.ps1 -ZipPath C:\Downloads\ocx-validator.zip -InstallDir D:\tools\ocx-validator
#>
[CmdletBinding()]
param(
    [string]$ZipPath = (Join-Path $PSScriptRoot "ocx-validator.zip"),
    [string]$InstallDir
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $ZipPath)) {
    Write-Error "Zip file not found: $ZipPath"
    exit 1
}

$defaultDir = Join-Path $env:LOCALAPPDATA "Programs\ocx-validator"
if (-not $InstallDir) {
    $answer = Read-Host "Install folder [$defaultDir]"
    $InstallDir = if ([string]::IsNullOrWhiteSpace($answer)) { $defaultDir } else { $answer }
}
$InstallDir = [System.IO.Path]::GetFullPath($InstallDir)

Write-Host "Installing ocx-validator to $InstallDir ..."
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
Expand-Archive -Path $ZipPath -DestinationPath $InstallDir -Force

# If the zip contained a top-level ocx-validator folder, flatten it.
$nested = Join-Path $InstallDir "ocx-validator"
if ((Test-Path (Join-Path $nested "ocx-validator.exe")) -and
    -not (Test-Path (Join-Path $InstallDir "ocx-validator.exe"))) {
    Get-ChildItem $nested | Move-Item -Destination $InstallDir -Force
    Remove-Item $nested -Recurse -Force
}

$exe = Join-Path $InstallDir "ocx-validator.exe"
if (-not (Test-Path $exe)) {
    Write-Error "ocx-validator.exe not found after extraction - is $ZipPath a dist zip?"
    exit 1
}

# Add the install dir to the user's PATH (idempotent).
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
$entries = ($userPath -split ";") | Where-Object { $_ -ne "" }
if ($entries -notcontains $InstallDir) {
    [Environment]::SetEnvironmentVariable("Path", (($entries + $InstallDir) -join ";"), "User")
    Write-Host "Added $InstallDir to the user PATH."
} else {
    Write-Host "$InstallDir is already on the user PATH."
}

Write-Host ""
Write-Host "Installed: $exe"
Write-Host "Open a NEW terminal and run: ocx-validator --help"
