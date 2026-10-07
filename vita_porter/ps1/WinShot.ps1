# Screenshot of a process's main visible window (client area) -> PNG. Used by `vita sim --shot` and `vita emu --shot`.
# From universal-decompiler (ud/ps1/WinShot.ps1, MIT, same author).
# PrintWindow with PW_RENDERFULLCONTENT captures most GPU-rendered windows even when covered (not minimized).
# The caller prepends: $TargetPid = <pid>; $Name = '<process name without .exe>'; $Out = '<C:\path\shot.png>'
# Embedded C# stays at C# 5 (Windows PowerShell 5.1's compiler).
$ErrorActionPreference = "Stop"
Add-Type -ReferencedAssemblies System.Drawing -TypeDefinition @"
using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Imaging;
using System.Runtime.InteropServices;
public static class UdShot {
    public delegate bool EnumProc(IntPtr h, IntPtr l);
    [DllImport("user32.dll")] static extern bool EnumWindows(EnumProc cb, IntPtr l);
    [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
    [DllImport("user32.dll")] static extern bool IsWindowVisible(IntPtr h);
    [DllImport("user32.dll")] static extern bool GetClientRect(IntPtr h, out RECT r);
    [DllImport("user32.dll")] static extern bool PrintWindow(IntPtr h, IntPtr hdc, uint flags);
    [DllImport("user32.dll")] static extern bool SetProcessDPIAware();
    [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
    public static IntPtr Find(HashSet<uint> pids) {
        IntPtr best = IntPtr.Zero;
        int bestArea = 0;
        EnumWindows(delegate(IntPtr h, IntPtr l) {
            uint pid;
            GetWindowThreadProcessId(h, out pid);
            if (pids.Contains(pid) && IsWindowVisible(h)) {
                RECT r;
                GetClientRect(h, out r);
                int area = (r.Right - r.Left) * (r.Bottom - r.Top);
                if (area > bestArea) { bestArea = area; best = h; }
            }
            return true;
        }, IntPtr.Zero);
        return best;
    }
    public static string Shot(IntPtr h, string path) {
        SetProcessDPIAware();
        RECT r;
        GetClientRect(h, out r);
        int w = r.Right - r.Left, ht = r.Bottom - r.Top;
        if (w <= 0 || ht <= 0) return "error: empty client area (minimized?)";
        using (Bitmap bmp = new Bitmap(w, ht, PixelFormat.Format32bppArgb)) {
            using (Graphics g = Graphics.FromImage(bmp)) {
                IntPtr hdc = g.GetHdc();
                bool ok = PrintWindow(h, hdc, 3);
                g.ReleaseHdc(hdc);
                if (!ok) return "error: PrintWindow failed";
            }
            bmp.Save(path, ImageFormat.Png);
        }
        return "ok " + w + "x" + ht;
    }
}
"@
$pids = New-Object 'System.Collections.Generic.HashSet[uint32]'
if ($TargetPid -gt 0) {
    [void]$pids.Add([uint32]$TargetPid)
    Get-CimInstance Win32_Process -Filter "ParentProcessId=$TargetPid" | ForEach-Object { [void]$pids.Add([uint32]$_.ProcessId) }
}
if ($Name) { Get-Process -Name $Name -ErrorAction SilentlyContinue | ForEach-Object { [void]$pids.Add([uint32]$_.Id) } }
$h = [UdShot]::Find($pids)
if ($h -eq [IntPtr]::Zero) { Write-Output "error: no visible window for those processes"; exit 2 }
Write-Output ([UdShot]::Shot($h, $Out))
