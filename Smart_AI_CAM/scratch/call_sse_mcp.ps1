# call_sse_mcp.ps1
$url = "http://127.0.0.1:27182/mcp"
$outFile = "C:\Users\y00079\.gemini\antigravity-ide\scratch\scan_output.json"

Write-Output "Connecting to SSE MCP Server at $url..."

# Clear old file
if (Test-Path $outFile) { Remove-Item $outFile }

try {
    $httpClient = New-Object System.Net.Http.HttpClient
    $httpClient.Timeout = [System.TimeSpan]::FromSeconds(30)
    
    # Send GET request to establish SSE session
    $request = New-Object System.Net.Http.HttpRequestMessage([System.Net.Http.HttpMethod]::Get, $url)
    $request.Headers.Accept.Add((New-Object System.Net.Http.Headers.MediaTypeWithQualityHeaderValue("text/event-stream")))
    
    $responseTask = $httpClient.SendAsync($request, [System.Net.Http.HttpCompletionOption]::ResponseHeadersRead)
    if (-not $responseTask.Wait(5000)) {
        Write-Output "Error: GET /mcp connection timed out."
        exit 1
    }
    
    $response = $responseTask.Result
    Write-Output "SSE Connected! Status: $($response.StatusCode)"
    
    $stream = $response.Content.ReadAsStreamAsync().Result
    $reader = New-Object System.IO.StreamReader($stream)
    
    $postUrl = $null
    
    # Read SSE events until we get the endpoint
    Write-Output "Reading SSE stream for endpoint..."
    while ($null -ne ($line = $reader.ReadLine())) {
        # Standard SSE event lines
        if ($line.StartsWith("event: endpoint")) {
            # The next line should be data: ...
            $dataLine = $reader.ReadLine()
            if ($dataLine.StartsWith("data: ")) {
                $endpointStr = $dataLine.Substring(6).Trim()
                # Resolve relative URL
                if ($endpointStr.StartsWith("http")) {
                    $postUrl = $endpointStr
                } else {
                    $postUrl = "http://127.0.0.1:27182" + $endpointStr
                }
                Write-Output "Endpoint found: $postUrl"
                break
            }
        } elseif ($line.StartsWith("data: ")) {
            # Some implementations send only data line, or endpoint is in data
            $dataVal = $line.Substring(6).Trim()
            if ($dataVal.Contains("session_id")) {
                if ($dataVal.StartsWith("http")) {
                    $postUrl = $dataVal
                } else {
                    $postUrl = "http://127.0.0.1:27182" + $dataVal
                }
                Write-Output "Endpoint found from data: $postUrl"
                break
            }
        }
    }
    
    if (-not $postUrl) {
        Write-Output "Error: Could not extract message POST endpoint."
        exit 1
    }
    
    # 2. Now we have the post endpoint. Let's send a JSON-RPC request to call tool 'scan_machining_features'
    # Request payload
    $jsonPayload = @{
        jsonrpc = "2.0"
        id = "tool_call_1"
        method = "tools/call"
        params = @{
            name = "scan_machining_features"
            arguments = @{
                material = "AL6061"
            }
        }
    } | ConvertTo-Json -Depth 5
    
    Write-Output "Sending tool call scan_machining_features..."
    $content = New-Object System.Net.Http.StringContent($jsonPayload, [System.Text.Encoding]::UTF8, "application/json")
    
    $postResponseTask = $httpClient.PostAsync($postUrl, $content)
    if (-not $postResponseTask.Wait(10000)) {
        Write-Output "Error: POST request to call tool timed out."
        exit 1
    }
    
    $postResponse = $postResponseTask.Result
    Write-Output "POST Sent! Status: $($postResponse.StatusCode) ($([int]$postResponse.StatusCode))"
    
    # 3. Read response from SSE stream
    Write-Output "Reading response from SSE stream..."
    $resultJson = $null
    
    while ($null -ne ($line = $reader.ReadLine())) {
        if ($line.StartsWith("data: ")) {
            $dataStr = $line.Substring(6).Trim()
            Write-Output "Received data: $dataStr"
            
            # Save raw json to file
            $dataStr | Out-File -FilePath $outFile -Encoding utf8
            Write-Output "Result written successfully to $outFile"
            $resultJson = $dataStr
            break
        }
    }
    
    if (-not $resultJson) {
        Write-Output "Error: No response received from SSE stream."
    }
    
} catch {
    Write-Output "Exception occurred: $_"
} finally {
    if ($reader) { $reader.Close() }
    if ($httpClient) { $httpClient.Dispose() }
    Write-Output "Done."
}
