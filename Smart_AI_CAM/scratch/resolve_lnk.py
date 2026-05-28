# -*- coding: utf-8 -*-
import os
import sys

def resolve_shortcut(lnk_path):
    print("Resolving:", lnk_path)
    if not os.path.isfile(lnk_path):
        print("Error: File not found")
        return None
    try:
        import win32com.client
        shell = win32com.client.Dispatch("WScript.Shell")
        shortcut = shell.CreateShortcut(os.path.abspath(lnk_path))
        print("TargetPath:", shortcut.TargetPath)
        print("Arguments:", shortcut.Arguments)
        print("WorkingDirectory:", shortcut.WorkingDirectory)
        return shortcut.TargetPath
    except Exception as e:
        print("COM Error:", e)
    
    # Binary fallback if win32com fails
    try:
        with open(lnk_path, "rb") as f:
            data = f.read()
        # Look for Unicode/ASCII path patterns in .lnk binary
        # (This is a lightweight fallback)
        import re
        matches = re.findall(rb'[A-Za-z]:\\[^\x00-\x1f\x7f-\xff]+', data)
        if matches:
            print("Binary search matches:")
            for m in matches:
                path = m.decode('ascii', errors='ignore')
                if path.lower().endswith('.exe'):
                    print("Found EXE:", path)
                    return path
    except Exception as e:
        print("Binary fallback error:", e)
    return None

if __name__ == "__main__":
    lnk = r"C:\Users\y00079\Desktop\ollama.lnk"
    resolve_shortcut(lnk)
