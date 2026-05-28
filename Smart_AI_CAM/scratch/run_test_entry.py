import urllib.request, urllib.parse, json, sys

data = json.dumps({
    'action': 'eval_python',
    'params': {
        'code': '''
import adsk.core, adsk.fusion, adsk.cam
try:
    app = adsk.core.Application.get()
    cam = adsk.cam.CAM.cast(app.activeProduct)
    if not cam:
        result = "No CAM product"
    else:
        setup = cam.setups.item(0)
        op = None
        for i in range(setup.allOperations.count):
            o = setup.allOperations.item(i)
            s = o.strategy.lower()
            if "contour" in s:
                op = o
                break
        if not op:
            result = "No 2D Contour found"
        else:
            param = op.parameters.itemByName('entryPositions')
            if not param:
                result = "No entryPositions param"
            else:
                pt = adsk.core.Point3D.create(0, 0, 0)
                col = adsk.core.ObjectCollection.create()
                col.add(pt)
                try:
                    param.value = col
                    result = "SUCCESS: Set entryPositions with Point3D!"
                except Exception as e:
                    result = "ERROR setting param: " + str(e)
except Exception as e:
    result = str(e)
'''
    }
}).encode('utf-8')

req = urllib.request.Request('http://127.0.0.1:9877/mcp', data=data, headers={'Content-Type': 'application/json'})
try:
    res = urllib.request.urlopen(req)
    print(res.read().decode())
except Exception as e:
    print('Failed:', e)
