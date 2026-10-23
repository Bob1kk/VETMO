$token = $env:SUPABASE_TOKEN

$sql = Get-Content 'supabase\migrations\20261020_001_init.sql' -Raw -Encoding UTF8
$seed = Get-Content 'supabase\seed\20261020_002_seed_heroes.sql' -Raw -Encoding UTF8

# Replace non-ASCII chars that break JSON
$replacements = @{
    '—' = '-';
    '–' = '-';
    '“' = '"';
    '”' = '"';
    '’' = "'";
    '‘' = "'";
    '…' = '...';
}

foreach ($pair in $replacements.GetEnumerator()) {
    $sql = $sql -replace $pair.Key, $pair.Value
    $seed = $seed -replace $pair.Key, $pair.Value
}

$combined = $sql + "`n`n-- Seed`n" + $seed

$body = @{ query = $combined } | ConvertTo-Json -Compress -Depth 20

try {
    $response = Invoke-RestMethod -Uri "https://api.supabase.com/v1/projects/qtqntybxwwhggqimkxpi/database/query" -Method POST -Headers @{ Authorization = "Bearer $token" } -Body $body -ContentType "application/json"
    Write-Host "SUCCESS!"
    $response | ConvertTo-Json -Depth 5
} catch {
    Write-Host "Error: $($_.Exception.Message)"
    if ($_.ErrorDetails) { Write-Host "Details: $($_.ErrorDetails)" }
}
