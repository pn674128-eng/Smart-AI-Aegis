param(
    [switch]$SafeModeOnly
)

$ErrorActionPreference = "SilentlyContinue"

Write-Host "=== Antigravity IDE Repair ===" -ForegroundColor Cyan

function Stop-AntigravityProcesses {
    Write-Host "[1/5] Stopping Antigravity related processes..."
    $names = @(
        "Antigravity",
        "antigravity",
        "Code"
    )
    foreach ($n in $names) {
        Get-Process -Name $n -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Milliseconds 500
}

function Clear-AntigravityCaches {
    Write-Host "[2/5] Clearing cache folders (Cache/Code Cache/GPUCache)..."
    $scanRoots = @(
        $env:APPDATA,
        $env:LOCALAPPDATA
    )

    foreach ($root in $scanRoots) {
        if (-not (Test-Path $root)) { continue }
        Get-ChildItem -Path $root -Directory -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -match "antigravity" } |
            ForEach-Object {
                $base = $_.FullName
                Remove-Item (Join-Path $base "Cache") -Recurse -Force -ErrorAction SilentlyContinue
                Remove-Item (Join-Path $base "Code Cache") -Recurse -Force -ErrorAction SilentlyContinue
                Remove-Item (Join-Path $base "GPUCache") -Recurse -Force -ErrorAction SilentlyContinue
            }
    }
}

function Find-AntigravityExe {
    $shortcutCandidates = @(
        (Join-Path $env:USERPROFILE "Desktop\Antigravity IDE.lnk"),
        (Join-Path ([Environment]::GetFolderPath("CommonDesktopDirectory")) "Antigravity IDE.lnk")
    )
    foreach ($lnk in $shortcutCandidates) {
        if (-not (Test-Path $lnk)) { continue }
        try {
            $ws = New-Object -ComObject WScript.Shell
            $sc = $ws.CreateShortcut($lnk)
            $target = [string]$sc.TargetPath
            if ($target -and (Test-Path $target) -and $target.ToLower().EndsWith(".exe")) {
                return $target
            }
        } catch {}
    }

    $candidates = @(
        (Join-Path $env:LOCALAPPDATA "Programs\Antigravity\Antigravity.exe"),
        (Join-Path $env:LOCALAPPDATA "Antigravity\Antigravity.exe"),
        (Join-Path $env:ProgramFiles "Antigravity\Antigravity.exe"),
        (Join-Path ${env:ProgramFiles(x86)} "Antigravity\Antigravity.exe")
    )
    foreach ($p in $candidates) {
        if (Test-Path $p) { return $p }
    }
    return $null
}

function Start-Antigravity {
    param(
        [Parameter(Mandatory=$true)][string]$ExePath,
        [switch]$Safe
    )
    if ($Safe) {
        Write-Host "[4/5] Starting Antigravity in safe GPU mode..."
        Start-Process -FilePath $ExePath -ArgumentList "--disable-gpu --disable-software-rasterizer"
    } else {
        Write-Host "[3/5] Starting Antigravity normally..."
        Start-Process -FilePath $ExePath
    }
}

Stop-AntigravityProcesses
Clear-AntigravityCaches

$exe = Find-AntigravityExe
if (-not $exe) {
    Write-Host "Antigravity.exe not found. Reinstall Antigravity IDE first." -ForegroundColor Yellow
    exit 1
}

if ($SafeModeOnly) {
    Start-Antigravity -ExePath $exe -Safe
    Write-Host "[Done] Safe mode launch attempted." -ForegroundColor Green
    exit 0
}

Start-Antigravity -ExePath $exe
Start-Sleep -Seconds 3

$running = Get-Process -Name "Antigravity" -ErrorAction SilentlyContinue
if (-not $running) {
    Write-Host "[5/5] Normal launch did not stay alive. Retrying in safe GPU mode..." -ForegroundColor Yellow
    Start-Antigravity -ExePath $exe -Safe
} else {
    Write-Host "[5/5] Antigravity is running." -ForegroundColor Green
}

Write-Host "Repair flow finished." -ForegroundColor Cyan
