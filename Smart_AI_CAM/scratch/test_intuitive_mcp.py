import urllib.request, json

data = json.dumps({
    'action': 'eval_python',
    'params': {
        'code': '''
import adsk.core, adsk.fusion, adsk.cam
import sys, traceback
try:
    import Smart_AI.reasoning.intuitive_programming as ip
    # Check if we can trigger intuitive programming from here
    res = ip.run_intuitive_programming(adsk.core.Application.get(), None)
    result = "SUCCESS: " + str(res)
except Exception as e:
    result = "ERROR: " + str(e) + "\\n" + traceback.format_exc()
'''
    }
}).encode('utf-8')

req = urllib.request.Request('http://127.0.0.1:9877/mcp', data=data, headers={'Content-Type': 'application/json'})
try:
    res = urllib.request.urlopen(req)
    print("Response:", res.read().decode())
except Exception as e:
    print('Failed:', e)
