param(
  [string]$Email = "alvaroscareli@gmail.com",
  [string]$EnvPath = "$(Resolve-Path (Join-Path $PSScriptRoot '..\.env'))"
)

function Set-Or-ReplaceEnvLine {
  param(
    [string]$Key,
    [string]$Value,
    [string[]]$Lines
  )

  $pattern = "^\s*" + [regex]::Escape($Key) + "\s*="
  $found = $false
  $out = @()

  foreach ($line in $Lines) {
    if ($line -match $pattern) {
      $out += ("$Key=$Value")
      $found = $true
    } else {
      $out += $line
    }
  }

  if (-not $found) {
    $out += ("$Key=$Value")
  }

  return ,$out
}

Write-Host "Configurar SMTP no .env: $EnvPath" -ForegroundColor Cyan
Write-Host "Email padrão: $Email" -ForegroundColor Cyan
Write-Host "" 
Write-Host "Cole o App Password do Gmail quando solicitado (não aparece na tela)." -ForegroundColor Yellow

$secure = Read-Host -AsSecureString "SMTP App Password"
$ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try {
  $plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
} finally {
  [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
}

# remove spaces just in case user pastes with spaces
$plain = ($plain -replace "\s+", "").Trim()
if (-not $plain) {
  throw "Senha vazia. Abortando."
}

$lines = @()
if (Test-Path $EnvPath) {
  $lines = Get-Content -LiteralPath $EnvPath -Encoding UTF8
}

$lines = Set-Or-ReplaceEnvLine -Key "SMTP_HOST" -Value "smtp.gmail.com" -Lines $lines
$lines = Set-Or-ReplaceEnvLine -Key "SMTP_PORT" -Value "587" -Lines $lines
$lines = Set-Or-ReplaceEnvLine -Key "SMTP_TLS" -Value "1" -Lines $lines
$lines = Set-Or-ReplaceEnvLine -Key "SMTP_SSL" -Value "0" -Lines $lines
$lines = Set-Or-ReplaceEnvLine -Key "SMTP_USER" -Value $Email -Lines $lines
$lines = Set-Or-ReplaceEnvLine -Key "SMTP_FROM" -Value $Email -Lines $lines
$lines = Set-Or-ReplaceEnvLine -Key "SMTP_PASSWORD" -Value $plain -Lines $lines

Set-Content -LiteralPath $EnvPath -Value $lines -Encoding UTF8
Write-Host "OK: .env atualizado (SMTP_*)." -ForegroundColor Green
Write-Host "Agora rode: python scripts/test_smtp_send.py" -ForegroundColor Cyan
