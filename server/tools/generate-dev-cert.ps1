# Generates a self-signed certificate for local HTTPS API testing.
$rootDir = Split-Path -Parent $PSScriptRoot
$certDir = Join-Path $rootDir "certs"
New-Item -ItemType Directory -Force -Path $certDir | Out-Null

openssl req `
  -x509 `
  -nodes `
  -days 365 `
  -newkey rsa:2048 `
  -keyout (Join-Path $certDir "server.key") `
  -out (Join-Path $certDir "server.crt") `
  -subj "/CN=127.0.0.1"

Write-Host "Generated development certificate in $certDir"
