$ErrorActionPreference = 'Stop'
$ctrlRoot = Split-Path -Parent $PSScriptRoot
$ctrlDesktop = [Environment]::GetFolderPath('Desktop')
$ctrlPowerShell = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$ctrlShell = New-Object -ComObject WScript.Shell
try {
    foreach ($ctrlItem in @(
        @{ Name='CTRL Hybrid Experiment.lnk'; Script='Start-CTRL.ps1'; Extra='-STA'; Description='Start the isolated TipTour Windows browser adaptation: Gemini planner + Jev.' },
        @{ Name='CTRL Hybrid Control Panel.lnk'; Script='scripts\Control-CTRL.ps1'; Extra='-STA'; Description='Open only the hybrid experiment control panel. Ctrl+Alt+Shift+H stops this experiment.' },
        @{ Name='STOP CTRL Hybrid.lnk'; Script='Stop-CTRL.ps1'; Extra=''; Description='Turn off only the isolated CTRL hybrid experiment. Chrome remains open.' }
    )) {
        $ctrlShortcut = $ctrlShell.CreateShortcut((Join-Path $ctrlDesktop $ctrlItem.Name))
        $ctrlShortcut.TargetPath = $ctrlPowerShell
        $ctrlShortcut.Arguments = '-NoProfile -ExecutionPolicy Bypass ' + $ctrlItem.Extra + ' -File "' + (Join-Path $ctrlRoot $ctrlItem.Script) + '"'
        if ($ctrlItem.Script -eq 'Stop-CTRL.ps1') { $ctrlShortcut.Arguments += ' -Force' }
        $ctrlShortcut.WorkingDirectory = $ctrlRoot
        $ctrlShortcut.WindowStyle = 7
        $ctrlShortcut.Description = $ctrlItem.Description
        $ctrlShortcut.Save()
    }
} finally { [System.Runtime.InteropServices.Marshal]::ReleaseComObject($ctrlShell) | Out-Null }
Write-Output '[CTRL] Hybrid experiment shortcuts installed. Baseline CTRL shortcuts are unchanged.'
