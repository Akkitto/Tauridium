$ErrorActionPreference = "Stop"
$PythonArguments = @($args)

$PythonCandidates = @(
  @{ Command = "py.exe"; Prefix = @("-3") },
  @{ Command = "python.exe"; Prefix = @() },
  @{ Command = "python3.exe"; Prefix = @() }
)

foreach ($PythonCandidate in $PythonCandidates) {
  $PythonCommand = Get-Command -Name $PythonCandidate.Command -ErrorAction SilentlyContinue
  if ($null -eq $PythonCommand) {
    continue
  }

  $ProbeArguments = @()
  $ProbeArguments += $PythonCandidate.Prefix
  $ProbeArguments += "--version"

  $SavedErrorActionPreference = $ErrorActionPreference
  try {
    $ErrorActionPreference = "SilentlyContinue"
    $PythonVersion = & $PythonCommand.Source @ProbeArguments 2>&1 | Out-String
    $PythonProbeExitCode = $LASTEXITCODE
  } finally {
    $ErrorActionPreference = $SavedErrorActionPreference
  }

  if ($PythonProbeExitCode -ne 0 -or $PythonVersion -notmatch "Python\s+3\.") {
    continue
  }

  $InvocationArguments = @()
  $InvocationArguments += $PythonCandidate.Prefix
  $InvocationArguments += $PythonArguments

  & $PythonCommand.Source @InvocationArguments
  exit $LASTEXITCODE
}

Write-Error "No usable Python 3 runtime was found. Run just init first."
exit 1
