# VidShrink installer for Windows. Run this in PowerShell:
#
#   irm https://raw.githubusercontent.com/unknownleaves/vidshrink/main/install.ps1 | iex
#
# Installs the latest VidShrink.exe to %LOCALAPPDATA%\Programs\VidShrink (no admin needed),
# adds Start menu + Desktop shortcuts and an entry in Settings > Apps for uninstalling.
# Running it again updates or repairs an existing install.

& {
    $ErrorActionPreference = 'Stop'
    $ProgressPreference = 'SilentlyContinue'   # much faster downloads in Windows PowerShell 5.1
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

    $repo    = 'unknownleaves/vidshrink'
    $dir     = Join-Path $env:LOCALAPPDATA 'Programs\VidShrink'
    $exe     = Join-Path $dir 'VidShrink.exe'
    $regKey  = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\VidShrink'
    $headers = @{ 'User-Agent' = 'VidShrink-Installer' }

    try {
        Write-Host ''
        Write-Host '  VidShrink installer' -ForegroundColor Cyan
        Write-Host '  -------------------'

        # --- find the latest release -----------------------------------------
        $rel   = Invoke-RestMethod "https://api.github.com/repos/$repo/releases/latest" -Headers $headers -UseBasicParsing
        $asset = $rel.assets | Where-Object { $_.name -eq 'VidShrink.exe' }
        $sums  = $rel.assets | Where-Object { $_.name -eq 'SHA256SUMS.txt' }
        if (-not $asset) { throw 'The latest release has no VidShrink.exe.' }
        $version = $rel.tag_name.TrimStart('v', 'V')

        # --- download + verify -----------------------------------------------
        Write-Host "  Downloading VidShrink $version..."
        $tmp = Join-Path $env:TEMP "VidShrink-$version.exe"
        Invoke-WebRequest $asset.browser_download_url -OutFile $tmp -Headers $headers -UseBasicParsing

        if ($sums) {
            Write-Host '  Verifying download...'
            $sumsFile = Join-Path $env:TEMP 'VidShrink-SHA256SUMS.txt'
            Invoke-WebRequest $sums.browser_download_url -OutFile $sumsFile -Headers $headers -UseBasicParsing
            $line = Get-Content $sumsFile | Where-Object { $_ -match '^\s*([0-9a-fA-F]{64})\s+\*?VidShrink\.exe\s*$' } | Select-Object -First 1
            Remove-Item $sumsFile -ErrorAction SilentlyContinue
            $actual = (Get-FileHash $tmp -Algorithm SHA256).Hash
            if (-not $line -or ($line.Trim() -split '\s+')[0] -ne $actual) {
                Remove-Item $tmp -ErrorAction SilentlyContinue
                throw 'The download failed verification (checksum mismatch). Please try again.'
            }
        }

        # --- install -----------------------------------------------------------
        New-Item -ItemType Directory -Force $dir | Out-Null
        Get-Process VidShrink -ErrorAction SilentlyContinue |
            Where-Object { $_.Path -eq $exe } | Stop-Process -Force -ErrorAction SilentlyContinue
        Start-Sleep -Milliseconds 800
        Move-Item $tmp $exe -Force
        Unblock-File $exe -ErrorAction SilentlyContinue

        # --- shortcuts -----------------------------------------------------------
        $ws = New-Object -ComObject WScript.Shell
        foreach ($folder in @([Environment]::GetFolderPath('Programs'), [Environment]::GetFolderPath('Desktop'))) {
            $lnk = $ws.CreateShortcut((Join-Path $folder 'VidShrink.lnk'))
            $lnk.TargetPath = $exe
            $lnk.WorkingDirectory = $dir
            $lnk.IconLocation = "$exe,0"
            $lnk.Description = 'VidShrink - video compressor'
            $lnk.Save()
        }

        # --- uninstaller + Settings > Apps entry -------------------------------
        $uninstall = Join-Path $dir 'uninstall.ps1'
        @'
$ErrorActionPreference = 'SilentlyContinue'
$dir = Join-Path $env:LOCALAPPDATA 'Programs\VidShrink'
Get-Process VidShrink | Where-Object { $_.Path -like "$dir\*" } | Stop-Process -Force
Start-Sleep -Milliseconds 800
Remove-Item (Join-Path ([Environment]::GetFolderPath('Programs')) 'VidShrink.lnk') -Force
Remove-Item (Join-Path ([Environment]::GetFolderPath('Desktop')) 'VidShrink.lnk') -Force
Remove-Item 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\VidShrink' -Recurse -Force
Remove-Item (Join-Path $env:LOCALAPPDATA 'VidShrink') -Recurse -Force   # downloaded FFmpeg
Remove-Item $dir -Recurse -Force
'@ | Set-Content -Path $uninstall -Encoding UTF8

        New-Item -Path $regKey -Force | Out-Null
        $props = @{
            DisplayName     = 'VidShrink'
            DisplayVersion  = $version
            DisplayIcon     = "$exe,0"
            Publisher       = 'unknownleaves'
            InstallLocation = $dir
            URLInfoAbout    = "https://github.com/$repo"
            UninstallString = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$uninstall`""
        }
        foreach ($k in $props.Keys) { Set-ItemProperty -Path $regKey -Name $k -Value $props[$k] }
        Set-ItemProperty -Path $regKey -Name NoModify -Value 1 -Type DWord
        Set-ItemProperty -Path $regKey -Name NoRepair -Value 1 -Type DWord

        Write-Host "  Installed VidShrink $version to $dir" -ForegroundColor Green
        Write-Host '  Shortcuts added to the Start menu and Desktop. Launching...'
        Write-Host ''
        Start-Process $exe
    }
    catch {
        Write-Host ''
        Write-Host "  Installation failed: $($_.Exception.Message)" -ForegroundColor Red
        Write-Host "  You can also download VidShrink.exe from https://github.com/$repo/releases/latest"
        Write-Host ''
    }
}
