import sys
import json
import socket

def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        
    script = """
try:
    from smart_ai_cam_state.runtime_state import state as runtime_state
    import os
    
    m = runtime_state.allTopFaceRoughMap.get('AL6061', [])
    res = []
    for x in m:
        url = x.get('url')
        try:
            url_str = url.toString() if hasattr(url, 'toString') else str(url)
        except Exception as e:
            url_str = f"Error: {e}"
        res.append({"name": x.get('name'), "url": url_str})
    
    runtime_state.app.userInterface.messageBox(str(res))
    print(json.dumps(res, ensure_ascii=False))
except Exception as e:
    import traceback
    print(traceback.format_exc())
"""
    # Wait, we can't easily execute raw code in Fusion via MCP unless there's an endpoint.
    pass

if __name__ == '__main__':
    main()
