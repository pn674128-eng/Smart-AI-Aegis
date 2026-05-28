import adsk.core
import traceback
import os

app = None
ui = None
palette = None

PALETTE_ID = "fusionApiReferencePalette"
PALETTE_NAME = "Fusion API 參考手冊"


def run(context):
    run_file("reference.html")


def run_file(filename):
    global app, ui, palette
    try:
        app = adsk.core.Application.get()
        ui = app.userInterface
        palettes = ui.palettes
        
        if not filename:
            filename = "reference.html"
            
        html_path = os.path.join(os.path.dirname(__file__), filename)
        html_url = "file:///" + html_path.replace(os.sep, "/")

        palette = palettes.itemById(PALETTE_ID)
        if palette:
            try:
                palette.deleteMe()
            except:
                pass

        palette = palettes.add(
            PALETTE_ID,
            PALETTE_NAME,
            html_url,
            True,
            True,
            True,
            900,
            740,
        )
        palette.dockingOption = adsk.core.PaletteDockingOptions.PaletteDockOptionsToVerticalOnly
        palette.dockingState = adsk.core.PaletteDockingStates.PaletteDockStateRight
        palette.isVisible = True
    except:
        if ui:
            ui.messageBox("Fusion API 參考插件啟動失敗:\n{}".format(traceback.format_exc()))


def stop(context):
    global app, ui, palette
    try:
        app = adsk.core.Application.get()
        ui = app.userInterface
        p = ui.palettes.itemById(PALETTE_ID)
        if p:
            p.deleteMe()
        palette = None
    except:
        if ui:
            ui.messageBox("Fusion API 參考插件停止失敗:\\n{}".format(traceback.format_exc()))
