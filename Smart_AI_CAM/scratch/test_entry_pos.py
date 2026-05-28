import adsk.core, adsk.fusion, adsk.cam
import traceback

def run(context):
    try:
        app = adsk.core.Application.get()
        cam = adsk.cam.CAM.cast(app.activeProduct)
        if not cam:
            print('No CAM product')
            return
            
        setup = cam.setups.item(0)
        op = None
        for i in range(setup.allOperations.count):
            o = setup.allOperations.item(i)
            if '2D Contour' in o.strategy or 'contour2d' in o.strategy:
                op = o
                break
                
        if not op:
            print('No 2D Contour found')
            return
            
        param = op.parameters.itemByName('entryPositions')
        if not param:
            print('No entryPositions param')
            return
            
        pt = adsk.core.Point3D.create(0, 0, 0)
        col = adsk.core.ObjectCollection.create()
        col.add(pt)
        
        try:
            param.value = col
            print('SUCCESS: Successfully set entryPositions with Point3D!')
        except Exception as e:
            print('ERROR: Failed to set entryPositions with Point3D: ' + str(e))
            
    except Exception as e:
        print('Exception: ' + str(e))

if __name__ == '__main__':
    run(None)
