# probe_sse_file.ps1
$ip = "127.0.0.1"
$port = 27182
$path = "/mcp"
$outFile = "C:\Users\y00079\.gemini\antigravity-ide\scratch\probe_result.txt"

# Clear old results
"Starting probe..." | Out-File -FilePath $outFile -Encoding utf8

try {
    "Connecting to SSE MCP Server at $ip:$port..." | Out-File -FilePath $outFile -Append -Encoding utf8
    
    $client = New-Object System.Net.Sockets.TcpClient
    $connect = $client.BeginConnect($ip, $port, $null, $null)
    $success = $connect.AsyncWaitHandle.WaitOne(3000, $false)
    
    if (-not $success) {
        "Error: Connection timed out to $ip:$port" | Out-File -FilePath $outFile -Append -Encoding utf8
        exit 1
    }
    
    $client.EndConnect($connect)
    "Connected successfully! Sending HTTP GET request..." | Out-File -FilePath $outFile -Append -Encoding utf8
    
    $stream = $client.GetStream()
    $writer = New-Object System.IO.StreamWriter($stream)
    $reader = New-Object System.IO.StreamReader($stream)
    
    # Send HTTP GET for SSE
    $writer.WriteLine("GET $path HTTP/1.1")
    $writer.WriteLine("Host: $ip:$port")
    $writer.WriteLine("Accept: text/event-stream")
    $writer.WriteLine("Connection: keep-alive")
    $writer.WriteLine("")
    $writer.Flush()
    
    "Request sent. Reading response headers..." | Out-File -FilePath $outFile -Append -Encoding utf8
    
    # Read headers
    $headers = @()
    while ($true) {
        $line = $reader.ReadLine()
        if ($null -eq $line -or $line -eq "") {
            break
        }
        "Header: $line" | Out-File -FilePath $outFile -Append -Encoding utf8
    }
    
    "`nReading first few SSE events (max 5 lines)..." | Out-File -FilePath $outFile -Append -Encoding utf8
    for ($i = 0; $i -lt 5; $i++) {
        $line = $reader.ReadLine()
        if ($null -eq $line) {
            "Stream closed by server." | Out-File -FilePath $outFile -Append -Encoding utf8
            break
        }
        "SSE: $line" | Out-File -FilePath $outFile -Append -Encoding utf8
    }
    
} catch {
    "Exception: $_" | Out-File -FilePath $outFile -Append -Encoding utf8
} finally {
    if ($client) {
        $client.Close()
        "Socket connection closed." | Out-File -FilePath $outFile -Append -Encoding utf8
    }
}
