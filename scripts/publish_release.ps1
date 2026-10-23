# VETMO release publishing:
#   создаёт (или обновляет) GitHub Release и прикрепляет установщики из release/.
# Usage:
#   .\scripts\publish_release.ps1
#   .\scripts\publish_release.ps1 -Tag v0.1.0 -NotesFile release-notes.md
#   .\scripts\publish_release.ps1 -Draft
#   .\scripts\publish_release.ps1 -KeepExistingAssets
#
# Токен берётся из $env:GH_TOKEN / $env:GITHUB_TOKEN, иначе — из Git Credential
# Manager (git credential fill для github.com). Нужен scope "repo".
[CmdletBinding()]
param(
    [string]$Version = "",
    [string]$Tag = "",
    [string]$TargetBranch = "release/public-installer",
    [string]$Name = "",
    [string]$NotesFile = "",
    [switch]$Draft,
    [switch]$Prerelease,
    [switch]$KeepExistingAssets
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$OutputEncoding = [Text.Encoding]::UTF8

$Root = Split-Path -Parent $PSScriptRoot
$ReleaseDir = Join-Path $Root "release"

function Write-Step([string]$Text) {
    Write-Host ""
    Write-Host "==> $Text" -ForegroundColor Cyan
}

function Write-Ok([string]$Text) {
    Write-Host "OK: $Text" -ForegroundColor Green
}

function Get-GitHubToken {
    foreach ($envName in @("GH_TOKEN", "GITHUB_TOKEN")) {
        $value = [Environment]::GetEnvironmentVariable($envName)
        if ($value) {
            return $value
        }
    }
    $psi = New-Object Diagnostics.ProcessStartInfo
    $psi.FileName = "git"
    $psi.Arguments = "credential fill"
    $psi.RedirectStandardInput = $true
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.UseShellExecute = $false
    $proc = [Diagnostics.Process]::Start($psi)
    $proc.StandardInput.Write("protocol=https`nhost=github.com`n`n")
    $proc.StandardInput.Close()
    $stdout = $proc.StandardOutput.ReadToEnd()
    [void]$proc.StandardError.ReadToEnd()
    $proc.WaitForExit()
    foreach ($line in ($stdout -split "`r?`n")) {
        if ($line -match '^password=(.+)$') {
            return $Matches[1]
        }
    }
    throw 'Не найден токен GitHub: задайте $env:GH_TOKEN или войдите через git (Git Credential Manager).'
}

function Get-RepoSlug {
    $remoteUrl = (& git remote get-url origin).Trim()
    if ($remoteUrl -notmatch 'github\.com[:/](?<owner>[^/]+)/(?<repo>[^/]+?)(\.git)?$') {
        throw "Не удалось определить owner/repo из origin: $remoteUrl"
    }
    return @{ Owner = $Matches['owner']; Repo = $Matches['repo'] }
}

function New-DefaultNotes([string]$AppVersion) {
    $lines = @(
        "## VETMO $AppVersion",
        "",
        "Помощник в драфте Dota 2 (All Pick): лаунчер с метой и новостями,",
        "прозрачный перетаскиваемый оверлей поверх игры и доска пиков.",
        "",
        "### Установка (игрок)",
        "1. Скачайте ``VETMO-Setup-$AppVersion.exe`` из раздела Assets.",
        "2. Запустите: установка идёт в профиль пользователя",
        "   (``%LOCALAPPDATA%\Programs\VETMO``), права администратора не нужны.",
        "3. Запустите VETMO и нажмите «Оверлей» в лаунчере.",
        "",
        "Требования: Windows 10/11 x64. Python не нужен — всё внутри установщика.",
        "",
        "### VETMO Admin",
        "``VETMO-Admin-Setup-$AppVersion.exe`` — инструмент сопровождения (мета/sync).",
        "Ему нужен ``%APPDATA%\VETMO\secrets.env``; инструкция —",
        "``installer/ADMIN-SETUP.txt`` в репозитории.",
        "",
        "Установщики не подписаны: SmartScreen может предупредить",
        "(«Подробнее» -> «Выполнить всё равно»)."
    )
    return ($lines -join "`n")
}

$initPath = Join-Path $Root "src\vetmo\__init__.py"
$initText = Get-Content -LiteralPath $initPath -Raw -Encoding UTF8
if ($initText -notmatch '__version__\s*=\s*"([^"]+)"') {
    throw "Не удалось прочитать версию из src\vetmo\__init__.py"
}
$detectedVersion = $Matches[1]
if (-not $Version) {
    $Version = $detectedVersion
}
$Version = $Version.TrimStart("v")
if (-not $Tag) {
    $Tag = "v$Version"
}
if (-not $Name) {
    $Name = "VETMO $Version"
}

$assets = @(
    (Join-Path $ReleaseDir "VETMO-Setup-$Version.exe"),
    (Join-Path $ReleaseDir "VETMO-Admin-Setup-$Version.exe")
)
foreach ($assetPath in $assets) {
    if (-not (Test-Path -LiteralPath $assetPath)) {
        throw "Нет файла $assetPath — сначала запустите .\scripts\build_release.ps1"
    }
}

if ($NotesFile) {
    $notesPath = Resolve-Path -LiteralPath $NotesFile
    $body = Get-Content -LiteralPath $notesPath -Raw -Encoding UTF8
} else {
    $body = New-DefaultNotes $Version
}
# Windows PowerShell 5.1: ConvertTo-Json иначе сериализует строку как объект.
$body = [string]$body

Write-Step "Публикация релиза $Tag"
$slug = Get-RepoSlug
$owner = $slug.Owner
$repo = $slug.Repo
Write-Host "Репозиторий: $owner/$repo"

$token = Get-GitHubToken
$headers = @{
    Authorization          = "Bearer $token"
    Accept                 = "application/vnd.github+json"
    "X-GitHub-Api-Version" = "2022-11-28"
    "User-Agent"           = "vetmo-publish-release"
}

$release = $null
$payload = @{
    tag_name         = $Tag
    target_commitish = $TargetBranch
    name             = $Name
    body             = $body
    draft            = [bool]$Draft
    prerelease       = [bool]$Prerelease
} | ConvertTo-Json -Depth 4

try {
    $release = Invoke-RestMethod -Method Post -Uri "https://api.github.com/repos/$owner/$repo/releases" `
        -Headers $headers -Body ([Text.Encoding]::UTF8.GetBytes($payload)) `
        -ContentType "application/json; charset=utf-8" -TimeoutSec 180
    Write-Ok "Релиз создан: $($release.html_url)"
} catch {
    $status = 0
    if ($_.Exception.Response) {
        $status = [int]$_.Exception.Response.StatusCode
    }
    if ($status -ne 422) {
        throw
    }
    Write-Host "Релиз $Tag уже существует — обновляю метаданные."
    $release = Invoke-RestMethod -Uri "https://api.github.com/repos/$owner/$repo/releases/tags/$Tag" `
        -Headers $headers -TimeoutSec 180
    $patch = @{
        name       = $Name
        draft      = [bool]$Draft
        prerelease = [bool]$Prerelease
    }
    if ($NotesFile) {
        $patch['body'] = $body
    }
    $patchJson = $patch | ConvertTo-Json -Depth 4
    $release = Invoke-RestMethod -Method Patch -Uri "https://api.github.com/repos/$owner/$repo/releases/$($release.id)" `
        -Headers $headers -Body ([Text.Encoding]::UTF8.GetBytes($patchJson)) `
        -ContentType "application/json; charset=utf-8" -TimeoutSec 180
    Write-Ok "Релиз обновлён: $($release.html_url)"
}

Write-Step "Загрузка файлов"
$existing = @{}
if ($release.assets) {
    foreach ($asset in $release.assets) {
        $existing[$asset.name] = $asset
    }
}

foreach ($assetPath in $assets) {
    $fileName = Split-Path -Leaf $assetPath
    if ($existing.ContainsKey($fileName)) {
        if ($KeepExistingAssets) {
            Write-Host "Пропускаю $fileName (уже прикреплён, -KeepExistingAssets)."
            continue
        }
        Write-Host "Удаляю предыдущую версию $fileName..."
        Invoke-RestMethod -Method Delete `
            -Uri "https://api.github.com/repos/$owner/$repo/releases/assets/$($existing[$fileName].id)" `
            -Headers $headers -TimeoutSec 180 | Out-Null
    }
    $sizeMiB = [math]::Round((Get-Item -LiteralPath $assetPath).Length / 1MB, 2)
    Write-Host "Загружаю $fileName ($sizeMiB МиБ)..."
    $sw = [Diagnostics.Stopwatch]::StartNew()
    $uploadUri = "https://uploads.github.com/repos/$owner/$repo/releases/$($release.id)/assets?name=$([uri]::EscapeDataString($fileName))"
    Invoke-RestMethod -Method Post -Uri $uploadUri -Headers $headers `
        -ContentType "application/octet-stream" -InFile $assetPath -TimeoutSec 3600 | Out-Null
    Write-Ok "$fileName загружен за $([int]$sw.Elapsed.TotalSeconds) с"
}

Write-Step "Проверка"
$final = Invoke-RestMethod -Uri "https://api.github.com/repos/$owner/$repo/releases/tags/$Tag" `
    -Headers $headers -TimeoutSec 180
Write-Host "Релиз: $($final.html_url)"
Write-Host "Статус: draft=$($final.draft), prerelease=$($final.prerelease), файлов=$($final.assets.Count)"
foreach ($asset in $final.assets) {
    Write-Host ("  {0} — {1} Б" -f $asset.name, $asset.size)
    Write-Host ("    {0}" -f $asset.browser_download_url)
}

$expected = $assets.Count
if ($final.assets.Count -lt $expected) {
    throw "В релизе $($final.assets.Count) файл(ов) из $expected — проверьте вывод выше."
}
Write-Ok "Релиз $Tag готов к скачиванию."
