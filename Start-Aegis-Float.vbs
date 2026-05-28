' Smart AI Aegis float launcher (no .pyw association needed)
Option Explicit

Dim sh, fso, toolDir, appPy, pyExe, cmd, base, subf, pyBase, pyDir, pywCandidate, pyCandidate

Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
toolDir = fso.GetParentFolderName(WScript.ScriptFullName)
appPy = toolDir & "\aegis_float\aegis_float_app.py"

If Not fso.FileExists(appPy) Then
    MsgBox "App not found:" & vbCrLf & appPy, 16, "Smart AI Aegis"
    WScript.Quit 2
End If

pyExe = ""

' 1) Prefer user-installed Python (has tkinter)
pyBase = sh.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Programs\Python\"
If fso.FolderExists(pyBase) Then
    For Each pyDir In fso.GetFolder(pyBase).SubFolders
        pywCandidate = pyDir.Path & "\pythonw.exe"
        pyCandidate = pyDir.Path & "\python.exe"
        If fso.FileExists(pywCandidate) Then
            pyExe = pywCandidate
            Exit For
        End If
        If fso.FileExists(pyCandidate) Then
            pyExe = pyCandidate
        End If
    Next
End If

' 2) Fallback to Fusion embedded Python
base = sh.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Autodesk\webdeploy\production\"
If fso.FolderExists(base) Then
    For Each subf In fso.GetFolder(base).SubFolders
        If pyExe <> "" Then Exit For
        If fso.FileExists(subf.Path & "\Python\pythonw.exe") Then
            pyExe = subf.Path & "\Python\pythonw.exe"
            Exit For
        End If
        If fso.FileExists(subf.Path & "\Python\python.exe") Then
            pyExe = subf.Path & "\Python\python.exe"
        End If
    Next
End If

If pyExe = "" Then
    If fso.FileExists("C:\Windows\py.exe") Then
        cmd = "cmd /c py -3 " & Chr(34) & appPy & Chr(34)
    Else
        cmd = "cmd /c python " & Chr(34) & appPy & Chr(34)
    End If
Else
    cmd = Chr(34) & pyExe & Chr(34) & " " & Chr(34) & appPy & Chr(34)
End If

sh.Environment("PROCESS")("AEGIS_MODEL") = "smart-ai-aegis"
sh.Run cmd, 0, False
