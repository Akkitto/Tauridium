# Account-free HTTP fixtures must never create a console or steal GUI-test focus.
function Start-HttpFixtureServer {
  param(
    [Parameter(Mandatory = $true)][string]$Python,
    [Parameter(Mandatory = $true)][string]$Directory,
    [Parameter(Mandatory = $true)][ValidateRange(1,65535)][int]$Port
  )
  $Directory = (Resolve-Path -LiteralPath $Directory).Path
  $Info = New-Object Diagnostics.ProcessStartInfo
  $Info.FileName = $Python
  $Info.Arguments = '-I -u -m http.server {0} --bind 127.0.0.1 --directory "{1}"' -f $Port,$Directory
  $Info.WorkingDirectory = $Directory
  $Info.UseShellExecute = $false
  $Info.CreateNoWindow = $true
  $Info.RedirectStandardOutput = $true
  $Info.RedirectStandardError = $true
  $Process = New-Object Diagnostics.Process
  $Process.StartInfo = $Info
  $Started = $false
  try {
    if (-not $Process.Start()) { throw 'Unable to start the HTTP fixture server.' }
    $Started = $true
    # Drain both pipes immediately, without PowerShell callbacks/runspaces.
    return [PSCustomObject]@{
      Process = $Process
      Stdout = $Process.StandardOutput.ReadToEndAsync()
      Stderr = $Process.StandardError.ReadToEndAsync()
      Directory = $Directory
      Port = $Port
      Stopped = $false
    }
  } catch {
    try {
      if ($Started -and -not $Process.HasExited) {
        $Process.Kill()
        if (-not $Process.WaitForExit(5000)) { throw 'HTTP fixture server did not stop after startup failed.' }
      }
    } finally { $Process.Dispose() }
    throw
  }
}

function Wait-HttpFixtureServer {
  param([Parameter(Mandatory = $true)]$Server, [ValidateRange(1,45)][int]$Seconds = 15)
  $Deadline = [DateTime]::UtcNow.AddSeconds($Seconds)
  do {
    if ($Server.Process.HasExited) {
      throw "HTTP fixture server exited with code $($Server.Process.ExitCode) before becoming ready."
    }
    try {
      $Response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$($Server.Port)/fixture.html" -TimeoutSec 2
      if ($Response.StatusCode -eq 200) { return }
    } catch {
      # PowerShell 5.1 uses WebException; PowerShell 7 uses HttpClient exceptions.
      # Retry only connection/timeout failures, not script or HTTP status errors.
      if ($_.Exception -is [Net.WebException] -and $_.Exception.Status -eq [Net.WebExceptionStatus]::ProtocolError) { throw }
      if ($_.Exception -isnot [Net.WebException] -and $_.Exception.GetType().FullName -notin @(
        'System.Net.Http.HttpRequestException', 'System.Threading.Tasks.TaskCanceledException'
      )) { throw }
    }
    Start-Sleep -Milliseconds 100
  } while ([DateTime]::UtcNow -lt $Deadline)
  throw 'Timed out waiting for the local HTTP fixture server.'
}

function Stop-HttpFixtureServer {
  param([Parameter(Mandatory = $true)]$Server)
  if ($Server.Stopped) { return }
  try {
    if (-not $Server.Process.HasExited) {
      $Server.Process.Kill()
      if (-not $Server.Process.WaitForExit(5000)) { throw 'HTTP fixture server did not stop.' }
    }
    $Tasks = [Threading.Tasks.Task[]]@($Server.Stdout,$Server.Stderr)
    if (-not [Threading.Tasks.Task]::WaitAll($Tasks,5000)) { throw 'HTTP fixture server output did not close.' }
    $Encoding = New-Object Text.UTF8Encoding($false)
    [IO.File]::WriteAllText((Join-Path $Server.Directory 'server.log'),$Server.Stdout.GetAwaiter().GetResult(),$Encoding)
    [IO.File]::WriteAllText((Join-Path $Server.Directory 'server-errors.log'),$Server.Stderr.GetAwaiter().GetResult(),$Encoding)
  } finally {
    $Server.Process.Dispose()
    $Server.Stopped = $true
  }
}
