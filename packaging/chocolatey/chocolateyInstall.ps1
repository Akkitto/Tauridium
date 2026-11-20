$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'tauridium.ps1')
Assert-TauridiumStopped
$Payload = Get-TauridiumPayload $PSScriptRoot
$Products = @(Get-TauridiumProducts)
Assert-TauridiumRegistrations $Products
if ($Products.Count -eq 1 -and [version]$Products[0].Version -gt [version]$Payload.Version) {
  throw 'A newer Tauridium MSI is already installed. Use a package matching that version; downgrades are refused.'
}
# MSI is installed machine-wide; never launch the app elevated or reboot silently.
Install-ChocolateyInstallPackage -PackageName 'tauridium' -FileType 'msi' `
  -File $Payload.File -SilentArgs '/qn /norestart REBOOT=ReallySuppress AUTOLAUNCHAPP=0 WIXUI_EXITDIALOGOPTIONALCHECKBOX=0' `
  -UseOnlyPackageSilentArguments -ValidExitCodes @(0, 3010)
$Installed = @(Get-TauridiumProducts)
Assert-TauridiumRegistrations $Installed
if ($Installed.Count -ne 1 -or $Installed[0].Version -ne $Payload.Version) { throw 'MSI installation identity did not converge to the requested version.' }
