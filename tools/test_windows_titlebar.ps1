param([Parameter(Mandatory = $true)][string]$Binary, [string]$Output = "release/evidence/windows-titlebar")
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
if ($env:GITHUB_ACTIONS -ne 'true' -or $env:RUNNER_ENVIRONMENT -ne 'github-hosted') { throw 'This GUI gate requires a fresh GitHub-hosted Windows CI user profile.' }
$Binary = (Resolve-Path -LiteralPath $Binary).Path
$ProfileRoot = Join-Path ([Environment]::GetFolderPath('ApplicationData')) 'dev.brani.tauridium'
if (Test-Path -LiteralPath $ProfileRoot) { throw 'Existing Tauridium data found; refusing to inspect or change it.' }
if (Get-Process -Name tauridium -ErrorAction SilentlyContinue) { throw 'An existing Tauridium process is running.' }
$Output = [IO.Path]::GetFullPath($Output)
[IO.Directory]::CreateDirectory($Output) | Out-Null
[IO.Directory]::CreateDirectory($ProfileRoot) | Out-Null
$Settings = Join-Path $ProfileRoot 'app_settings.json'
$Utf8 = New-Object Text.UTF8Encoding($false)
# Missing unifiedTitleBar exercises migration from an older profile.
[IO.File]::WriteAllText($Settings, '{"closeToSystemTray":false,"theme":"dark"}', $Utf8)
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type -AssemblyName System.Windows.Forms
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class ChromeNative {
  [StructLayout(LayoutKind.Sequential)] public struct Rect { public int Left, Top, Right, Bottom; }
  [StructLayout(LayoutKind.Sequential)] public struct Point { public int X, Y; }
  [StructLayout(LayoutKind.Sequential)] public struct TitleInfo {
    public int Size; public Rect Bar;
    [MarshalAs(UnmanagedType.ByValArray, SizeConst=6)] public uint[] State;
    [MarshalAs(UnmanagedType.ByValArray, SizeConst=6)] public Rect[] Buttons;
  }
  [DllImport("user32.dll")] public static extern IntPtr GetMenu(IntPtr h);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h,out Rect r);
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] private static extern int GetClassName(IntPtr h,System.Text.StringBuilder name,int length);
  [StructLayout(LayoutKind.Sequential)] private struct MouseInput {
    public int X,Y; public uint Data,Flags,Time; public UIntPtr Extra;
  }
  [StructLayout(LayoutKind.Sequential)] private struct KeyboardInput {
    public ushort Key,Scan; public uint Flags,Time; public UIntPtr Extra;
  }
  [StructLayout(LayoutKind.Explicit)] private struct InputData {
    [FieldOffset(0)] public MouseInput Mouse;
    [FieldOffset(0)] public KeyboardInput Keyboard;
  }
  [StructLayout(LayoutKind.Sequential)] private struct Input { public uint Type; public InputData Data; }
  [DllImport("user32.dll", SetLastError=true)] private static extern uint SendInput(uint count,Input[] input,int size);
  public static bool Activate(IntPtr h) {
    if (GetForegroundWindow()==h) return true;
    SetForegroundWindow(h);
    if (GetForegroundWindow()==h) return true;
    // A foreground CoreWindow on the fresh ARM runner can refuse activation.
    // Windows documents Alt input as releasing the foreground lock. This is
    // test-driver input only; never change global settings or app focus policy.
    Input down=new Input(), up=new Input(); down.Type=1; up.Type=1;
    down.Data.Keyboard.Key=0x12; up.Data.Keyboard.Key=0x12; up.Data.Keyboard.Flags=2;
    Input[] input={down,up};
    if (SendInput(2,input,Marshal.SizeOf(typeof(Input)))!=2) return false;
    SetForegroundWindow(h);
    return GetForegroundWindow()==h;
  }
  public static string WindowMetadata(IntPtr h) {
    uint pid; uint thread=GetWindowThreadProcessId(h,out pid);
    var name=new System.Text.StringBuilder(128); GetClassName(h,name,name.Capacity);
    string process="unavailable";
    try { process=System.Diagnostics.Process.GetProcessById((int)pid).ProcessName; }
    catch (ArgumentException) { }
    catch (System.ComponentModel.Win32Exception) { }
    return String.Format("HWND={0}; PID={1}; process={2}; thread={3}; class={4}; style=0x{5:x}",h,pid,process,thread,name,WindowStyle(h,-16).ToInt64());
  }
  public static bool HasCaptionStyles(IntPtr h) {
    const long required=0x00c00000|0x00080000|0x00040000|0x00020000|0x00010000;
    return (WindowStyle(h,-16).ToInt64() & required)==required;
  }
  public static void ClickCaption(IntPtr h,int index) {
    if (GetForegroundWindow()!=h) throw new InvalidOperationException("Refusing to click a background window.");
    Rect r=Title(h).Buttons[index];
    if (r.Right<=r.Left || r.Bottom<=r.Top) throw new InvalidOperationException("Caption button has no rectangle.");
    Point p=new Point(); p.X=(r.Left+r.Right)/2; p.Y=(r.Top+r.Bottom)/2;
    if (WindowFromPoint(p)!=h || !SetCursorPos(p.X,p.Y)) throw new InvalidOperationException("Caption button is covered.");
    if (GetForegroundWindow()!=h) throw new InvalidOperationException("Foreground changed before native click.");
    Input down=new Input(), up=new Input(); down.Data.Mouse.Flags=2; up.Data.Mouse.Flags=4;
    Input[] input={down,up};
    if (SendInput(2,input,Marshal.SizeOf(typeof(Input)))!=2) throw new InvalidOperationException("Native mouse click was blocked.");
  }
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h,int n);
  [DllImport("user32.dll")] public static extern bool IsZoomed(IntPtr h);
  [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr h);
  [DllImport("user32.dll")] public static extern uint GetDpiForWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern IntPtr SetThreadDpiAwarenessContext(IntPtr context);
  [DllImport("user32.dll")] public static extern IntPtr WindowFromPoint(Point p);
  [DllImport("user32.dll")] private static extern bool SetCursorPos(int x,int y);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] private static extern IntPtr FindWindowEx(IntPtr p,IntPtr a,string c,string n);
  [DllImport("user32.dll")] private static extern uint GetWindowThreadProcessId(IntPtr h,out uint pid);
  [DllImport("user32.dll")] private static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] private static extern IntPtr GetWindow(IntPtr h,uint command);
  [DllImport("user32.dll", EntryPoint="GetWindowLongPtrW")] private static extern IntPtr WindowStyle(IntPtr h,int index);
  public static IntPtr MainWindow(int pid) {
    // Process.MainWindowHandle can choose WebView2's visible 16x16 helper.
    // Select the largest visible, unowned, captioned window of this process.
    IntPtr h=IntPtr.Zero, best=IntPtr.Zero; long largest=0;
    while ((h=FindWindowEx(IntPtr.Zero,h,null,null)) != IntPtr.Zero) {
      uint owner; GetWindowThreadProcessId(h,out owner);
      if (owner!=(uint)pid || !IsWindowVisible(h) || GetWindow(h,4)!=IntPtr.Zero
          || (WindowStyle(h,-16).ToInt64() & 0x00c00000)!=0x00c00000) continue;
      Rect r;
      if (GetWindowRect(h,out r)) {
        long width=(long)r.Right-r.Left, height=(long)r.Bottom-r.Top;
        if (width>64 && height>64 && width*height>largest) { best=h; largest=width*height; }
      }
    }
    return best;
  }
  [DllImport("user32.dll", EntryPoint="SendMessageW")] public static extern IntPtr SendMessage(IntPtr h,uint m,IntPtr w,IntPtr l);
  [DllImport("user32.dll", EntryPoint="SendMessageW")] private static extern IntPtr TitleMessage(IntPtr h,uint m,IntPtr w,ref TitleInfo info);
  [DllImport("user32.dll")] public static extern bool PostMessageW(IntPtr h,uint m,IntPtr w,IntPtr l);
  public static TitleInfo Title(IntPtr h) {
    TitleInfo t=new TitleInfo(); t.Size=Marshal.SizeOf(typeof(TitleInfo)); t.State=new uint[6]; t.Buttons=new Rect[6];
    TitleMessage(h,0x033f,IntPtr.Zero,ref t); return t;
  }
  public static int Hit(IntPtr h,Point p) {
    if (!SetCursorPos(p.X,p.Y)) return int.MinValue;
    return (int)SendMessage(h,0x84,IntPtr.Zero,new IntPtr(((p.Y&65535)<<16)|(p.X&65535)));
  }
  public static bool CaptionReady(IntPtr h,bool unified) {
    TitleInfo info=Title(h); int[] indexes={2,3,5}, hits={8,9,20};
    for (int i=0;i<indexes.Length;i++) {
      Rect r=info.Buttons[indexes[i]];
      if (r.Right<=r.Left || r.Bottom<=r.Top) return false;
      Point p=new Point(); p.X=(r.Left+r.Right)/2; p.Y=(r.Top+r.Bottom)/2;
      if ((info.State[indexes[i]] & 0x8001)!=0 || WindowFromPoint(p)!=h) return false;
      if (unified && Hit(h,p)!=hits[i]) return false;
    }
    return true;
  }
  public static bool HasPopup(int pid) {
    IntPtr h=IntPtr.Zero;
    while ((h=FindWindowEx(IntPtr.Zero,h,"#32768",null)) != IntPtr.Zero) {
      uint owner; GetWindowThreadProcessId(h,out owner); if (owner==(uint)pid) return true;
    } return false;
  }
}
'@
$script:Child = $null
$script:Window = [IntPtr]::Zero
$script:Checks = New-Object 'System.Collections.Generic.List[string]'
$script:TestPids = New-Object 'System.Collections.Generic.List[int]'
$TestStarted = [DateTime]::UtcNow
# Keep Win32 rectangles and UIA bounds in the same physical screen pixels.
$PreviousDpiContext = [ChromeNative]::SetThreadDpiAwarenessContext([IntPtr](-4))
if ($PreviousDpiContext -eq [IntPtr]::Zero) { throw 'Unable to enable per-monitor physical-pixel measurements.' }
function Write-Test-Diagnostics {
  Write-Host 'Fresh test profile diagnostics (no personal accounts or service data):'
  if ($script:Window -ne [IntPtr]::Zero) {
    Write-Host ('Main: {0}; menu={1}' -f [ChromeNative]::WindowMetadata($script:Window),[ChromeNative]::GetMenu($script:Window))
    Write-Host ('Foreground: '+[ChromeNative]::WindowMetadata([ChromeNative]::GetForegroundWindow()))
    $Info=[ChromeNative]::Title($script:Window)
    foreach ($Index in @(2,3,5)) {
      $R=$Info.Buttons[$Index]; $P=New-Object ChromeNative+Point
      $P.X=[int](($R.Left+$R.Right)/2); $P.Y=[int](($R.Top+$R.Bottom)/2)
      Write-Host ('Caption {0}: rect={1},{2},{3},{4}; hit={5}; pointWindow={6}; state=0x{7:x}' -f $Index,$R.Left,$R.Top,$R.Right,$R.Bottom,[ChromeNative]::Hit($script:Window,$P),[ChromeNative]::WindowFromPoint($P),$Info.State[$Index])
    }
    try {
      $Nodes = (Root).FindAll([Windows.Automation.TreeScope]::Subtree,[Windows.Automation.Condition]::TrueCondition)
      Write-Host ('UIA node count: {0}' -f $Nodes.Count)
      for ($Index=0; $Index -lt [Math]::Min($Nodes.Count,120); $Index++) {
        $Current = $Nodes[$Index].Current
        $Name = $Current.Name -replace '[\r\n\t]',' '
        if ($Name.Length -gt 160) { $Name=$Name.Substring(0,160) }
        Write-Host ('UIA {0}: {1}; {2}; {3}' -f $Index,$Current.ControlType.ProgrammaticName,$Name,$Current.BoundingRectangle)
      }
    } catch { Write-Host 'UIA diagnostic enumeration was unavailable.' }
  }
  try {
    $Control = Find-Control 'Unified title bar' ([Windows.Automation.ControlType]::CheckBox)
    if ($null -ne $Control) {
      $Toggle = $Control.GetCurrentPattern([Windows.Automation.TogglePattern]::Pattern)
      Write-Host ('Preference UI: state={0}; enabled={1}; offscreen={2}' -f $Toggle.Current.ToggleState,$Control.Current.IsEnabled,$Control.Current.IsOffscreen)
    }
    $Data = Read-Settings
    $Property = $Data.PSObject.Properties['unifiedTitleBar']
    Write-Host ('Preference file: present={0}; value={1}' -f ($null -ne $Property),$(if ($Property -and $Property.Value -is [bool]) { $Property.Value } else { 'not a Boolean' }))
    $TextNodes = (Root).FindAll([Windows.Automation.TreeScope]::Descendants,[Windows.Automation.Condition]::TrueCondition)
    $Found=0
    foreach ($Node in $TextNodes) {
      $Name=$Node.Current.Name
      if ($Name -match 'Unable to|Saved preference|Saved\.|Error:' -and $Found -lt 15) {
        if ($Name.Length -gt 240) { $Name=$Name.Substring(0,240) }
        Write-Host ('Preference status: '+$Name); $Found++
      }
    }
  } catch { Write-Host 'Preference diagnostics were unavailable.' }
  $Diagnostics = Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'Tauridium\diagnostics'
  foreach ($TestPid in $script:TestPids) {
    foreach ($Log in @(Get-ChildItem -LiteralPath $Diagnostics -Filter ('startup-*-{0}.log' -f $TestPid) -File -ErrorAction SilentlyContinue)) {
      if ($Log.LastWriteTimeUtc -ge $TestStarted) {
        Get-Content -LiteralPath $Log.FullName -Tail 40 | ForEach-Object { Write-Host $_ }
      }
    }
  }
}
function Wait-For([scriptblock]$Condition, [string]$Label, [int]$Seconds = 45) {
  $Deadline = [DateTime]::UtcNow.AddSeconds($Seconds)
  do {
    if (& $Condition) { return }
    if ($script:Child -and $script:Child.HasExited) { throw "Tauridium exited while waiting for $Label" }
    Start-Sleep -Milliseconds 150
  } while ([DateTime]::UtcNow -lt $Deadline)
  throw "Timed out waiting for $Label"
}
function Check([bool]$Passed, [string]$Label) {
  if (-not $Passed) { throw "Failed: $Label" }
  $script:Checks.Add($Label); Write-Host "PASS $Label"
}
function Root { return [Windows.Automation.AutomationElement]::FromHandle($script:Window) }
function Find-Control([string]$Name, [Windows.Automation.ControlType]$Type = $null) {
  $Condition = New-Object Windows.Automation.PropertyCondition([Windows.Automation.AutomationElement]::NameProperty,$Name)
  if ($null -ne $Type) {
    $Kind = New-Object Windows.Automation.PropertyCondition([Windows.Automation.AutomationElement]::ControlTypeProperty,$Type)
    $Condition = New-Object Windows.Automation.AndCondition($Condition,$Kind)
  }
  return (Root).FindFirst([Windows.Automation.TreeScope]::Descendants,$Condition)
}
function Invoke-Control([string]$Name, [Windows.Automation.ControlType]$Type = [Windows.Automation.ControlType]::Button) {
  Wait-For { $null -ne (Find-Control $Name $Type) } $Name
  $Control = Find-Control $Name $Type
  $Pattern = $null
  # Menu items with a submenu expose ExpandCollapse, while ordinary buttons
  # expose Invoke. Use the provider's actual semantic action.
  if ($Control.TryGetCurrentPattern([Windows.Automation.ExpandCollapsePattern]::Pattern,[ref]$Pattern)) {
    $Pattern.Expand()
  } elseif ($Control.TryGetCurrentPattern([Windows.Automation.InvokePattern]::Pattern,[ref]$Pattern)) {
    $Pattern.Invoke()
  } else {
    $Available = ($Control.GetSupportedPatterns() | ForEach-Object { $_.ProgrammaticName }) -join ', '
    throw "Control $Name exposes neither menu expansion nor button invocation: $Available"
  }
}
function Start-Tauridium {
  $script:Child = Start-Process -FilePath $Binary -ArgumentList '--startup-diagnostics' -PassThru
  $script:TestPids.Add($script:Child.Id)
  $script:Window = [IntPtr]::Zero
  Wait-For { $script:Window = [ChromeNative]::MainWindow($script:Child.Id); $script:Window -ne [IntPtr]::Zero } 'captioned application window'
  Activate-Tauridium
  Wait-For { $null -ne (Find-Control 'Application' ([Windows.Automation.ControlType]::MenuBar)) -or [ChromeNative]::GetMenu($script:Window) -ne [IntPtr]::Zero } 'application menus'
  Wait-For { $null -ne (Find-Control 'Tauridium' ([Windows.Automation.ControlType]::Document)) } 'local shell document'
  Activate-Tauridium
}
function Activate-Tauridium {
  Wait-For { [ChromeNative]::Activate($script:Window) } 'foreground application window'
}
function Stop-Tauridium {
  [ChromeNative]::PostMessageW($script:Window,0x10,[IntPtr]::Zero,[IntPtr]::Zero) | Out-Null
  if (-not $script:Child.WaitForExit(15000)) { throw 'Normal application close did not exit.' }
  $script:Child.Dispose(); $script:Child = $null
}
function Check-Caption([bool]$Unified = $true) {
  Activate-Tauridium
  Check ([ChromeNative]::HasCaptionStyles($script:Window)) 'native caption, sizing, system menu and min/max styles remain present'
  Wait-For { [ChromeNative]::CaptionReady($script:Window,$Unified) } 'settled and enabled native caption targets'
  $Info = [ChromeNative]::Title($script:Window)
  foreach ($Entry in @(@(2,8,'minimize'),@(3,9,'maximize'),@(5,20,'close'))) {
    $R = $Info.Buttons[$Entry[0]]
    Check ($R.Right -gt $R.Left -and $R.Bottom -gt $R.Top) "native $($Entry[2]) rectangle exists"
    $P = New-Object ChromeNative+Point
    $P.X = [int](($R.Left+$R.Right)/2); $P.Y = [int](($R.Top+$R.Bottom)/2)
    Check ([ChromeNative]::WindowFromPoint($P) -eq $script:Window) "native $($Entry[2]) is not covered by a WebView"
    if ($Unified) {
      Check ([ChromeNative]::Hit($script:Window,$P) -eq $Entry[1]) "unified native $($Entry[2]) hit test"
    }
    Check (($Info.State[$Entry[0]] -band 0x8001) -eq 0) "native $($Entry[2]) is visible and enabled"
  }
}
function Check-Caption-Interaction {
  # Real input reaches DWM's standard-frame routing; manually sending
  # WM_NCHITTEST alone does not exercise that path. Keep exact 8/9/20
  # assertions for our custom frame and verify actual controls in both modes.
  Activate-Tauridium
  [ChromeNative]::ClickCaption($script:Window,3)
  Wait-For { [ChromeNative]::IsZoomed($script:Window) } 'native maximize button'
  Activate-Tauridium
  [ChromeNative]::ClickCaption($script:Window,3)
  Wait-For { -not [ChromeNative]::IsZoomed($script:Window) } 'native restore button'
  Activate-Tauridium
  [ChromeNative]::ClickCaption($script:Window,2)
  Wait-For { [ChromeNative]::IsIconic($script:Window) } 'native minimize button'
  [ChromeNative]::ShowWindow($script:Window,9) | Out-Null
  Wait-For { -not [ChromeNative]::IsIconic($script:Window) } 'restored minimized window'
  Activate-Tauridium
  Check $true 'native caption buttons maximize, restore and minimize through real mouse input'
}
function Outer-Size {
  $R = New-Object ChromeNative+Rect
  if (-not [ChromeNative]::GetWindowRect($script:Window,[ref]$R)) { throw 'Unable to read the test window rectangle.' }
  return @(($R.Right - $R.Left), ($R.Bottom - $R.Top))
}
function Open-Advanced {
  Activate-Tauridium
  [Windows.Forms.SendKeys]::SendWait('^,')
  Invoke-Control 'Advanced'
  Wait-For { $null -ne (Find-Control 'Unified title bar' ([Windows.Automation.ControlType]::CheckBox)) } 'title-bar setting'
}
function Read-Settings([string]$Path = $Settings) {
  $Stream = [IO.File]::Open($Path,[IO.FileMode]::Open,[IO.FileAccess]::Read,([IO.FileShare]::ReadWrite -bor [IO.FileShare]::Delete))
  $Reader = New-Object IO.StreamReader($Stream)
  try { return ($Reader.ReadToEnd() | ConvertFrom-Json) } finally { $Reader.Dispose() }
}
function Toggle-Chrome([bool]$Enabled) {
  $Before = if ($Enabled) { [Windows.Automation.ToggleState]::Off } else { [Windows.Automation.ToggleState]::On }
  $Expected = if ($Enabled) { [Windows.Automation.ToggleState]::On } else { [Windows.Automation.ToggleState]::Off }
  Wait-For {
    $Control=Find-Control 'Unified title bar' ([Windows.Automation.ControlType]::CheckBox)
    $Control.Current.IsEnabled -and $Control.GetCurrentPattern([Windows.Automation.TogglePattern]::Pattern).Current.ToggleState -eq $Before
  } 'current title-bar checkbox state'
  # Exercise the user's keyboard action and confirm the UI transition before
  # checking durable storage independently.
  (Find-Control 'Unified title bar' ([Windows.Automation.ControlType]::CheckBox)).SetFocus()
  Wait-For { [Windows.Automation.AutomationElement]::FocusedElement.Current.Name -eq 'Unified title bar' } 'focused title-bar checkbox'
  [Windows.Forms.SendKeys]::SendWait(' ')
  Wait-For {
    (Find-Control 'Unified title bar' ([Windows.Automation.ControlType]::CheckBox)).GetCurrentPattern([Windows.Automation.TogglePattern]::Pattern).Current.ToggleState -eq $Expected
  } 'changed title-bar checkbox state'
  Wait-For { $Value=Read-Settings; $Value.PSObject.Properties['unifiedTitleBar'] -and $Value.unifiedTitleBar -is [bool] -and $Value.unifiedTitleBar -eq $Enabled } 'saved title-bar preference'
}
try {
  Start-Tauridium
  Check ([ChromeNative]::GetMenu($script:Window) -eq [IntPtr]::Zero) 'older settings default to a unified title bar'
  Check-Caption
  Check-Caption-Interaction
  $OriginalOuter = Outer-Size
  Check ($null -ne (Find-Control 'Application' ([Windows.Automation.ControlType]::MenuBar))) 'accessible application menu bar exists'
  Invoke-Control 'Tauridium' ([Windows.Automation.ControlType]::MenuItem)
  Wait-For { [ChromeNative]::HasPopup($script:Child.Id) } 'native application popup'
  Check $true 'unified menu opens a real native popup'
  [Windows.Forms.SendKeys]::SendWait('{ESC}')
  Wait-For { -not [ChromeNative]::HasPopup($script:Child.Id) } 'dismissed native popup'
  Invoke-Control 'Use Tauridium without an account'
  Open-Advanced
  $Scale = [double][ChromeNative]::GetDpiForWindow($script:Window) / 96.0
  Check ($Scale -gt 0) 'native window DPI is available'
  Check ((Find-Control 'Unified title bar' ([Windows.Automation.ControlType]::CheckBox)).Current.BoundingRectangle.Width -le (48 * $Scale)) 'Advanced toggle has bounded switch geometry'
  Toggle-Chrome $false
  Check ([ChromeNative]::GetMenu($script:Window) -eq [IntPtr]::Zero) 'saved classic preference does not reconstruct a live window'
  Stop-Tauridium
  $SavedWindow = (Read-Settings (Join-Path $ProfileRoot 'window-state.json')).main
  Check ($SavedWindow.outer_size -eq $true -and $SavedWindow.width -eq $OriginalOuter[0] -and $SavedWindow.height -eq $OriginalOuter[1]) 'physical outer size is stored with an explicit format marker'
  Start-Tauridium
  Check ([ChromeNative]::GetMenu($script:Window) -ne [IntPtr]::Zero) 'restart restores the classic native menu bar'
  $RestoredOuter = Outer-Size
  Check ($RestoredOuter[0] -eq $OriginalOuter[0] -and $RestoredOuter[1] -eq $OriginalOuter[1]) 'classic restart preserves outside dimensions'
  Check-Caption $false
  Check-Caption-Interaction
  Open-Advanced
  Toggle-Chrome $true
  Check ([ChromeNative]::GetMenu($script:Window) -ne [IntPtr]::Zero) 'saved unified preference waits for restart'
  Stop-Tauridium
  Start-Tauridium
  Check ([ChromeNative]::GetMenu($script:Window) -eq [IntPtr]::Zero) 'restart restores unified chrome'
  $RestoredOuter = Outer-Size
  Check ($RestoredOuter[0] -eq $OriginalOuter[0] -and $RestoredOuter[1] -eq $OriginalOuter[1]) 'unified restart preserves outside dimensions'
  Check-Caption
  Check-Caption-Interaction
  [ChromeNative]::ShowWindow($script:Window,3) | Out-Null
  Wait-For { [ChromeNative]::IsZoomed($script:Window) } 'maximized window'
  Check-Caption
  [ChromeNative]::ShowWindow($script:Window,9) | Out-Null
  Wait-For { -not [ChromeNative]::IsZoomed($script:Window) } 'restored window'
  [ChromeNative]::ShowWindow($script:Window,6) | Out-Null
  Wait-For { [ChromeNative]::IsIconic($script:Window) } 'minimized window'
  [ChromeNative]::ShowWindow($script:Window,9) | Out-Null
  Wait-For { -not [ChromeNative]::IsIconic($script:Window) } 'restored minimized window'
  Check-Caption
  Activate-Tauridium
  [Windows.Forms.SendKeys]::SendWait('{F10}')
  Wait-For { [Windows.Automation.AutomationElement]::FocusedElement.Current.Name -eq 'Tauridium' } 'F10 menu access'
  [Windows.Forms.SendKeys]::SendWait('{RIGHT}')
  Wait-For { [Windows.Automation.AutomationElement]::FocusedElement.Current.Name -eq 'Edit' } 'menu arrow navigation'
  [Windows.Forms.SendKeys]::SendWait('{ESC}')
  Check $true 'F10 and arrow navigation are accessible'
  Stop-Tauridium
  Start-Tauridium
  $RestoredOuter = Outer-Size
  Check ($RestoredOuter[0] -eq $OriginalOuter[0] -and $RestoredOuter[1] -eq $OriginalOuter[1]) 'repeated unified restart does not accumulate frame height'
  [ChromeNative]::ShowWindow($script:Window,3) | Out-Null
  Wait-For { [ChromeNative]::IsZoomed($script:Window) } 'maximized state before restart'
  Stop-Tauridium
  Start-Tauridium
  Wait-For { [ChromeNative]::IsZoomed($script:Window) } 'restored maximized state'
  Check-Caption
  [ChromeNative]::ShowWindow($script:Window,9) | Out-Null
  Wait-For { -not [ChromeNative]::IsZoomed($script:Window) } 'normal window after maximized restart'
  $RestoredOuter = Outer-Size
  Check ($RestoredOuter[0] -eq $OriginalOuter[0] -and $RestoredOuter[1] -eq $OriginalOuter[1]) 'maximized restart preserves normal outside dimensions'
  Stop-Tauridium
  $Result = @{ passed=$true; checks=$script:Checks.ToArray(); privateAccountsUsed=$false; titleBarModes=@('unified-default','classic-restarted','unified-restarted') }
  [IO.File]::WriteAllText((Join-Path $Output 'result.json'),($Result | ConvertTo-Json -Depth 6),$Utf8)
  Write-Host 'Native production Windows title-bar smoke passed.'
} catch {
  Write-Test-Diagnostics
  throw
} finally {
  [ChromeNative]::SetThreadDpiAwarenessContext($PreviousDpiContext) | Out-Null
  if ($script:Child -and -not $script:Child.HasExited) {
    [ChromeNative]::PostMessageW($script:Window,0x10,[IntPtr]::Zero,[IntPtr]::Zero) | Out-Null
    if (-not $script:Child.WaitForExit(5000)) { Stop-Process -Id $script:Child.Id -Force }
  }
}
