import json
import socket
import sys

def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    action = "run_intuitive_one_click"
    params = {"material": "AL6061"}
    
    print(f"Attempting to connect to Fusion 360 MCP server at 127.0.0.1:9877...")
    print(f"Action: {action}, Params: {params}")

    try:
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.settimeout(60.0) # execution might take some time
        client.connect(("127.0.0.1", 9877))
        payload = {"action": action, "params": params}
        client.sendall((json.dumps(payload) + "\n").encode("utf-8"))
        
        buffer = ""
        while True:
            data = client.recv(65536)
            if not data:
                break
            buffer += data.decode("utf-8")
            if "\n" in buffer:
                break
                
        client.close()
        
        if buffer:
            result = json.loads(buffer.strip())
            print("\n=== Result ===")
            print(f"Success: {result.get('success')}")
            if not result.get("success"):
                print(f"Error: {result.get('error')}")
            
            data = result.get("data") or {}
            if "report_text" in data:
                print("\n--- Report ---")
                print(data["report_text"])
                
            print("\n--- Full Data Preview ---")
            print(json.dumps(data, ensure_ascii=False, indent=2)[:1000] + "...\n(truncated)" if len(json.dumps(data)) > 1000 else json.dumps(data, ensure_ascii=False, indent=2))
        else:
            print("No response from server.")
            
    except ConnectionRefusedError:
        print("\nError: Could not connect to the Fusion 360 MCP server.")
        print("Please ensure that Fusion 360 is open and the Smart_AI_CAM add-in is running.")
    except Exception as e:
        print(f"\nError: {e}")

if __name__ == "__main__":
    main()
