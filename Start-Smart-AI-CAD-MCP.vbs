CreateObject("WScript.Shell").Run "pythonw.exe """ & CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName) & "\Smart AI CAD\mcp\cad_mcp_server.py""", 0, False
