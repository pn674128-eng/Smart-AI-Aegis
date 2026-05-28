# -*- coding: utf-8 -*-
"""
Test Ollama Auto-Start Wakeup and Shortcut Resolution logic.
"""
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Smart_AI.reasoning.reference_paths import OLLAMA_LNK, resolve_ollama_path, resolve_shortcut_target
from Smart_AI.reasoning.ai_decision_engine import OllamaDecisionConnector

def main():
    print("=" * 60)
    print("Ollama Shortcut & Auto-Start Diagnostic")
    print("=" * 60)

    # 1. Test Shortcut Resolution
    print(f"Ollama Shortcut Lnk: {OLLAMA_LNK}")
    print(f"Lnk exists? {os.path.exists(OLLAMA_LNK)}")
    
    target = resolve_shortcut_target(OLLAMA_LNK)
    print(f"Shortcut target: {target}")
    
    resolved_exe = resolve_ollama_path()
    print(f"Resolved EXE path: {resolved_exe}")
    if resolved_exe:
        print(f"EXE exists on disk? {os.path.exists(resolved_exe)}")
    else:
        print("EXE path could not be resolved.")
        
    print("-" * 60)

    # 2. Test Connection Status
    connector = OllamaDecisionConnector(default_model="qwen2.5-coder:7b")
    status = connector.is_running()
    print(f"Is Ollama running right now? {status}")
    
    if status:
        print("\n[NOTE] Ollama is already running. If you want to test the self-healing")
        print("wakeup logic, please close the Ollama app (from the system tray) and re-run this script.")
    else:
        print("\n[NOTE] Ollama is NOT running. Attempting self-healing wakeup via ask_ollama...")
        
    # 3. Trigger ask_ollama (this will invoke resolve_ollama_path() and subprocess if not running)
    print("\nCalling connector.ask_ollama with simple prompt...")
    t0 = time.time()
    res = connector.ask_ollama("Hello, reply in 5 words.", require_json=False)
    dt = time.time() - t0
    
    print("\nResponse:")
    print(res)
    print(f"Time taken: {dt:.2f} seconds")
    
    # Final check of status
    print(f"\nFinal Ollama status: {connector.is_running()}")

if __name__ == "__main__":
    main()
