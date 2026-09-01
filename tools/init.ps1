[CmdletBinding()]
param(
  [switch]$NativeOnly,
  [switch]$NoSystemChanges,
  [switch]$SelfTest
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$InitVersion = "0.7.2"
$Root = Split-Path -Parent $PSScriptRoot
$VsConfig = Join-Path $Root ".vsconfig"

try {
  Set-Location -LiteralPath $Root

  # Release identity is checked before any system or dependency mutation.
  $PackagePath = Join-Path $Root "package.json"
  if (-not (Test-Path -LiteralPath $PackagePath)) {
    throw "package.json is missing; extract Tauridium into a new empty directory"
  }
  $Package = Get-Content -LiteralPath $PackagePath -Raw | ConvertFrom-Json
  if ($Package.version -ne $InitVersion) {
    throw ("initializer version {0} does not match package.json version {1}; extract the release into a new empty directory instead of overlaying releases" -f $InitVersion, $Package.version)
  }

  Write-Host "Tauridium initializer $InitVersion (Windows PowerShell)."

  # The self-test intentionally uses only built-in PowerShell/.NET facilities.
  # init.ps1 itself contains no user-defined functions and performs no indirect
  # bootstrap dispatch, eliminating the Windows PowerShell lookup failure seen
  # in Tauridium 0.2.0 and the script-block dispatch failure seen in 0.2.1.
  if ($SelfTest) {
    if ($PSVersionTable.PSVersion.Major -lt 5) {
      throw ("Windows PowerShell 5.1 or newer is required; detected {0}" -f $PSVersionTable.PSVersion)
    }

    $Tokens = $null
    $ParseErrors = $null
    [void][System.Management.Automation.Language.Parser]::ParseFile(
      $PSCommandPath,
      [ref]$Tokens,
      [ref]$ParseErrors
    )
    if ($null -ne $ParseErrors -and $ParseErrors.Count -ne 0) {
      $FirstParseError = $ParseErrors | Select-Object -First 1
      throw ("PowerShell parser rejected tools/init.ps1: {0}" -f $FirstParseError.Message)
    }

    $PythonRunnerPath = Join-Path $Root "tools\python.ps1"
    if (-not (Test-Path -LiteralPath $PythonRunnerPath)) {
      throw "tools/python.ps1 is missing from the Tauridium source tree"
    }
    $PythonRunnerTokens = $null
    $PythonRunnerParseErrors = $null
    [void][System.Management.Automation.Language.Parser]::ParseFile(
      $PythonRunnerPath,
      [ref]$PythonRunnerTokens,
      [ref]$PythonRunnerParseErrors
    )
    if ($null -ne $PythonRunnerParseErrors -and $PythonRunnerParseErrors.Count -ne 0) {
      $FirstPythonRunnerParseError = $PythonRunnerParseErrors | Select-Object -First 1
      throw ("PowerShell parser rejected tools/python.ps1: {0}" -f $FirstPythonRunnerParseError.Message)
    }

    if (-not (Test-Path -LiteralPath $VsConfig)) {
      throw ".vsconfig is missing from the Tauridium source tree"
    }
    $VsConfiguration = Get-Content -LiteralPath $VsConfig -Raw | ConvertFrom-Json
    $RequiredVsComponents = @(
      "Microsoft.VisualStudio.Component.VC.Tools.x86.x64",
      "Microsoft.VisualStudio.Component.VC.Tools.ARM64",
      "Microsoft.VisualStudio.Component.Windows11SDK.26100"
    )
    foreach ($RequiredVsComponent in $RequiredVsComponents) {
      if ($VsConfiguration.components -notcontains $RequiredVsComponent) {
        throw (".vsconfig is missing required component: {0}" -f $RequiredVsComponent)
      }
    }

    # Verify that an expected native-command failure cannot be promoted to a
    # terminating PowerShell error. Windows PowerShell 5.1 converts redirected
    # native stderr into its error stream, which previously aborted py -3 probes.
    $SavedErrorActionPreference = $ErrorActionPreference
    try {
      $ErrorActionPreference = "SilentlyContinue"
      & cmd.exe /d /c "echo Tauridium-native-probe-self-test 1>&2 & exit /b 7" *> $null
      $NativeProbeExitCode = $LASTEXITCODE
    } finally {
      $ErrorActionPreference = $SavedErrorActionPreference
    }
    if ($NativeProbeExitCode -ne 7) {
      throw ("native probe isolation self-test returned exit code {0}, expected 7" -f $NativeProbeExitCode)
    }

    Write-Host "Tauridium Windows PowerShell bootstrap self-test passed."
    exit 0
  }

  $WindowsVersion = [Environment]::OSVersion.Version
  if ($WindowsVersion.Major -lt 10 -or $WindowsVersion.Build -lt 22000) {
    throw ("native PowerShell initialization requires Windows 11 (build 22000 or newer); detected {0}" -f $WindowsVersion)
  }

  # Reload persisted Windows PATH values before prerequisite discovery. Each
  # just recipe starts a fresh child PowerShell that otherwise inherits the
  # parent shell's stale PATH after a prior package-manager installation.
  $MachinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
  $UserPath = [Environment]::GetEnvironmentVariable("Path", "User")
  $PathParts = @()
  if ($MachinePath) { $PathParts += $MachinePath }
  if ($UserPath) { $PathParts += $UserPath }
  if ($env:Path) { $PathParts += $env:Path }
  $DefaultScoopShims = Join-Path $HOME "scoop\shims"
  if (Test-Path -LiteralPath $DefaultScoopShims) { $PathParts += $DefaultScoopShims }
  if (-not [string]::IsNullOrWhiteSpace($env:SCOOP)) {
    $ConfiguredScoopShims = Join-Path $env:SCOOP "shims"
    if (Test-Path -LiteralPath $ConfiguredScoopShims) { $PathParts += $ConfiguredScoopShims }
  }
  $CargoBin = Join-Path $HOME ".cargo\bin"
  if (Test-Path -LiteralPath $CargoBin) { $PathParts += $CargoBin }
  $env:Path = $PathParts -join ";"

  $ScoopAvailable = $null -ne (Get-Command -Name "scoop" -ErrorAction SilentlyContinue)
  $WingetAvailable = $null -ne (Get-Command -Name "winget.exe" -ErrorAction SilentlyContinue)
  if ($ScoopAvailable) {
    Write-Host "+ Windows package manager: Scoop preferred"
  } elseif ($WingetAvailable) {
    Write-Host "+ Windows package manager: winget fallback"
  }

  # ---------------------------------------------------------------------------
  # Microsoft Visual C++ Build Tools + Windows 11 SDK
  # ---------------------------------------------------------------------------
  $VsWhereCandidates = @()
  if (-not [string]::IsNullOrWhiteSpace(${env:ProgramFiles(x86)})) {
    $VsWhereCandidates += Join-Path ${env:ProgramFiles(x86)} "Microsoft Visual Studio\Installer\vswhere.exe"
  }
  if (-not [string]::IsNullOrWhiteSpace($env:ProgramFiles)) {
    $VsWhereCandidates += Join-Path $env:ProgramFiles "Microsoft Visual Studio\Installer\vswhere.exe"
  }

  $VsWhere = $null
  foreach ($VsWhereCandidate in $VsWhereCandidates) {
    if ($VsWhereCandidate -and (Test-Path -LiteralPath $VsWhereCandidate)) {
      $VsWhere = $VsWhereCandidate
      break
    }
  }

  $ProcessorArchitecture = if (
    $env:PROCESSOR_ARCHITECTURE -eq "ARM64" -or
    $env:PROCESSOR_ARCHITEW6432 -eq "ARM64"
  ) { "ARM64" } else { "x86.x64" }
  $MsvcComponent = if ($ProcessorArchitecture -eq "ARM64") {
    "Microsoft.VisualStudio.Component.VC.Tools.ARM64"
  } else {
    "Microsoft.VisualStudio.Component.VC.Tools.x86.x64"
  }

  $MsvcInstalled = $false
  if (-not [string]::IsNullOrWhiteSpace($VsWhere)) {
    $SavedErrorActionPreference = $ErrorActionPreference
    try {
      $ErrorActionPreference = "SilentlyContinue"
      $MsvcInstallation = & $VsWhere -latest -products * -requires $MsvcComponent -property installationPath 2>$null
      $MsvcProbeExitCode = $LASTEXITCODE
    } finally {
      $ErrorActionPreference = $SavedErrorActionPreference
    }
    if ($MsvcProbeExitCode -eq 0 -and -not [string]::IsNullOrWhiteSpace(($MsvcInstallation | Out-String))) {
      $MsvcInstalled = $true
    }
  }

  if (-not $MsvcInstalled) {
    if (-not (Test-Path -LiteralPath $VsConfig)) {
      throw ".vsconfig is missing from the Tauridium source tree"
    }
    if ($NoSystemChanges) {
      throw "Microsoft C++ Build Tools are missing and -NoSystemChanges was requested"
    }
    if ($null -eq (Get-Command -Name "winget.exe" -ErrorAction SilentlyContinue)) {
      throw 'winget.exe is required for automatic Windows prerequisite installation; install/update Microsoft App Installer, then rerun just init'
    }

    $VsOverride = ('--wait --passive --norestart --config "{0}"' -f $VsConfig)
    $VsPackageInstalled = $false
    foreach ($VsPackageId in @("Microsoft.VisualStudio.BuildTools", "Microsoft.VisualStudio.2022.BuildTools")) {
      $SavedErrorActionPreference = $ErrorActionPreference
      try {
        $ErrorActionPreference = "SilentlyContinue"
        & winget.exe show -e --id $VsPackageId --source winget *> $null
        $WingetShowExitCode = $LASTEXITCODE
      } finally {
        $ErrorActionPreference = $SavedErrorActionPreference
      }
      if ($WingetShowExitCode -ne 0) {
        continue
      }
      Write-Host ("+ winget.exe install {0}" -f $VsPackageId)
      & winget.exe install -e --id $VsPackageId --source winget --accept-source-agreements --accept-package-agreements --override $VsOverride
      if ($LASTEXITCODE -ne 0) {
        throw ("winget.exe failed with exit code {0} while installing {1}" -f $LASTEXITCODE, $VsPackageId)
      }
      $VsPackageInstalled = $true
      break
    }
    if (-not $VsPackageInstalled) {
      throw "no supported Visual Studio Build Tools package was found in the winget source"
    }

    # Rediscover vswhere after Visual Studio Installer/Build Tools installation.
    $VsWhere = $null
    foreach ($VsWhereCandidate in $VsWhereCandidates) {
      if ($VsWhereCandidate -and (Test-Path -LiteralPath $VsWhereCandidate)) {
        $VsWhere = $VsWhereCandidate
        break
      }
    }
    if ([string]::IsNullOrWhiteSpace($VsWhere)) {
      throw 'Microsoft C++ Build Tools installation completed but vswhere.exe was not detected; restart Windows if Visual Studio Installer requested it, then rerun just init'
    }
    $SavedErrorActionPreference = $ErrorActionPreference
    try {
      $ErrorActionPreference = "SilentlyContinue"
      $MsvcInstallation = & $VsWhere -latest -products * -requires $MsvcComponent -property installationPath 2>$null
      $MsvcProbeExitCode = $LASTEXITCODE
    } finally {
      $ErrorActionPreference = $SavedErrorActionPreference
    }
    if ($MsvcProbeExitCode -ne 0 -or [string]::IsNullOrWhiteSpace(($MsvcInstallation | Out-String))) {
      throw 'Microsoft C++ Build Tools installation completed but the required MSVC component was not detected; restart Windows if Visual Studio Installer requested it, then rerun just init'
    }
  }
  Write-Host "+ Microsoft C++ Build Tools: available"

  # ---------------------------------------------------------------------------
  # Microsoft Edge WebView2 Runtime
  # ---------------------------------------------------------------------------
  $WebView2Installed = $false
  $WebViewRegistryRoots = @(
    "HKLM:\SOFTWARE\Microsoft\EdgeUpdate\Clients",
    "HKLM:\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients",
    "HKCU:\SOFTWARE\Microsoft\EdgeUpdate\Clients"
  )
  foreach ($WebViewRegistryRoot in $WebViewRegistryRoots) {
    if ($WebView2Installed -or -not (Test-Path $WebViewRegistryRoot)) {
      continue
    }
    foreach ($WebViewClient in Get-ChildItem -Path $WebViewRegistryRoot -ErrorAction SilentlyContinue) {
      $WebViewProperties = Get-ItemProperty -Path $WebViewClient.PSPath -ErrorAction SilentlyContinue
      if ($null -ne $WebViewProperties -and "$($WebViewProperties.name)" -match "WebView2") {
        $WebView2Installed = $true
        break
      }
    }
  }

  $WebViewRoots = @()
  if (-not [string]::IsNullOrWhiteSpace(${env:ProgramFiles(x86)})) {
    $WebViewRoots += Join-Path ${env:ProgramFiles(x86)} "Microsoft\EdgeWebView\Application"
  }
  if (-not [string]::IsNullOrWhiteSpace($env:ProgramFiles)) {
    $WebViewRoots += Join-Path $env:ProgramFiles "Microsoft\EdgeWebView\Application"
  }
  if (-not [string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) {
    $WebViewRoots += Join-Path $env:LOCALAPPDATA "Microsoft\EdgeWebView\Application"
  }
  if (-not $WebView2Installed) {
    foreach ($WebViewRoot in $WebViewRoots) {
      if (-not $WebViewRoot -or -not (Test-Path -LiteralPath $WebViewRoot)) {
        continue
      }
      $WebViewExecutable = Get-ChildItem -LiteralPath $WebViewRoot -Filter "msedgewebview2.exe" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
      if ($null -ne $WebViewExecutable) {
        $WebView2Installed = $true
        break
      }
    }
  }

  if (-not $WebView2Installed) {
    if ($NoSystemChanges) {
      throw "Windows prerequisite Microsoft.EdgeWebView2Runtime is missing and -NoSystemChanges was requested"
    }
    if ($null -eq (Get-Command -Name "winget.exe" -ErrorAction SilentlyContinue)) {
      throw 'winget.exe is required for automatic Windows prerequisite installation; install/update Microsoft App Installer, then rerun just init'
    }
    Write-Host "+ winget.exe install Microsoft.EdgeWebView2Runtime"
    & winget.exe install -e --id Microsoft.EdgeWebView2Runtime --source winget --accept-source-agreements --accept-package-agreements
    if ($LASTEXITCODE -ne 0) {
      throw ("winget.exe failed with exit code {0} while installing Microsoft.EdgeWebView2Runtime" -f $LASTEXITCODE)
    }
  }
  Write-Host "+ Microsoft Edge WebView2 Runtime: available"

  # ---------------------------------------------------------------------------
  # Windows VBSCRIPT optional feature used by Tauri MSI bundling
  # ---------------------------------------------------------------------------
  $VbScriptEnabled = $true
  if ($null -ne (Get-Command -Name "dism.exe" -ErrorAction SilentlyContinue)) {
    $SavedErrorActionPreference = $ErrorActionPreference
    try {
      $ErrorActionPreference = "SilentlyContinue"
      $DismOutput = & dism.exe /Online /English /Get-FeatureInfo /FeatureName:VBSCRIPT 2>$null | Out-String
      $DismProbeExitCode = $LASTEXITCODE
    } finally {
      $ErrorActionPreference = $SavedErrorActionPreference
    }
    if ($DismProbeExitCode -eq 0) {
      $VbScriptEnabled = $DismOutput -match "State\s*:\s*Enabled"
    }
  }
  if (-not $VbScriptEnabled) {
    if ($NoSystemChanges) {
      throw "Windows VBSCRIPT optional feature is disabled; Tauri needs it to build MSI bundles"
    }
    Write-Host "+ enabling Windows VBSCRIPT optional feature for MSI bundling"
    $DismProcess = Start-Process -FilePath "dism.exe" -Verb RunAs -Wait -PassThru -ArgumentList @(
      "/Online", "/Enable-Feature", "/FeatureName:VBSCRIPT", "/All", "/NoRestart"
    )
    if ($DismProcess.ExitCode -notin @(0, 3010)) {
      throw ("enabling VBSCRIPT failed with exit code {0}" -f $DismProcess.ExitCode)
    }
    $SavedErrorActionPreference = $ErrorActionPreference
    try {
      $ErrorActionPreference = "SilentlyContinue"
      $DismOutput = & dism.exe /Online /English /Get-FeatureInfo /FeatureName:VBSCRIPT 2>$null | Out-String
      $DismProbeExitCode = $LASTEXITCODE
    } finally {
      $ErrorActionPreference = $SavedErrorActionPreference
    }
    if ($DismProbeExitCode -eq 0 -and $DismOutput -notmatch "State\s*:\s*Enabled") {
      throw 'VBSCRIPT was enabled but is not active yet; restart Windows, then rerun just init'
    }
  }
  Write-Host "+ Windows VBSCRIPT feature: available"

  if (-not $NativeOnly) {
    # -------------------------------------------------------------------------
    # Node.js + npm
    # -------------------------------------------------------------------------
    $NodeReady = $false
    $NodeCommand = Get-Command -Name "node.exe" -ErrorAction SilentlyContinue
    $NpmCommand = Get-Command -Name "npm.cmd" -ErrorAction SilentlyContinue
    if ($null -ne $NodeCommand -and $null -ne $NpmCommand) {
      $SavedErrorActionPreference = $ErrorActionPreference
      try {
        $ErrorActionPreference = "SilentlyContinue"
        $NodeVersion = & node.exe --version 2>$null
        $NodeProbeExitCode = $LASTEXITCODE
      } finally {
        $ErrorActionPreference = $SavedErrorActionPreference
      }
      if ($NodeProbeExitCode -eq 0 -and $NodeVersion -match '^v(\d+)\.' -and [int]$Matches[1] -ge 20) {
        $NodeReady = $true
      }
    }

    if (-not $NodeReady) {
      if ($NoSystemChanges) {
        throw "Windows prerequisite Node.js 20 or newer is missing and -NoSystemChanges was requested"
      }

      $NodeScoopAttempted = $false
      if ($ScoopAvailable) {
        $NodeScoopAttempted = $true
        Write-Host "+ scoop install nodejs-lts"
        $SavedErrorActionPreference = $ErrorActionPreference
        try {
          $ErrorActionPreference = "Continue"
          & scoop install nodejs-lts
        } catch {
          Write-Warning ("Scoop could not install nodejs-lts: {0}" -f $_.Exception.Message)
        } finally {
          $ErrorActionPreference = $SavedErrorActionPreference
        }

        $MachinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
        $UserPath = [Environment]::GetEnvironmentVariable("Path", "User")
        $PathParts = @()
        if ($MachinePath) { $PathParts += $MachinePath }
        if ($UserPath) { $PathParts += $UserPath }
        if ($env:Path) { $PathParts += $env:Path }
        if (Test-Path -LiteralPath $DefaultScoopShims) { $PathParts += $DefaultScoopShims }
        if (-not [string]::IsNullOrWhiteSpace($env:SCOOP)) {
          $ConfiguredScoopShims = Join-Path $env:SCOOP "shims"
          if (Test-Path -LiteralPath $ConfiguredScoopShims) { $PathParts += $ConfiguredScoopShims }
        }
        if (Test-Path -LiteralPath $CargoBin) { $PathParts += $CargoBin }
        $env:Path = $PathParts -join ";"

        $NodeCommand = Get-Command -Name "node.exe" -ErrorAction SilentlyContinue
        $NpmCommand = Get-Command -Name "npm.cmd" -ErrorAction SilentlyContinue
        if ($null -ne $NodeCommand -and $null -ne $NpmCommand) {
          $SavedErrorActionPreference = $ErrorActionPreference
          try {
            $ErrorActionPreference = "SilentlyContinue"
            $NodeVersion = & node.exe --version 2>$null
            $NodeProbeExitCode = $LASTEXITCODE
          } finally {
            $ErrorActionPreference = $SavedErrorActionPreference
          }
          if ($NodeProbeExitCode -eq 0 -and $NodeVersion -match '^v(\d+)\.' -and [int]$Matches[1] -ge 20) {
            $NodeReady = $true
          }
        }
      }

      if (-not $NodeReady -and $WingetAvailable) {
        Write-Host "+ winget.exe install OpenJS.NodeJS.LTS (fallback)"
        $SavedErrorActionPreference = $ErrorActionPreference
        try {
          $ErrorActionPreference = "SilentlyContinue"
          & winget.exe install -e --id OpenJS.NodeJS.LTS --source winget --accept-source-agreements --accept-package-agreements
          $NodeWingetExitCode = $LASTEXITCODE
        } finally {
          $ErrorActionPreference = $SavedErrorActionPreference
        }

        $MachinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
        $UserPath = [Environment]::GetEnvironmentVariable("Path", "User")
        $PathParts = @()
        if ($MachinePath) { $PathParts += $MachinePath }
        if ($UserPath) { $PathParts += $UserPath }
        if ($env:Path) { $PathParts += $env:Path }
        if (Test-Path -LiteralPath $DefaultScoopShims) { $PathParts += $DefaultScoopShims }
        if (-not [string]::IsNullOrWhiteSpace($env:SCOOP)) {
          $ConfiguredScoopShims = Join-Path $env:SCOOP "shims"
          if (Test-Path -LiteralPath $ConfiguredScoopShims) { $PathParts += $ConfiguredScoopShims }
        }
        if (Test-Path -LiteralPath $CargoBin) { $PathParts += $CargoBin }
        $env:Path = $PathParts -join ";"

        $NodeCommand = Get-Command -Name "node.exe" -ErrorAction SilentlyContinue
        $NpmCommand = Get-Command -Name "npm.cmd" -ErrorAction SilentlyContinue
        if ($null -ne $NodeCommand -and $null -ne $NpmCommand) {
          $SavedErrorActionPreference = $ErrorActionPreference
          try {
            $ErrorActionPreference = "SilentlyContinue"
            $NodeVersion = & node.exe --version 2>$null
            $NodeProbeExitCode = $LASTEXITCODE
          } finally {
            $ErrorActionPreference = $SavedErrorActionPreference
          }
          if ($NodeProbeExitCode -eq 0 -and $NodeVersion -match '^v(\d+)\.' -and [int]$Matches[1] -ge 20) {
            $NodeReady = $true
          }
        }
      }

      if (-not $NodeReady) {
        if (-not $ScoopAvailable -and -not $WingetAvailable) {
          throw "Node.js is missing and neither Scoop nor winget is available for installation"
        }
        if ($null -ne $NodeWingetExitCode) {
          throw ("Node.js installation did not provide a usable Node.js 20+ runtime; winget exit code was {0}" -f $NodeWingetExitCode)
        }
        if ($NodeScoopAttempted) {
          throw "Scoop did not provide a usable Node.js 20+ runtime and winget fallback was unavailable"
        }
        throw "Node.js installation did not provide a usable Node.js 20+ runtime"
      }
    }
    Write-Host ("+ Node.js: {0}" -f $NodeVersion)

    # -------------------------------------------------------------------------
    # Python 3
    # -------------------------------------------------------------------------
    $PythonRunnerPath = Join-Path $Root "tools\python.ps1"
    $SavedErrorActionPreference = $ErrorActionPreference
    try {
      $ErrorActionPreference = "SilentlyContinue"
      & powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File $PythonRunnerPath --version *> $null
      $PythonProbeExitCode = $LASTEXITCODE
    } finally {
      $ErrorActionPreference = $SavedErrorActionPreference
    }
    $PythonReady = $PythonProbeExitCode -eq 0

    if (-not $PythonReady) {
      if ($NoSystemChanges) {
        throw "Windows prerequisite Python 3 is missing and -NoSystemChanges was requested"
      }

      $PythonScoopAttempted = $false
      if ($ScoopAvailable) {
        $PythonScoopAttempted = $true
        Write-Host "+ scoop install python"
        $SavedErrorActionPreference = $ErrorActionPreference
        try {
          $ErrorActionPreference = "Continue"
          & scoop install python
        } catch {
          Write-Warning ("Scoop could not install python: {0}" -f $_.Exception.Message)
        } finally {
          $ErrorActionPreference = $SavedErrorActionPreference
        }

        $MachinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
        $UserPath = [Environment]::GetEnvironmentVariable("Path", "User")
        $PathParts = @()
        if ($MachinePath) { $PathParts += $MachinePath }
        if ($UserPath) { $PathParts += $UserPath }
        if ($env:Path) { $PathParts += $env:Path }
        if (Test-Path -LiteralPath $DefaultScoopShims) { $PathParts += $DefaultScoopShims }
        if (-not [string]::IsNullOrWhiteSpace($env:SCOOP)) {
          $ConfiguredScoopShims = Join-Path $env:SCOOP "shims"
          if (Test-Path -LiteralPath $ConfiguredScoopShims) { $PathParts += $ConfiguredScoopShims }
        }
        if (Test-Path -LiteralPath $CargoBin) { $PathParts += $CargoBin }
        $env:Path = $PathParts -join ";"

        $SavedErrorActionPreference = $ErrorActionPreference
        try {
          $ErrorActionPreference = "SilentlyContinue"
          & powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File $PythonRunnerPath --version *> $null
          $PythonProbeExitCode = $LASTEXITCODE
        } finally {
          $ErrorActionPreference = $SavedErrorActionPreference
        }
        $PythonReady = $PythonProbeExitCode -eq 0
      }

      if (-not $PythonReady -and $WingetAvailable) {
        Write-Host "+ winget.exe install Python.Python.3.13 (fallback)"
        $SavedErrorActionPreference = $ErrorActionPreference
        try {
          $ErrorActionPreference = "SilentlyContinue"
          & winget.exe install -e --id Python.Python.3.13 --source winget --accept-source-agreements --accept-package-agreements
          $PythonWingetExitCode = $LASTEXITCODE
        } finally {
          $ErrorActionPreference = $SavedErrorActionPreference
        }

        $MachinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
        $UserPath = [Environment]::GetEnvironmentVariable("Path", "User")
        $PathParts = @()
        if ($MachinePath) { $PathParts += $MachinePath }
        if ($UserPath) { $PathParts += $UserPath }
        if ($env:Path) { $PathParts += $env:Path }
        if (Test-Path -LiteralPath $DefaultScoopShims) { $PathParts += $DefaultScoopShims }
        if (-not [string]::IsNullOrWhiteSpace($env:SCOOP)) {
          $ConfiguredScoopShims = Join-Path $env:SCOOP "shims"
          if (Test-Path -LiteralPath $ConfiguredScoopShims) { $PathParts += $ConfiguredScoopShims }
        }
        if (Test-Path -LiteralPath $CargoBin) { $PathParts += $CargoBin }
        $env:Path = $PathParts -join ";"

        $SavedErrorActionPreference = $ErrorActionPreference
        try {
          $ErrorActionPreference = "SilentlyContinue"
          & powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File $PythonRunnerPath --version *> $null
          $PythonProbeExitCode = $LASTEXITCODE
        } finally {
          $ErrorActionPreference = $SavedErrorActionPreference
        }
        $PythonReady = $PythonProbeExitCode -eq 0
      }

      if (-not $PythonReady) {
        if (-not $ScoopAvailable -and -not $WingetAvailable) {
          throw "Python 3 is missing and neither Scoop nor winget is available for installation"
        }
        if ($null -ne $PythonWingetExitCode) {
          throw ("Python installation did not provide a usable Python 3 runtime; winget exit code was {0}" -f $PythonWingetExitCode)
        }
        if ($PythonScoopAttempted) {
          throw "Scoop did not provide a usable Python 3 runtime and winget fallback was unavailable"
        }
        throw "Python installation did not provide a usable Python 3 runtime"
      }
    }
    Write-Host "+ Python 3: available"

    # -------------------------------------------------------------------------
    # Git
    # -------------------------------------------------------------------------
    $GitReady = $null -ne (Get-Command -Name "git.exe" -ErrorAction SilentlyContinue)
    if (-not $GitReady) {
      if ($NoSystemChanges) {
        throw "Windows prerequisite Git is missing and -NoSystemChanges was requested"
      }

      $GitScoopAttempted = $false
      if ($ScoopAvailable) {
        $GitScoopAttempted = $true
        Write-Host "+ scoop install git"
        $SavedErrorActionPreference = $ErrorActionPreference
        try {
          $ErrorActionPreference = "Continue"
          & scoop install git
        } catch {
          Write-Warning ("Scoop could not install git: {0}" -f $_.Exception.Message)
        } finally {
          $ErrorActionPreference = $SavedErrorActionPreference
        }

        $MachinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
        $UserPath = [Environment]::GetEnvironmentVariable("Path", "User")
        $PathParts = @()
        if ($MachinePath) { $PathParts += $MachinePath }
        if ($UserPath) { $PathParts += $UserPath }
        if ($env:Path) { $PathParts += $env:Path }
        if (Test-Path -LiteralPath $DefaultScoopShims) { $PathParts += $DefaultScoopShims }
        if (-not [string]::IsNullOrWhiteSpace($env:SCOOP)) {
          $ConfiguredScoopShims = Join-Path $env:SCOOP "shims"
          if (Test-Path -LiteralPath $ConfiguredScoopShims) { $PathParts += $ConfiguredScoopShims }
        }
        if (Test-Path -LiteralPath $CargoBin) { $PathParts += $CargoBin }
        $env:Path = $PathParts -join ";"
        $GitReady = $null -ne (Get-Command -Name "git.exe" -ErrorAction SilentlyContinue)
      }

      if (-not $GitReady -and $WingetAvailable) {
        Write-Host "+ winget.exe install Git.Git (fallback)"
        $SavedErrorActionPreference = $ErrorActionPreference
        try {
          $ErrorActionPreference = "SilentlyContinue"
          & winget.exe install -e --id Git.Git --source winget --accept-source-agreements --accept-package-agreements
          $GitWingetExitCode = $LASTEXITCODE
        } finally {
          $ErrorActionPreference = $SavedErrorActionPreference
        }

        $MachinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
        $UserPath = [Environment]::GetEnvironmentVariable("Path", "User")
        $PathParts = @()
        if ($MachinePath) { $PathParts += $MachinePath }
        if ($UserPath) { $PathParts += $UserPath }
        if ($env:Path) { $PathParts += $env:Path }
        if (Test-Path -LiteralPath $DefaultScoopShims) { $PathParts += $DefaultScoopShims }
        if (-not [string]::IsNullOrWhiteSpace($env:SCOOP)) {
          $ConfiguredScoopShims = Join-Path $env:SCOOP "shims"
          if (Test-Path -LiteralPath $ConfiguredScoopShims) { $PathParts += $ConfiguredScoopShims }
        }
        if (Test-Path -LiteralPath $CargoBin) { $PathParts += $CargoBin }
        $env:Path = $PathParts -join ";"
        $GitReady = $null -ne (Get-Command -Name "git.exe" -ErrorAction SilentlyContinue)
      }

      if (-not $GitReady) {
        if (-not $ScoopAvailable -and -not $WingetAvailable) {
          throw "Git is missing and neither Scoop nor winget is available for installation"
        }
        if ($null -ne $GitWingetExitCode) {
          throw ("Git installation did not provide git.exe; winget exit code was {0}" -f $GitWingetExitCode)
        }
        if ($GitScoopAttempted) {
          throw "Scoop did not provide git.exe and winget fallback was unavailable"
        }
        throw "Git installation did not provide git.exe"
      }
    }
    Write-Host "+ Git: available"

    # -------------------------------------------------------------------------
    # Rustup + stable-msvc + rustfmt + clippy
    # -------------------------------------------------------------------------
    $RustReady = $null -ne (Get-Command -Name "rustup.exe" -ErrorAction SilentlyContinue) -and $null -ne (Get-Command -Name "cargo.exe" -ErrorAction SilentlyContinue)
    if (-not $RustReady) {
      if ($NoSystemChanges) {
        throw "Windows prerequisite rustup is missing and -NoSystemChanges was requested"
      }

      $RustScoopAttempted = $false
      if ($ScoopAvailable) {
        $RustScoopAttempted = $true
        Write-Host "+ scoop install rustup"
        $SavedErrorActionPreference = $ErrorActionPreference
        try {
          $ErrorActionPreference = "Continue"
          & scoop install rustup
        } catch {
          Write-Warning ("Scoop could not install rustup: {0}" -f $_.Exception.Message)
        } finally {
          $ErrorActionPreference = $SavedErrorActionPreference
        }

        $MachinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
        $UserPath = [Environment]::GetEnvironmentVariable("Path", "User")
        $PathParts = @()
        if ($MachinePath) { $PathParts += $MachinePath }
        if ($UserPath) { $PathParts += $UserPath }
        if ($env:Path) { $PathParts += $env:Path }
        if (Test-Path -LiteralPath $DefaultScoopShims) { $PathParts += $DefaultScoopShims }
        if (-not [string]::IsNullOrWhiteSpace($env:SCOOP)) {
          $ConfiguredScoopShims = Join-Path $env:SCOOP "shims"
          if (Test-Path -LiteralPath $ConfiguredScoopShims) { $PathParts += $ConfiguredScoopShims }
        }
        if (Test-Path -LiteralPath $CargoBin) { $PathParts += $CargoBin }
        $env:Path = $PathParts -join ";"
        $RustReady = $null -ne (Get-Command -Name "rustup.exe" -ErrorAction SilentlyContinue) -and $null -ne (Get-Command -Name "cargo.exe" -ErrorAction SilentlyContinue)
      }

      if (-not $RustReady -and $WingetAvailable) {
        Write-Host "+ winget.exe install Rustlang.Rustup (fallback)"
        $SavedErrorActionPreference = $ErrorActionPreference
        try {
          $ErrorActionPreference = "SilentlyContinue"
          & winget.exe install -e --id Rustlang.Rustup --source winget --accept-source-agreements --accept-package-agreements
          $RustWingetExitCode = $LASTEXITCODE
        } finally {
          $ErrorActionPreference = $SavedErrorActionPreference
        }

        $MachinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
        $UserPath = [Environment]::GetEnvironmentVariable("Path", "User")
        $PathParts = @()
        if ($MachinePath) { $PathParts += $MachinePath }
        if ($UserPath) { $PathParts += $UserPath }
        if ($env:Path) { $PathParts += $env:Path }
        if (Test-Path -LiteralPath $DefaultScoopShims) { $PathParts += $DefaultScoopShims }
        if (-not [string]::IsNullOrWhiteSpace($env:SCOOP)) {
          $ConfiguredScoopShims = Join-Path $env:SCOOP "shims"
          if (Test-Path -LiteralPath $ConfiguredScoopShims) { $PathParts += $ConfiguredScoopShims }
        }
        if (Test-Path -LiteralPath $CargoBin) { $PathParts += $CargoBin }
        $env:Path = $PathParts -join ";"
        $RustReady = $null -ne (Get-Command -Name "rustup.exe" -ErrorAction SilentlyContinue) -and $null -ne (Get-Command -Name "cargo.exe" -ErrorAction SilentlyContinue)
      }

      if (-not $RustReady) {
        if (-not $ScoopAvailable -and -not $WingetAvailable) {
          throw "rustup is missing and neither Scoop nor winget is available for installation"
        }
        if ($null -ne $RustWingetExitCode) {
          throw ("rustup installation did not provide rustup.exe and cargo.exe; winget exit code was {0}" -f $RustWingetExitCode)
        }
        if ($RustScoopAttempted) {
          throw "Scoop did not provide rustup.exe and cargo.exe and winget fallback was unavailable"
        }
        throw "rustup installation did not provide rustup.exe and cargo.exe"
      }
    }

    Write-Host "+ rustup.exe toolchain install 1.97.1 --profile minimal --component rustfmt --component clippy"
    & rustup.exe toolchain install 1.97.1 --profile minimal --component rustfmt --component clippy
    if ($LASTEXITCODE -ne 0) {
      throw ("rustup.exe toolchain install 1.97.1 failed with exit code {0}" -f $LASTEXITCODE)
    }
    Write-Host "+ Rust toolchain: pinned 1.97.1 with rustfmt and clippy"

    # -------------------------------------------------------------------------
    # cargo-tauri
    # -------------------------------------------------------------------------
    $SavedErrorActionPreference = $ErrorActionPreference
    try {
      $ErrorActionPreference = "SilentlyContinue"
      & cargo.exe tauri --version *> $null
      $CargoTauriProbeExitCode = $LASTEXITCODE
    } finally {
      $ErrorActionPreference = $SavedErrorActionPreference
    }
    if ($CargoTauriProbeExitCode -ne 0) {
      Write-Host "+ cargo.exe install tauri-cli --locked --version ^2"
      & cargo.exe install tauri-cli --locked --version "^2"
      if ($LASTEXITCODE -ne 0) {
        throw ("cargo.exe install tauri-cli failed with exit code {0}" -f $LASTEXITCODE)
      }
      $SavedErrorActionPreference = $ErrorActionPreference
      try {
        $ErrorActionPreference = "SilentlyContinue"
        & cargo.exe tauri --version *> $null
        $CargoTauriProbeExitCode = $LASTEXITCODE
      } finally {
        $ErrorActionPreference = $SavedErrorActionPreference
      }
      if ($CargoTauriProbeExitCode -ne 0) {
        throw "cargo tauri is still unavailable after installing tauri-cli"
      }
    }

    # -------------------------------------------------------------------------
    # cargo-audit
    # -------------------------------------------------------------------------
    $SavedErrorActionPreference = $ErrorActionPreference
    try {
      $ErrorActionPreference = "SilentlyContinue"
      & cargo.exe audit --version *> $null
      $CargoAuditProbeExitCode = $LASTEXITCODE
    } finally {
      $ErrorActionPreference = $SavedErrorActionPreference
    }
    if ($CargoAuditProbeExitCode -ne 0) {
      Write-Host "+ cargo.exe install cargo-audit --locked"
      & cargo.exe install cargo-audit --locked
      if ($LASTEXITCODE -ne 0) {
        throw ("cargo.exe install cargo-audit failed with exit code {0}" -f $LASTEXITCODE)
      }
      $SavedErrorActionPreference = $ErrorActionPreference
      try {
        $ErrorActionPreference = "SilentlyContinue"
        & cargo.exe audit --version *> $null
        $CargoAuditProbeExitCode = $LASTEXITCODE
      } finally {
        $ErrorActionPreference = $SavedErrorActionPreference
      }
      if ($CargoAuditProbeExitCode -ne 0) {
        throw "cargo audit is still unavailable after installing cargo-audit"
      }
    }

    # -------------------------------------------------------------------------
    # JavaScript dependency policy + installation
    # -------------------------------------------------------------------------
    $Package = Get-Content -LiteralPath $PackagePath -Raw | ConvertFrom-Json
    $AllowScriptProperties = @($Package.allowScripts.PSObject.Properties)
    if (
      $AllowScriptProperties.Count -ne 1 -or
      $AllowScriptProperties[0].Name -ne "esbuild@0.25.12" -or
      $AllowScriptProperties[0].Value -ne $true
    ) {
      throw "package.json must approve exactly the reviewed esbuild@0.25.12 install script"
    }

    Write-Host "+ npm.cmd ci"
    & npm.cmd ci
    if ($LASTEXITCODE -ne 0) {
      throw ("npm.cmd ci failed with exit code {0}" -f $LASTEXITCODE)
    }
    Write-Host "+ npm.cmd audit --audit-level=high"
    & npm.cmd audit --audit-level=high
    if ($LASTEXITCODE -ne 0) {
      throw ("npm.cmd audit failed with exit code {0}" -f $LASTEXITCODE)
    }
    Write-Host "+ npm.cmd exec --offline -- esbuild --version"
    & npm.cmd exec --offline -- esbuild --version
    if ($LASTEXITCODE -ne 0) {
      throw ("local esbuild validation failed with exit code {0}" -f $LASTEXITCODE)
    }
  }

  Write-Host "Tauridium Windows development environment initialized."
  exit 0
} catch {
  Write-Error ("Tauridium initialization failed: {0}" -f $_.Exception.Message)
  exit 1
}
