# VETMO release build: tests -> VETMO.exe -> secret scan -> installer -> smoke.
# Usage:
#   .\scripts\build_release.ps1
#   .\scripts\build_release.ps1 -SkipTests -IsccPath "C:\...\ISCC.exe"
[CmdletBinding()]
param(
    [string]$Version = "",
    [string]$IsccPath = "",
    [switch]$SkipTests,
    [switch]$SkipInstaller,
    [switch]$SkipSmoke
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$OutputEncoding = [Text.Encoding]::UTF8

$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$DistExe = Join-Path $Root "dist\VETMO.exe"
$ReleaseDir = Join-Path $Root "release"

function Write-Step([string]$Text) {
    Write-Host ""
    Write-Host "==> $Text" -ForegroundColor Cyan
}

function Invoke-Checked([string]$FilePath, [string[]]$Arguments, [string]$ErrorMessage) {
    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$ErrorMessage (exit code $LASTEXITCODE)"
    }
}

function Invoke-FileSmoke([string]$ExePath, [string]$Label, [string]$WorkingDirectory) {
    $tempRoot = Join-Path ([IO.Path]::GetTempPath()) ("vetmo-smoke-" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $tempRoot | Out-Null
    $oldAppData = $env:APPDATA
    $oldQt = $env:QT_QPA_PLATFORM
    $process = $null
    try {
        $env:APPDATA = $tempRoot
        $env:QT_QPA_PLATFORM = "offscreen"
        $process = Start-Process -FilePath $ExePath -WorkingDirectory $WorkingDirectory -PassThru
        Start-Sleep -Seconds 12
        $process.Refresh()
        if ($process.HasExited) {
            throw "${Label}: процесс завершился с кодом $($process.ExitCode)"
        }
        $logPath = Join-Path $tempRoot "VETMO\logs\vetmo.log"
        if (-not (Test-Path -LiteralPath $logPath)) {
            throw "${Label}: не создан лог $logPath"
        }
        $log = Get-Content -LiteralPath $logPath -Raw
        if ($log -match "Traceback \(most recent call last\)") {
            throw "${Label}: в логе есть Traceback"
        }
        $unexpected = @(Get-ChildItem -LiteralPath $tempRoot -Recurse -File -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -in @("secrets.env", ".env") })
        if ($unexpected.Count -gt 0) {
            throw "${Label}: приложение создало файл секретов: $($unexpected[0].FullName)"
        }
        Write-Host "OK: $Label запускается с чистым APPDATA и без secret-файлов." -ForegroundColor Green
    }
    finally {
        if ($null -ne $process) {
            $process.Refresh()
            if (-not $process.HasExited) {
                & taskkill.exe /PID $process.Id /T /F 2>$null | Out-Null
            }
        }
        $env:APPDATA = $oldAppData
        $env:QT_QPA_PLATFORM = $oldQt
        Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}

function Find-Iscc([string]$ExplicitPath) {
    if ($ExplicitPath) {
        if (-not (Test-Path -LiteralPath $ExplicitPath)) {
            throw "ISCC.exe не найден: $ExplicitPath"
        }
        return (Resolve-Path -LiteralPath $ExplicitPath).Path
    }
    $command = Get-Command iscc.exe -ErrorAction SilentlyContinue
    if ($null -ne $command) {
        return $command.Source
    }
    $candidates = @(
        (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"),
        "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        "C:\Program Files\Inno Setup 6\ISCC.exe",
        (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 7\ISCC.exe"),
        "C:\Program Files\Inno Setup 7\ISCC.exe"
    )
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate) {
            return $candidate
        }
    }
    throw "Inno Setup 6.7+ не найден. Установите его или передайте -IsccPath <путь к ISCC.exe>."
}

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Не найден $Python. Создайте окружение: py -3.12 -m uv sync"
}

$initPath = Join-Path $Root "src\vetmo\__init__.py"
$initText = Get-Content -LiteralPath $initPath -Raw
if ($initText -notmatch '__version__\s*=\s*"([^"]+)"') {
    throw "Не удалось прочитать версию из src\vetmo\__init__.py"
}
$detectedVersion = $Matches[1]
if (-not $Version) {
    $Version = $detectedVersion
}
$Version = $Version.TrimStart("v")

