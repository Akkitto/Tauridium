[CmdletBinding()]
param(
  [switch]$NoSystemChanges,
  [switch]$Portable
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$Root = Split-Path -Parent $PSScriptRoot
$PythonRunnerPath = Join-Path $PSScriptRoot "python.ps1"

try {
  if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
    throw "This verifier bootstrap requires Windows"
  }
  Set-Location -LiteralPath $Root
  $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User") + ";" + $env:Path
  $ShimRoots = @(Join-Path $HOME "scoop\shims")
  if ($env:SCOOP) { $ShimRoots += Join-Path $env:SCOOP "shims" }
  foreach ($ShimRoot in $ShimRoots) {
    if ($ShimRoot -and (Test-Path -LiteralPath $ShimRoot)) { $env:Path += ";" + $ShimRoot }
  }

  # Portable mode deliberately bypasses package managers and ambient tools. It
  # is useful on managed runners and exercises the same fallback used by init.
  $MinisignCommand = $null
  if (-not $Portable) {
    $MinisignCommand = Get-Command -Name "minisign.exe" -ErrorAction SilentlyContinue
    if ($null -eq $MinisignCommand -and -not $NoSystemChanges) {
      if ($null -ne (Get-Command -Name "scoop" -ErrorAction SilentlyContinue)) {
        try {
          & scoop install minisign
          if ($LASTEXITCODE -ne 0) { Write-Warning "Scoop Minisign installation failed; checking other verified options." }
        } catch {
          Write-Warning "Scoop could not install Minisign; checking other verified options."
        }
        $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User") + ";" + $env:Path
        $MinisignCommand = Get-Command -Name "minisign.exe" -ErrorAction SilentlyContinue
      }
      if ($null -eq $MinisignCommand -and $null -ne (Get-Command -Name "winget.exe" -ErrorAction SilentlyContinue)) {
        try {
          & winget.exe install -e --id jedisct1.minisign --source winget --accept-source-agreements --accept-package-agreements
          if ($LASTEXITCODE -ne 0) { Write-Warning "WinGet Minisign installation failed; using the verified portable fallback." }
        } catch {
          Write-Warning "WinGet could not install Minisign; using the verified portable fallback."
        }
        $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User") + ";" + $env:Path
        $MinisignCommand = Get-Command -Name "minisign.exe" -ErrorAction SilentlyContinue
      }
    }
  }

  if ($null -ne $MinisignCommand) {
    & $MinisignCommand.Source -v
    if ($LASTEXITCODE -ne 0) { throw "Installed Minisign validation failed" }
  } else {
    $BootstrapArguments = @("tools/security_tools.py", "--ensure-minisign")
    if ($NoSystemChanges) { $BootstrapArguments += "--no-download" }
    & powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File $PythonRunnerPath @BootstrapArguments
    if ($LASTEXITCODE -ne 0) { throw "Verified portable Minisign setup failed; no unverified executable was accepted" }
  }
  Write-Host "Tauridium Minisign verifier is ready."
  exit 0
} catch {
  Write-Error ("Tauridium Minisign setup failed: {0}" -f $_.Exception.Message)
  exit 1
}
