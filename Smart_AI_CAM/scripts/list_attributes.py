import socket
import json
import sys

# Force standard output to UTF-8
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

HOST = '127.0.0.1'
PORT = 9877

def send_request(action, params=None):
    if params is None:
        params = {}
    print(f"\n[Test] Sending action: {action} with params: {params}...")
    try:
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.settimeout(10.0)
        client.connect((HOST, PORT))
        
        payload = {
            "action": action,
            "params": params
        }
        
        client.sendall((json.dumps(payload) + "\n").encode('utf-8'))
        
        # Read the response
        buffer = ""
        while True:
            data = client.recv(8192)
            if not data:
                break
            buffer += data.decode('utf-8')
            if "\n" in buffer:
                break
        
        client.close()
        
        if buffer:
            response = json.loads(buffer.strip())
            print(f"[Test] Success! Response:")
            print(json.dumps(response, indent=2, ensure_ascii=False))
            return response
        else:
            print("[Test] Connected, but no response data returned.")
            return None
    except Exception as e:
        print(f"[Test] Failed: {str(e)}")
        return None

if __name__ == "__main__":
    code = """
import adsk.core
app = adsk.core.Application.get()
s = app.scripts.item(0)
global result
result = ", ".join(dir(s))
"""
    send_request("execute_python_code", {"code": code})
