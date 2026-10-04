$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$envPath = Join-Path $projectRoot ".env"
$secureKey = Read-Host "Enter your NEW Gemini API key (input is hidden)" -AsSecureString
$pointer = [IntPtr]::Zero
$apiKey = $null

try {
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)
    $apiKey = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    if ([string]::IsNullOrWhiteSpace($apiKey)) {
        throw "The API key cannot be empty."
    }

    $settings = [ordered]@{
        LLM_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai"
        LLM_API_KEY  = $apiKey
        LLM_MODEL    = "gemini-3.8-flash"
    }

    $content = if (Test-Path $envPath) {
        [System.IO.File]::ReadAllText($envPath)
    } else {
        ""
    }
    $content = [regex]::Replace($content, "(\r?\n)+$", "")
    $lines = [System.Collections.Generic.List[string]]::new()
    $written = @{}

    foreach ($existingLine in ($content -split "\r?\n")) {
        $matched = $false
        foreach ($name in $settings.Keys) {
            if ($existingLine -match "^\s*$([regex]::Escape($name))=") {
                $lines.Add("$name=$($settings[$name])")
                $written[$name] = $true
                $matched = $true
                break
            }
        }
        if (-not $matched -and ($existingLine.Length -gt 0 -or $content.Length -gt 0)) {
            $lines.Add($existingLine)
        }
    }

    foreach ($name in $settings.Keys) {
        if (-not $written.ContainsKey($name)) {
            $lines.Add("$name=$($settings[$name])")
        }
    }

    [System.IO.File]::WriteAllText(
        $envPath,
        ($lines -join "`r`n") + "`r`n",
        [System.Text.UTF8Encoding]::new($false)
    )
    Write-Host "Gemini settings saved to the local .env file. Restart Streamlit to use them."
} finally {
    if ($pointer -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
    }
    if ($secureKey) {
        $secureKey.Dispose()
    }
    Remove-Variable apiKey -ErrorAction SilentlyContinue
}
