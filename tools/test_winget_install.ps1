param(
  [ValidateSet('x64', 'arm64')][Parameter(Mandatory = $true)][string]$Architecture,
  [string]$Version = '1.0.3',
  [string]$PreviousVersion = '1.0.2'
)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
Set-StrictMode -Version Latest
if ($env:GITHUB_ACTIONS -ne 'true' -or $env:RUNNER_ENVIRONMENT -ne 'github-hosted') {
  throw 'Installer acceptance changes user installation state and is restricted to disposable GitHub-hosted Windows runners.'
}
if ([System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString().ToLowerInvariant() -ne $Architecture.Replace('x64', 'x64')) {
  throw 'Native runner architecture does not match the installer acceptance target.'
}
$Root = Split-Path -Parent $PSScriptRoot
$RunRoot = Join-Path $env:RUNNER_TEMP ('tauridium-winget-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $RunRoot | Out-Null
$Python = (Get-Command python.exe -ErrorAction Stop).Source
$Profile = Join-Path $env:APPDATA 'dev.brani.tauridium'
if (Test-Path -LiteralPath $Profile) { throw 'Refusing to use an existing application profile.' }

function Invoke-Native([string]$Command, [string[]]$Arguments, [int]$Timeout = 300000) {
  # All harness arguments are fixed switches, versions and generated runner paths.
  if (@($Arguments | Where-Object { $_ -match '["\r\n]' }).Count -ne 0) { throw 'Unexpected native argument.' }
  $Quoted = @($Arguments | ForEach-Object { if ($_ -match '\s') { '"' + $_ + '"' } else { $_ } }) -join ' '
  $Info = New-Object System.Diagnostics.ProcessStartInfo
  $Info.FileName = $Command
  $Info.Arguments = $Quoted
  $Info.UseShellExecute = $false
  $Info.RedirectStandardOutput = $true
  $Info.RedirectStandardError = $true
  $Process = New-Object System.Diagnostics.Process
  $Process.StartInfo = $Info
  try {
    if (-not $Process.Start()) { throw 'Native command failed to start.' }
    $Output = $Process.StandardOutput.ReadToEndAsync()
    $ErrorOutput = $Process.StandardError.ReadToEndAsync()
    if (-not $Process.WaitForExit($Timeout)) {
      Write-Host ('Native timeout before termination: ' + $Command)
      if (-not ('TauridiumInstallerWindow' -as [type])) {
        Add-Type -TypeDefinition @'
using System;
using System.Text;
using System.Collections.Generic;
using System.Runtime.InteropServices;
public static class TauridiumInstallerWindow {
  public delegate bool Callback(IntPtr window, IntPtr parameter);
  [DllImport("user32.dll")] public static extern bool EnumChildWindows(IntPtr parent, Callback callback, IntPtr parameter);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr window, StringBuilder text, int count);
  public static string[] Text(IntPtr parent) {
    var texts = new List<string>();
    EnumChildWindows(parent, (window, parameter) => {
      var text = new StringBuilder(512);
      GetWindowText(window, text, text.Capacity);
      if (text.Length > 0 && texts.Count < 30) texts.Add(text.ToString());
      return true;
    }, IntPtr.Zero);
    return texts.ToArray();
  }
}
'@
      }
      $Process.Refresh()
      if ($Process.MainWindowHandle -ne [IntPtr]::Zero) {
        Write-Host 'Blocked test process window text:'
        [TauridiumInstallerWindow]::Text($Process.MainWindowHandle) | Out-Host
      }
      Get-CimInstance Win32_Process | Where-Object { $_.ParentProcessId -eq $Process.Id -or $_.Name -match 'tauridium|[Ss]etup|[Ss]martscreen|[Cc]onsent|[Aa]pp[Rr]esolver|[Ee]xplorer' } | Select-Object Name, ProcessId, ParentProcessId | Format-Table | Out-Host
      Get-Process -Name '*tauridium*', '*setup*', 'smartscreen', 'consent', 'AppResolverUX' -ErrorAction SilentlyContinue | Select-Object Name, Id, MainWindowTitle | Format-Table | Out-Host
      $Process.Kill()
      if ($Output.Wait(1000)) { Write-Host $Output.Result }
      if ($ErrorOutput.Wait(1000)) { Write-Host $ErrorOutput.Result }
      throw ('Command timed out: ' + $Command + ' ' + ($Arguments -join ' '))
    }
    if (-not $Output.Wait(30000) -or -not $ErrorOutput.Wait(30000)) { throw 'Native output did not close.' }
    return @{ ExitCode=$Process.ExitCode; Output=$Output.Result; ErrorOutput=$ErrorOutput.Result }
  } finally { $Process.Dispose() }
}
function Invoke-Checked([string]$Command, [string[]]$Arguments, [int]$Timeout = 300000) {
  $Result = Invoke-Native $Command $Arguments $Timeout
  Write-Host $Result.Output
  Write-Host $Result.ErrorOutput
  if ($Result.ExitCode -ne 0) { throw ('Command failed with exit code ' + $Result.ExitCode + ': ' + $Command) }
}
function Get-Installation {
  $Rows = @()
  foreach ($Hive in @('HKCU:', 'HKLM:')) {
    foreach ($Path in @("$Hive\Software\Microsoft\Windows\CurrentVersion\Uninstall\*", "$Hive\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*")) {
      $Rows += @(Get-ItemProperty -Path $Path -ErrorAction SilentlyContinue | Where-Object { $_.PSObject.Properties['DisplayName'] -and $_.DisplayName -eq 'Tauridium' })
    }
  }
  return $Rows
}
function Assert-Installation([string]$ExpectedVersion) {
  $Rows = @(Get-Installation)
  if ($Rows.Count -ne 1) { throw ('Expected one installation, found ' + $Rows.Count) }
  $Row = $Rows[0]
  Write-Host ('ARP: ' + (@{Name=$Row.DisplayName; Publisher=$Row.Publisher; Version=$Row.DisplayVersion; Key=$Row.PSChildName; Path=$Row.PSPath; InstallLocation=$Row.InstallLocation} | ConvertTo-Json -Compress))
  if ($Row.PSPath -notlike '*HKEY_CURRENT_USER*') { throw 'Expected a per-user NSIS installation.' }
  if ($Row.DisplayVersion -ne $ExpectedVersion) { throw 'Unexpected ARP version.' }
  if ($Row.Publisher -ne 'brani') { throw ('Unexpected ARP publisher: ' + $Row.Publisher) }
  $script:InstalledExe = Join-Path $Row.InstallLocation 'tauridium.exe'
  if (-not (Test-Path -LiteralPath $script:InstalledExe -PathType Leaf)) { throw 'Installed executable is missing.' }
  $Probe = Join-Path $RunRoot ('build-info-' + [guid]::NewGuid().ToString('N') + '.json')
  Invoke-Checked $script:InstalledExe @('--build-info-file', $Probe)
  $Info = Get-Content -LiteralPath $Probe -Raw | ConvertFrom-Json
  $Target = if ($Architecture -eq 'x64') { 'x86_64-pc-windows-msvc' } else { 'aarch64-pc-windows-msvc' }
  if ($Info.version -ne $ExpectedVersion -or $Info.target -ne $Target -or $Info.buildMode -ne 'production') { throw 'Installed executable identity differs from its manifest.' }
}
function Get-WinGet {
  $Existing = Get-AppxPackage -Name Microsoft.DesktopAppInstaller
  if ($Existing) {
    $Executable = Join-Path $Existing.InstallLocation 'winget.exe'
    $Result = Invoke-Native $Executable @('--version') 20000
    $Text = $Result.Output.Trim().TrimStart('v')
    if ($Result.ExitCode -eq 0 -and [version]$Text -ge [version]'1.12.0') { return $Executable }
  }
  $Policy = Get-Content -LiteralPath (Join-Path $Root 'packaging/winget/client.json') -Raw | ConvertFrom-Json
  foreach ($Kind in @('bundle', 'dependencies')) {
    $Entry = $Policy.$Kind
    $Path = Join-Path $RunRoot $Entry.name
    Write-Host ('Downloading pinned WinGet ' + $Entry.name)
    Invoke-WebRequest -Uri ("https://github.com/microsoft/winget-cli/releases/download/v" + $Policy.version + '/' + $Entry.name) -OutFile $Path -UseBasicParsing
    if ((Get-Item -LiteralPath $Path).Length -ne $Entry.size -or (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Entry.sha256) { throw 'WinGet bootstrap size/hash mismatch.' }
  }
  $Dependencies = Join-Path $RunRoot 'dependencies'
  Expand-Archive -LiteralPath (Join-Path $RunRoot $Policy.dependencies.name) -DestinationPath $Dependencies
  $Packages = @(Get-ChildItem -LiteralPath (Join-Path $Dependencies $Architecture) -Filter '*.msix' -Recurse) + @(Get-ChildItem -LiteralPath (Join-Path $Dependencies $Architecture) -Filter '*.appx' -Recurse)
  if ($Packages.Count -eq 0) { throw 'No native WinGet dependencies in the pinned archive.' }
  Add-AppxPackage -Path (Join-Path $RunRoot $Policy.bundle.name) -DependencyPath @($Packages.FullName) -ForceApplicationShutdown
  $Package = Get-AppxPackage -Name Microsoft.DesktopAppInstaller
  if (-not $Package) { throw 'WinGet registration failed.' }
  $Command = Join-Path $Package.InstallLocation 'winget.exe'
  Invoke-Checked $Command @('--version')
  return $Command
}

function Assert-GuiStartup {
  $Process = [System.Diagnostics.Process]::Start($script:InstalledExe)
  try {
    $Deadline = [DateTime]::UtcNow.AddSeconds(45)
    do {
      Start-Sleep -Milliseconds 500
      $Process.Refresh()
      if ($Process.HasExited) { throw 'Installed application exited during GUI startup.' }
    } while ($Process.MainWindowHandle -eq [IntPtr]::Zero -and [DateTime]::UtcNow -lt $Deadline)
    if ($Process.MainWindowHandle -eq [IntPtr]::Zero -or -not $Process.Responding) { throw 'Installed application did not open a responsive window.' }
    Invoke-Checked -Command $script:InstalledExe -Arguments @()
    $Process.Refresh()
    if ($Process.HasExited -or @(Get-Process -Name tauridium -ErrorAction SilentlyContinue).Count -ne 1) { throw 'Second launch failed to preserve one primary application instance.' }
    Write-Host 'Installed GUI startup and second-instance activation passed.'
  } finally {
    if (-not $Process.HasExited) { $Process.Kill(); $Process.WaitForExit() }
    $Process.Dispose()
  }
}

if (@(Get-Installation).Count -ne 0) { throw 'Refusing to replace an existing Tauridium installation.' }
$Winget = $null
try {
  Set-Location -LiteralPath $Root
  Invoke-Checked $Python @('-c', "import sys; sys.path.insert(0, 'tools'); from security_tools import ensure_minisign; ensure_minisign()")
  foreach ($ReleaseVersion in @($PreviousVersion, $Version)) {
    $Lock = Join-Path $Root ('packaging/winget/releases/' + $ReleaseVersion + '.json')
    $Assets = Join-Path $RunRoot ('assets-' + $ReleaseVersion)
    $Manifest = Join-Path $RunRoot ('manifests/' + $ReleaseVersion)
    Invoke-Checked $Python @('tools/winget.py', 'fetch', '--lock', $Lock, '--assets-dir', $Assets)
    Invoke-Checked $Python @('tools/winget.py', 'prepare', '--lock', $Lock, '--assets-dir', $Assets, '--output', $Manifest)
  }
  # Separate signed installer execution from the package manager's ShellExecute
  # path, so acceptance failures identify the actual boundary.
  $DirectInstaller = Join-Path $RunRoot ('assets-' + $Version + '/tauridium-' + $Version + '-windows-' + $Architecture + '-setup.exe')
  Write-Host 'Testing verified installer directly before WinGet lifecycle.'
  Invoke-Checked $DirectInstaller @('/S') 45000
  Assert-Installation $Version
  $DirectUninstaller = Join-Path (Split-Path -Parent $script:InstalledExe) 'uninstall.exe'
  Invoke-Checked $DirectUninstaller @('/S')
  if (@(Get-Installation).Count -ne 0) { throw 'Direct installer cleanup left ARP registration.' }
  $Winget = Get-WinGet
  # Local manifests cannot be combined with --source. Keep unrelated catalogues
  # explicit in this disposable user so their REST startup cannot block an
  # installer test. The community application source remains available.
  $Sources = Invoke-Native $Winget @('source', 'list', '--disable-interactivity')
  if ($Sources.ExitCode -ne 0) { throw 'Unable to inspect disposable WinGet sources.' }
  foreach ($Name in @('msstore', 'winget-font')) {
    if ($Sources.Output -match ('(?m)^\s*' + [regex]::Escape($Name) + '\s')) {
      Invoke-Checked $Winget @('source', 'edit', '--name', $Name, '--explicit', 'true', '--disable-interactivity')
    }
  }
  Invoke-Checked $Winget @('settings', '--enable', 'LocalManifestFiles', '--disable-interactivity')
  foreach ($ReleaseVersion in @($PreviousVersion, $Version)) {
    Invoke-Checked $Winget @('validate', '--manifest', (Join-Path $RunRoot ('manifests/' + $ReleaseVersion)), '--disable-interactivity')
  }
  $Common = @('--architecture', $Architecture, '--scope', 'user', '--silent', '--accept-package-agreements', '--accept-source-agreements', '--disable-interactivity')
  Invoke-Checked $Winget (@('install', '--manifest', (Join-Path $RunRoot ('manifests/' + $PreviousVersion))) + $Common)
  Assert-Installation $PreviousVersion
  New-Item -ItemType Directory -Path $Profile | Out-Null
  $Marker = Join-Path $Profile 'winget-ci-persistence.marker'
  'retain synthetic data' | Set-Content -LiteralPath $Marker -Encoding utf8
  Invoke-Checked $Winget (@('upgrade', '--manifest', (Join-Path $RunRoot ('manifests/' + $Version))) + $Common)
  Assert-Installation $Version
  Invoke-Checked $Winget @('list', '--name', 'Tauridium', '--exact', '--source', 'winget', '--accept-source-agreements', '--disable-interactivity')
  Invoke-Checked $Winget @('uninstall', '--name', 'Tauridium', '--exact', '--source', 'winget', '--scope', 'user', '--silent', '--accept-source-agreements', '--disable-interactivity')
  if (@(Get-Installation).Count -ne 0 -or -not (Test-Path -LiteralPath $Marker)) { throw 'Uninstall did not preserve data or left ARP registration.' }
  Invoke-Checked $Winget (@('install', '--manifest', (Join-Path $RunRoot ('manifests/' + $Version))) + $Common)
  Assert-Installation $Version
  if ((Get-Content -LiteralPath $Marker -Raw).Trim() -ne 'retain synthetic data') { throw 'Reinstall modified application data.' }
  Assert-GuiStartup
  Invoke-Checked $Winget @('uninstall', '--name', 'Tauridium', '--exact', '--source', 'winget', '--scope', 'user', '--silent', '--accept-source-agreements', '--disable-interactivity')
  Invoke-Checked $Winget (@('install', '--manifest', (Join-Path $RunRoot ('manifests/' + $PreviousVersion))) + $Common)
  Assert-Installation $PreviousVersion
  # Exercise the updater's delivered NSIS /UPDATE installer path, without
  # pretending this is a UI-driven end-to-end updater test.
  $UpdaterInstaller = Join-Path $RunRoot ('assets-' + $Version + '/tauridium-' + $Version + '-windows-' + $Architecture + '-setup.exe')
  Invoke-Checked $UpdaterInstaller @('/S', '/UPDATE')
  Assert-Installation $Version
  Invoke-Checked $Winget @('list', '--name', 'Tauridium', '--exact', '--source', 'winget', '--accept-source-agreements', '--disable-interactivity')
  if (-not (Test-Path -LiteralPath $Marker)) { throw 'Native update removed application data.' }
  Write-Host ('WinGet native lifecycle passed on ' + $Architecture)
} catch {
  # Bounded diagnostics from an isolated fixture only. Never publish profiles or
  # recursively collect the runner's logs/environment.
  Get-Process -Name '*tauridium*', '*setup*', 'winget' -ErrorAction SilentlyContinue | Select-Object Name, Id | Format-Table | Out-Host
  $LogDirectory = Join-Path $env:LOCALAPPDATA 'Packages/Microsoft.DesktopAppInstaller_8wekyb3d8bbwe/LocalState/DiagOutputDir'
  if (Test-Path -LiteralPath $LogDirectory) {
    $Logs = @(Get-ChildItem -LiteralPath $LogDirectory -Filter 'WinGet-*.log' | Sort-Object LastWriteTime -Descending | Select-Object -First 2)
    foreach ($Log in $Logs) {
      Get-Content -LiteralPath $Log.FullName -Tail 100 | Where-Object { $_ -match 'Installer|Download|Starting|Executing|Source|Waiting|error|Error' } | Select-Object -Last 25 | Out-Host
    }
  }
  throw
} finally {
  if ($Winget -and @(Get-Installation).Count -eq 1) {
    Invoke-Checked $Winget @('uninstall', '--name', 'Tauridium', '--exact', '--source', 'winget', '--scope', 'user', '--silent', '--accept-source-agreements', '--disable-interactivity')
  }
  # This directory was absent at entry and holds only this disposable user's fixture.
  if (Test-Path -LiteralPath $Profile) { Remove-Item -LiteralPath $Profile -Recurse -Force }
}
