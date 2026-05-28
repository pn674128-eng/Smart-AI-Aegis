# dump_sse.ps1
$url = "http://127.0.0.1:27182/mcp"
$outFile = "C:\Users\y00079\.gemini\antigravity-ide\scratch\sse_dump.txt"

"Starting dump..." | Out-File -FilePath $outFile -Encoding utf8

try {
    $httpClient = New-Object System.Net.Http.HttpClient
    $httpClient.Timeout = [System.TimeSpan]::FromSeconds(10)
    
    $request = New-Object System.Net.Http.HttpRequestMessage([System.Net.Http.HttpMethod]::Get, $url)
    $request.Headers.Accept.Add((New-Object System.Net.Http.Headers.MediaTypeWithQualityHeaderValue("text/event-stream")))
    
    $responseTask = $httpClient.SendAsync($request, [System.Net.Http.HttpCompletionOption]::ResponseHeadersRead)
    if (-not $responseTask.Wait(5000)) {
        "Error: GET connection timed out." | Out-File -FilePath $outFile -Append -Encoding utf8
        exit 1
    }
    
    $response = $responseTask.Result
    "Connected! Status: $($response.StatusCode)" | Out-File -FilePath $outFile -Append -Encoding utf8
    
    $stream = $response.Content.ReadAsStreamAsync().Result
    $reader = New-Object System.IO.StreamReader($stream)
    
    "Reading lines..." | Out-File -FilePath $outFile -Append -Encoding utf8
    
    # Read max 50 lines or until stream end
    $lineCount = 0
    while ($lineCount -lt 50) {
        $line = $reader.ReadLine()
        if ($null -eq $line) {
            "Stream closed." | Out-File -FilePath $outFile -Append -Encoding utf8
            break
        }
        "Line $lineCount: $line" | Out-File -FilePath $outFile -Append -Encoding utf8
        $lineCount++
    }
    
    "Dump completed." | Out-File -FilePath $outFile -Append -Encoding utf8
} catch {
    "Exception: $_" | Out-File -FilePath $outFile -Append -Encoding utf8
} finally {
    if ($reader) { $reader.Close() }
    if ($httpClient) { $httpClient.Dispose() }
}
