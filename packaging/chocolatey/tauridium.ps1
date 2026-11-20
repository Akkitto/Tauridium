# Shared local-package policy. Compatible with Windows PowerShell 5.1.
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$TauridiumUpgradeCode = '{417CADD0-7C97-590B-8DAF-C89B2319571E}'

function Get-TauridiumArchitecture {
  if ($env:ChocolateyForceX86 -eq 'true') { throw 'Tauridium does not provide an x86 package.' }
  # The native OS architecture remains authoritative under emulated PowerShell.
  $Native = [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString()
  switch ($Native.ToLowerInvariant()) {
    'x64' { return 'x64' }
    'arm64' { return 'arm64' }
    default { throw 'Tauridium supports only Windows x64 and ARM64.' }
  }
}
function Assert-TauridiumStopped {
  if (@(Get-Process -Name tauridium -ErrorAction SilentlyContinue).Count -gt 0) {
    throw 'Close all Tauridium windows and quit its tray process, then retry. No process was terminated.'
  }
}
function Get-TauridiumRegistrations {
  $Rows = @()
  foreach ($Hive in @('HKCU:', 'HKLM:')) {
    foreach ($Key in @("$Hive\Software\Microsoft\Windows\CurrentVersion\Uninstall\*", "$Hive\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*")) {
      $Rows += @(Get-ItemProperty -Path $Key -ErrorAction SilentlyContinue | Where-Object {
        $_.PSObject.Properties['DisplayName'] -and $_.DisplayName -eq 'Tauridium'
      })
    }
  }
  return $Rows
}
function Get-TauridiumProducts {
  $Installer = New-Object -ComObject WindowsInstaller.Installer
  try {
    $Codes = @($Installer.RelatedProducts($TauridiumUpgradeCode))
    foreach ($Code in $Codes) {
      if ($Code -notmatch '^\{[A-Fa-f0-9-]{36}\}$' -or
          $Installer.ProductInfo($Code, 'ProductName') -ne 'Tauridium' -or
          $Installer.ProductInfo($Code, 'Publisher') -ne 'brani' -or
          [string]$Installer.ProductInfo($Code, 'AssignmentType') -ne '1') {
        throw 'Unexpected Tauridium MSI family or installation scope; preserve it for review.'
      }
      [PSCustomObject]@{ Code=[string]$Code; Version=[string]$Installer.ProductInfo($Code, 'VersionString') }
    }
  } finally { [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($Installer) }
}
function Assert-TauridiumRegistrations([object[]]$Products) {
  $Rows = @(Get-TauridiumRegistrations)
  if ($Products.Count -gt 1 -or $Rows.Count -ne $Products.Count) {
    throw 'A conflicting Tauridium installation exists. Remove its installer registration first; keep your application data.'
  }
  foreach ($Row in $Rows) {
    if ($Row.PSPath -notlike '*HKEY_LOCAL_MACHINE*' -or $Row.Publisher -ne 'brani' -or
        $Row.PSChildName -ne $Products[0].Code) {
      throw 'A per-user or unrelated installation conflicts with the Chocolatey machine installation.'
    }
  }
}
function Get-TauridiumMsiProperty($Database, [string]$Name) {
  if ($Name -notin @('ProductName','Manufacturer','ProductVersion','UpgradeCode','ALLUSERS','ProductCode')) { throw 'Unexpected MSI property query.' }
  $View = $Database.OpenView("SELECT ``Value`` FROM ``Property`` WHERE ``Property`` = '$Name'")
  try {
    [void]$View.Execute()
    $Record = $View.Fetch()
    if ($null -eq $Record) { return '' }
    try { return [string]$Record.StringData(1) }
    finally { [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($Record) }
  } finally { [void]$View.Close(); [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($View) }
}
function Get-TauridiumPayload([string]$Tools) {
  $Release = Get-Content -LiteralPath (Join-Path $Tools 'release.json') -Raw -Encoding UTF8 | ConvertFrom-Json
  if ($Release.schema -ne 1 -or $Release.version -notmatch '^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$') { throw 'Invalid packaged release metadata.' }
  $Arch = Get-TauridiumArchitecture
  $Name = 'tauridium-' + $Release.version + '-windows-' + $Arch + '.msi'
  $Entry = $Release.assets.$Name
  $File = Join-Path (Join-Path $Tools 'installers') $Name
  $Item = Get-Item -LiteralPath $File -Force
  if (($Item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 -or $Item.PSIsContainer -or
      $Entry.sha256 -notmatch '^[a-f0-9]{64}$' -or $Item.Length -ne $Entry.size -or
      (Get-FileHash -LiteralPath $File -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Entry.sha256) {
    throw 'Embedded installer failed exact size/SHA-256 verification.'
  }
  $Installer = New-Object -ComObject WindowsInstaller.Installer
  $Database = $null
  try {
    $Database = $Installer.OpenDatabase($File, 0)
    $Summary = $Database.SummaryInformation(0)
    try { $Template = ([string]$Summary.Property(7)).Split(';')[0] }
    finally { [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($Summary) }
    if ($Template.ToLowerInvariant() -ne $Arch) { throw 'MSI architecture differs from the native Windows target.' }
    $Expected = @{ ProductName='Tauridium'; Manufacturer='brani'; ProductVersion=[string]$Release.version; UpgradeCode=$TauridiumUpgradeCode; ALLUSERS='1' }
    $Mismatches = @()
    foreach ($Field in $Expected.Keys) {
      $Actual = Get-TauridiumMsiProperty $Database $Field
      if ($Actual -isnot [string] -or $Actual -cne $Expected[$Field]) { $Mismatches += $Field }
    }
    if ($Mismatches.Count) {
      throw ('Embedded MSI does not match expected identity/scope; property names: ' + ($Mismatches -join ', '))
    }
  } finally {
    if ($null -ne $Database) { [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($Database) }
    [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($Installer)
  }
  return [PSCustomObject]@{ File=$File; Version=$Release.version; Architecture=$Arch }
}
