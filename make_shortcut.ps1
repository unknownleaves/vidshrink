# Creates a "VidShrink" shortcut with the app icon on the Desktop and in the Start menu.
$dir = $PSScriptRoot
$exe = Join-Path $dir 'dist\VidShrink.exe'
$ico = Join-Path $dir 'vidshrink.ico'
$ws  = New-Object -ComObject WScript.Shell

if (Test-Path $exe) {
    $target = $exe; $arguments = ''
} else {
    $py = (Get-Command pythonw -ErrorAction SilentlyContinue).Source
    if (-not $py) { $py = (Get-Command pyw -ErrorAction SilentlyContinue).Source }
    if (-not $py) {
        Write-Host 'Python was not found. Install it from https://www.python.org/downloads/ first.'
        exit 1
    }
    $target = $py; $arguments = '"' + (Join-Path $dir 'vidshrink.py') + '"'
}

$places = @(
    [Environment]::GetFolderPath('Desktop'),
    [Environment]::GetFolderPath('Programs')
)
foreach ($place in $places) {
    $lnk = $ws.CreateShortcut((Join-Path $place 'VidShrink.lnk'))
    $lnk.TargetPath = $target
    $lnk.Arguments = $arguments
    $lnk.WorkingDirectory = $dir
    $lnk.IconLocation = "$ico,0"
    $lnk.Description = 'VidShrink - video compressor'
    $lnk.Save()
}
Write-Host 'VidShrink shortcut created on your Desktop and in the Start menu.'
