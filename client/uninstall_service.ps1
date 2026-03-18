param(
    [string]$ExecutablePath = ".\Client.exe"
)

# Uninstall uses the same executable switch so the service metadata does not
# need to be duplicated in PowerShell.
if (-not (Test-Path $ExecutablePath)) {
    throw "Client executable not found: $ExecutablePath"
}

& $ExecutablePath --uninstall-service
if ($LASTEXITCODE -ne 0) {
    throw "Failed to uninstall Windows service"
}

Write-Host "Service removed successfully."