$running = @(Get-Process -Name "VETMO", "VETMO-Admin" -ErrorAction SilentlyContinue)
if ($running.Count -gt 0) {
    throw "Закройте запущенные VETMO/VETMO-Admin перед сборкой (найдено процессов: $($running.Count))."
}

Push-Location $Root
try {
    Write-Step "Версия: $Version"

    if (-not $SkipTests) {
        Write-Step "Тесты и проверки"
        Invoke-Checked $Python @("-m", "pytest", "-q") "Тесты не прошли"
        Invoke-Checked $Python @("-m", "ruff", "check", "src", "tests") "ruff нашёл ошибки"
        Invoke-Checked $Python @("-m", "mypy", "src/vetmo", "--ignore-missing-imports") "mypy нашёл ошибки"
    }

    Write-Step "Сборка dist\VETMO.exe (PyInstaller)"
    Remove-Item -LiteralPath (Join-Path $Root "build\vetmo") -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $DistExe -Force -ErrorAction SilentlyContinue
    Invoke-Checked $Python @("-m", "PyInstaller", "vetmo.spec", "--noconfirm", "--clean") "PyInstaller завершился с ошибкой"
    if (-not (Test-Path -LiteralPath $DistExe)) {
        throw "PyInstaller не создал $DistExe"
    }

    Write-Step "Проверка, что в VETMO.exe нет admin/sync-кода и секретов"
    $bytes = [IO.File]::ReadAllBytes($DistExe)
    $haystack = [Text.Encoding]::UTF8.GetString($bytes)
    $markers = @(
        "service_role",
        "stratz_sync",
        "stratz_client",
        "VETMO_SYNC_SERVICE_KEY",
        "VETMO_SYNC_STRATZ_TOKEN",
        "vetmo.admin",
        "vetmo.infra.sync_settings"
    )
    $foundMarkers = @($markers | Where-Object { $haystack.Contains($_) })
    if ($foundMarkers.Count -gt 0) {
        throw "В пользовательской сборке найдены запрещённые маркеры: $($foundMarkers -join ', ')"
    }

    $archiveList = & $Python -m PyInstaller.utils.cliutils.archive_viewer -r -b $DistExe
    if ($LASTEXITCODE -ne 0) {
        throw "Не удалось прочитать список модулей VETMO.exe"
    }
    $archiveText = $archiveList -join "`n"
    $forbiddenModules = @(
        "vetmo.admin",
        "vetmo.infra.sync_settings",
        "vetmo.services.stratz_client",
        "vetmo.services.stratz_sync",
        "vetmo.services.stratz_aggregate"
    )
    $foundModules = @($forbiddenModules | Where-Object { $archiveText.Contains($_) })
    if ($foundModules.Count -gt 0) {
        throw "В VETMO.exe попали admin/sync-модули: $($foundModules -join ', ')"
    }
    if (-not $archiveText.Contains("vetmo.infra.public_config")) {
        throw "В VETMO.exe нет публичной конфигурации Supabase"
    }
    Write-Host "OK: admin/sync-модулей нет, публичная конфигурация Supabase включена." -ForegroundColor Green

    $secretsPath = Join-Path $env:APPDATA "VETMO\secrets.env"
    if (Test-Path -LiteralPath $secretsPath) {
        $secretValues = @()
        foreach ($line in Get-Content -LiteralPath $secretsPath) {
            if ($line -match "^\s*([^#=]+)=(.*)$") {
                $name = $Matches[1].Trim()
                $value = $Matches[2].Trim()
                if ($name -match "SERVICE_KEY|STRATZ_TOKEN|SECRET|PASSWORD" -and $value.Length -ge 8) {
                    $secretValues += $value
                }
            }
        }
        foreach ($value in $secretValues) {
            if ($haystack.Contains($value)) {
                throw "Значение секрета из secrets.env найдено в VETMO.exe"
            }
        }
        Write-Host "OK: проверено секретов: $($secretValues.Count), в exe не найдено." -ForegroundColor Green
    }
    else {
        Write-Host "secrets.env отсутствует — проверка значений секретов пропущена." -ForegroundColor Yellow
    }
    Remove-Variable bytes, haystack

    if (-not $SkipSmoke) {
        Write-Step "Smoke-запуск VETMO.exe с чистым APPDATA"
        Invoke-FileSmoke -ExePath $DistExe -Label "VETMO.exe" -WorkingDirectory (Split-Path $DistExe)
    }

    if ($SkipInstaller) {
        Write-Step "Установщик пропущен (-SkipInstaller)"
        return
    }

    Write-Step "Сборка установщика (Inno Setup)"
    $iscc = Find-Iscc $IsccPath
    New-Item -ItemType Directory -Path $ReleaseDir -Force | Out-Null
    $setupExe = Join-Path $ReleaseDir "VETMO-Setup-$Version.exe"
    Remove-Item -LiteralPath $setupExe -Force -ErrorAction SilentlyContinue
    Invoke-Checked $iscc @("/DMyAppVersion=$Version", (Join-Path $Root "installer\VETMO.iss")) "Inno Setup завершился с ошибкой"
    if (-not (Test-Path -LiteralPath $setupExe)) {
        throw "Установщик не создан: $setupExe"
    }

    Write-Step "Проверка установщика: тихая установка -> запуск -> удаление"
    $tempRoot = Join-Path ([IO.Path]::GetTempPath()) ("vetmo-installer-" + [guid]::NewGuid().ToString("N"))
    $installDir = Join-Path $tempRoot "app"
    New-Item -ItemType Directory -Path $tempRoot | Out-Null
    try {
        $installArgs = @(
            "/VERYSILENT",
            "/SUPPRESSMSGBOXES",
            "/NORESTART",
            "/SP-",
            "/NOICONS",
            "/DIR=`"$installDir`""
        )
        $install = Start-Process -FilePath $setupExe -ArgumentList $installArgs -Wait -PassThru
        if ($install.ExitCode -ne 0) {
            throw "Установщик вернул код $($install.ExitCode)"
        }
        $installedExe = Join-Path $installDir "VETMO.exe"
        if (-not (Test-Path -LiteralPath $installedExe)) {
            throw "После установки не найден $installedExe"
        }
        if (-not $SkipSmoke) {
            Invoke-FileSmoke -ExePath $installedExe -Label "Установленный VETMO.exe" -WorkingDirectory $installDir
        }
        $uninstaller = Join-Path $installDir "unins000.exe"
        if (-not (Test-Path -LiteralPath $uninstaller)) {
            throw "Не найден unins000.exe"
        }
        $uninstall = Start-Process -FilePath $uninstaller -ArgumentList @(
            "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"
        ) -Wait -PassThru
        for ($i = 0; $i -lt 30 -and (Test-Path -LiteralPath $installDir); $i++) {
            Start-Sleep -Milliseconds 500
        }
        if (Test-Path -LiteralPath $installDir) {
            throw "Uninstaller не удалил каталог установки"
        }
        Write-Host "OK: установщик устанавливает и удаляет приложение." -ForegroundColor Green
    }
    finally {
        Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
    }

    Write-Step "Контрольные суммы"
    $sums = foreach ($file in @($DistExe, $setupExe)) {
        $hash = Get-FileHash -LiteralPath $file -Algorithm SHA256
        "{0}  {1}" -f $hash.Hash.ToLowerInvariant(), [IO.Path]::GetFileName($file)
    }
    $sumsPath = Join-Path $ReleaseDir "SHA256SUMS.txt"
    $sums | Set-Content -LiteralPath $sumsPath -Encoding ASCII

    Write-Step "Готово"
    Write-Host "EXE:        $DistExe"
    Write-Host "Установщик: $setupExe"
    Write-Host "SHA256:     $sumsPath"
}
finally {
    Pop-Location
}
