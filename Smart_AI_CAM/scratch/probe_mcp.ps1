# probe_mcp.ps1
$url = "http://127.0.0.1:27182/mcp"
Write-Output "Probing MCP at $url..."

try {
    $client = New-Object System.Net.Http.HttpClient
    $client.Timeout = [System.TimeSpan]::FromSeconds(5)
    
    # Send GET request
    $responseTask = $client.GetAsync($url)
    if (-not $responseTask.Wait(5000)) {
        Write-Output "Error: Request timed out after 5 seconds."
        exit 1
    }
    
    $response = $responseTask.Result
    Write-Output "Status Code: $($response.StatusCode) ($([int]$response.StatusCode))"
    Write-Output "Headers:"
    foreach ($header in $response.Headers) {
        Write-Output "  $($header.Key): $($header.Value)"
    }
    foreach ($header in $response.Content.Headers) {
        Write-Output "  $($header.Key): $($header.Value)"
    }
    
    # Read first 1024 characters of content
    $contentTask = $response.Content.ReadAsStringAsync()
    if ($contentTask.Wait(3000)) {
        $content = $contentTask.Result
        Write-Output "`nContent (First 1024 chars):"
        if ($content.Length -gt 1024) {
            Write-Output $content.Substring(0, 1024)
        } else {
            Write-Output $content
        }
    } else {
        Write-Output "Error: Reading content timed out."
    }
} catch {
    Write-Output "Exception occurred: $_"
} finally {
    if ($client) { $client.Dispose() }
}
