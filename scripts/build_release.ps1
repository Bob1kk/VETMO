# VETMO release build:
#   tests -> VETMO.exe + VETMO-Admin.exe -> secret/scope scan -> installers -> smoke.
# Usage:
#   .\scripts\build_release.ps1
#   .\scripts\build_release.ps1 -SkipTests -IsccPath "C:\...\ISCC.exe"
#   .\scripts\build_release.ps1 -SkipInstaller -SkipSmoke
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
$UserExe = Join-Path $Root "dist\VETMO.exe"
$AdminExe = Join-Path $Root "dist\VETMO-Admin.exe"
$ReleaseDir = Join-Path $Root "release"

function Write-Step([string]$Text) {
    Write-Host ""
    Write-Host "==> $Text" -ForegroundColor Cyan
}

function Write-Ok([string]$Text) {
    Write-Host "OK: $Text" -ForegroundColor Green
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
        Write-Ok "$Label запускается с чистым APPDATA и без secret-файлов."
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

function Invoke-AdminSelfCheck([string]$ExePath, [string]$Label) {
    Write-Step "Смоук ${Label}: --self-check с заведомо отсутствующими секретами"
    $tempRoot = Join-Path ([IO.Path]::GetTempPath()) ("vetmo-admin-check-" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $tempRoot | Out-Null
    $oldAppData = $env:APPDATA
    $oldQt = $env:QT_QPA_PLATFORM
    $oldSecrets = $env:VETMO_SYNC_SECRETS_FILE
    $process = $null
    try {
        $env:APPDATA = $tempRoot
        $env:QT_QPA_PLATFORM = "offscreen"
        # Гарантируем отсутствие секретов: путь заведомо не существует.
        $env:VETMO_SYNC_SECRETS_FILE = Join-Path $tempRoot "no-such-secrets.env"
        $process = Start-Process -FilePath $ExePath -WorkingDirectory (Split-Path $ExePath) `
            -ArgumentList "--self-check" -PassThru
        if (-not $process.WaitForExit(120000)) {
            & taskkill.exe /PID $process.Id /T /F 2>$null | Out-Null
            throw "${Label}: --self-check не завершился за 120 секунд"
        }
        if ($process.ExitCode -ne 2) {
            throw "${Label}: --self-check вернул код $($process.ExitCode), ожидался 2 (нет секретов)"
        }
        $logPath = Join-Path $tempRoot "VETMO\logs\vetmo.log"
        if (-not (Test-Path -LiteralPath $logPath)) {
            throw "${Label}: --self-check не создал лог $logPath"
        }
        $log = Get-Content -LiteralPath $logPath -Raw
        if ($log -notmatch "Self-check") {
            throw "${Label}: в логе нет записи Self-check"
        }
        $unexpected = @(Get-ChildItem -LiteralPath $tempRoot -Recurse -File -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -in @("secrets.env", ".env") })
        if ($unexpected.Count -gt 0) {
            throw "${Label}: приложение создало файл секретов: $($unexpected[0].FullName)"
        }
        Write-Ok "${Label}: --self-check возвращает 2 без секретов и пишет лог."
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
        if ($null -ne $oldSecrets) {
            $env:VETMO_SYNC_SECRETS_FILE = $oldSecrets
        }
        else {
            Remove-Item Env:VETMO_SYNC_SECRETS_FILE -ErrorAction SilentlyContinue
        }
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

function Get-SecretValues {
    $secretsPath = Join-Path $env:APPDATA "VETMO\secrets.env"
    $values = @()
    if (-not (Test-Path -LiteralPath $secretsPath)) {
        Write-Host "secrets.env отсутствует — проверка значений секретов пропущена." -ForegroundColor Yellow
        return $values
    }
    foreach ($line in Get-Content -LiteralPath $secretsPath) {
        if ($line -match "^\s*([^#=]+)=(.*)$") {
            $name = $Matches[1].Trim()
            $value = $Matches[2].Trim()
            if ($name -match "SERVICE_KEY|STRATZ_TOKEN|SECRET|PASSWORD" -and $value.Length -ge 8) {
                $values += $value
            }
        }
    }
    return $values
}

function Assert-NoSecretValues([string]$ExePath, [string[]]$SecretValues, [string]$Label) {
    if ($SecretValues.Count -eq 0) {
        return
    }
    $bytes = [IO.File]::ReadAllBytes($ExePath)
    try {
        $haystack = [Text.Encoding]::UTF8.GetString($bytes)
        foreach ($value in $SecretValues) {
            if ($haystack.Contains($value)) {
                throw "${Label}: значение секрета из secrets.env найдено в exe"
            }
        }
    }
    finally {
        Remove-Variable bytes -ErrorAction SilentlyContinue
    }
    Write-Ok "${Label}: проверено секретов: $($SecretValues.Count), в exe не найдено."
}

function Assert-ExeMarkers([string]$ExePath, [string[]]$Forbidden, [string]$Label) {
    $bytes = [IO.File]::ReadAllBytes($ExePath)
    try {
        $haystack = [Text.Encoding]::UTF8.GetString($bytes)
        $found = @($Forbidden | Where-Object { $haystack.Contains($_) })
        if ($found.Count -gt 0) {
            throw "${Label}: найдены запрещённые маркеры: $($found -join ', ')"
        }
    }
    finally {
        Remove-Variable bytes -ErrorAction SilentlyContinue
    }
    Write-Ok "${Label}: запрещённых строк нет."
}

function Assert-ArchiveModules(
    [string]$ExePath,
    [string[]]$ForbiddenModules,
    [string[]]$RequiredModules,
    [string]$Label
) {
    $archiveList = & $Python -m PyInstaller.utils.cliutils.archive_viewer -r -b $ExePath
    if ($LASTEXITCODE -ne 0) {
        throw "${Label}: не удалось прочитать список модулей"
    }
    $archiveText = $archiveList -join "`n"
    $foundForbidden = @($ForbiddenModules | Where-Object { $archiveText.Contains($_) })
    if ($foundForbidden.Count -gt 0) {
        throw "${Label}: в сборку попали запрещённые модули: $($foundForbidden -join ', ')"
    }
    $missing = @($RequiredModules | Where-Object { -not $archiveText.Contains($_) })
    if ($missing.Count -gt 0) {
        throw "${Label}: в сборке нет обязательных модулей: $($missing -join ', ')"
    }
    Write-Ok "${Label}: состав модулей соответствует ожидаемому."
}

function Invoke-PyInstaller([string]$SpecName, [string]$ExePath, [string]$BuildLabel) {
    Write-Step "Сборка $BuildLabel (PyInstaller)"
    Remove-Item -LiteralPath (Join-Path $Root "build\$BuildLabel") -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $ExePath -Force -ErrorAction SilentlyContinue
    Invoke-Checked $Python @(
        "-m", "PyInstaller", $SpecName, "--noconfirm", "--clean"
    ) "PyInstaller ($BuildLabel) завершился с ошибкой"
    if (-not (Test-Path -LiteralPath $ExePath)) {
        throw "PyInstaller не создал $ExePath"
    }
}

function Invoke-InstallerBuild(
    [string]$Iscc, [string]$IssName, [string]$SetupPath, [string]$Label
) {
    Write-Step "Сборка установщика $Label (Inno Setup)"
    New-Item -ItemType Directory -Path $ReleaseDir -Force | Out-Null
    Remove-Item -LiteralPath $SetupPath -Force -ErrorAction SilentlyContinue
    Invoke-Checked $Iscc @(
        "/DMyAppVersion=$Version", (Join-Path $Root "installer\$IssName")
    ) "Inno Setup ($Label) завершился с ошибкой"
    if (-not (Test-Path -LiteralPath $SetupPath)) {
        throw "Установщик $Label не создан: $SetupPath"
    }
    Write-Ok "установщик $Label собран."
}

function Invoke-InstallerRoundTrip(
    [string]$SetupExe, [string]$ExeName, [string]$Label, [switch]$Admin
) {
    Write-Step "Проверка установщика ${Label}: тихая установка -> запуск -> удаление"
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
        $install = Start-Process -FilePath $SetupExe -ArgumentList $installArgs -Wait -PassThru
        if ($install.ExitCode -ne 0) {
            throw "Установщик ${Label} вернул код $($install.ExitCode)"
        }
        $installedExe = Join-Path $installDir $ExeName
        if (-not (Test-Path -LiteralPath $installedExe)) {
            throw "После установки не найден $installedExe"
        }
        if (-not $SkipSmoke) {
            if ($Admin) {
                Invoke-AdminSelfCheck -ExePath $installedExe -Label "Установленный $ExeName"
            }
            else {
                Invoke-FileSmoke -ExePath $installedExe -Label "Установленный $ExeName" -WorkingDirectory $installDir
            }
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
            throw "Uninstaller ($Label) не удалил каталог установки"
        }
        Write-Ok "установщик $Label устанавливает и удаляет приложение."
    }
    finally {
        Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
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

    $secretValues = @(Get-SecretValues)

    # --- пользовательская сборка: без admin/sync-кода и секретов ---
    Invoke-PyInstaller "vetmo.spec" $UserExe "vetmo"

    Write-Step "Проверка, что в VETMO.exe нет admin/sync-кода и секретов"
    Assert-ExeMarkers $UserExe @(
        "service_role",
        "stratz_sync",
        "stratz_client",
        "VETMO_SYNC_SERVICE_KEY",
        "VETMO_SYNC_STRATZ_TOKEN",
        "vetmo.admin",
        "vetmo.infra.sync_settings"
    ) "VETMO.exe"
    Assert-ArchiveModules $UserExe `
        @(
            "vetmo.admin",
            "vetmo.infra.sync_settings",
            "vetmo.services.stratz_client",
            "vetmo.services.stratz_sync",
            "vetmo.services.stratz_aggregate"
        ) `
        @("vetmo.infra.public_config") `
        "VETMO.exe"
    Assert-NoSecretValues $UserExe $secretValues "VETMO.exe"

    # --- админская сборка: содержит admin/sync-код, но не значения секретов ---
    Invoke-PyInstaller "vetmo-admin.spec" $AdminExe "vetmo-admin"

    Write-Step "Проверка, что VETMO-Admin.exe содержит admin/sync-код и без секретов"
    Assert-ArchiveModules $AdminExe `
        @() `
        @("vetmo.admin", "vetmo.services.stratz_sync") `
        "VETMO-Admin.exe"
    Assert-NoSecretValues $AdminExe $secretValues "VETMO-Admin.exe"

    if (-not $SkipSmoke) {
        Write-Step "Smoke-запуск сборок"
        Invoke-FileSmoke -ExePath $UserExe -Label "VETMO.exe" -WorkingDirectory (Split-Path $UserExe)
        Invoke-AdminSelfCheck -ExePath $AdminExe -Label "VETMO-Admin.exe"
    }

    if ($SkipInstaller) {
        Write-Step "Установщики пропущены (-SkipInstaller)"
        return
    }

    $iscc = Find-Iscc $IsccPath
    $userSetup = Join-Path $ReleaseDir "VETMO-Setup-$Version.exe"
    $adminSetup = Join-Path $ReleaseDir "VETMO-Admin-Setup-$Version.exe"

    Invoke-InstallerBuild $iscc "VETMO.iss" $userSetup "VETMO (пользователь)"
    Invoke-InstallerBuild $iscc "VETMO-Admin.iss" $adminSetup "VETMO Admin"

    Invoke-InstallerRoundTrip $userSetup "VETMO.exe" "VETMO (пользователь)"
    Invoke-InstallerRoundTrip $adminSetup "VETMO-Admin.exe" "VETMO Admin" -Admin

    Write-Step "Готово"
    Write-Host "EXE (пользователь): $UserExe"
    Write-Host "EXE (admin):        $AdminExe"
    Write-Host "Установщик:         $userSetup"
    Write-Host "Установщик admin:   $adminSetup"
}
finally {
    Pop-Location
}
