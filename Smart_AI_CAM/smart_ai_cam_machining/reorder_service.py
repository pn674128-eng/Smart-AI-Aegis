# -*- coding: utf-8 -*-
"""
reorder_service.py
Encapsulates operation tree reordering logic based on tool ordering rules.
"""

from __future__ import annotations
import json
import re
import adsk.core
import adsk.cam

def getToolOrder(op) -> tuple[int, float]:
    if not op.tool:
        return (99, 99)
    toolType = ''
    try:
        j = json.loads(op.tool.toJson())
        toolType = j.get('type', '')
    except:
        pass
    try:
        dia = op.tool.parameters.itemByName('tool_diameter').value.value
    except:
        dia = 0
    opName = str(op.name or '')
    opUpper = opName.upper()

    # 判斷粗精修
    is_rough = '粗' in opName
    is_finish = '精' in opName

    # 1) [優先級 10] 頂面粗加工 (Face Roughing)
    if '頂面' in opName and is_rough:
        return (10, -dia)

    # 2) [優先級 20] 外輪廓粗加工 (Profile Roughing)
    if ('外' in opName or '輪廓' in opName) and is_rough:
        return (20, -dia)

    # 3) [優先級 30] 中心鑽/定位鑽 (Spot Drill)
    if toolType in ['center drill', 'spot drill'] or '中心' in opName:
        return (30, -dia)

    # 4) [優先級 40] 鑽孔 (Drilling)
    if toolType == 'drill':
        return (40, dia) # 鑽頭一般從小排到大

    # 5) [優先級 50] 內部特徵粗銑削 (Internal Mill Roughing)
    if toolType == 'flat end mill' and not is_finish and not ('外' in opName) and not ('頂面' in opName):
        return (50, -dia)

    # 6) [優先級 60] 絞孔 (Reaming)
    if toolType == 'reamer' or '絞' in opName:
        return (60, dia)

    # 7) [優先級 70] 倒角加工 (Chamfering)
    if toolType == 'chamfer mill' or '倒角' in opName:
        return (70, -dia)

    # 8) [優先級 80] 精加工 (All Finishing)
    if is_finish:
        # 精修內部特徵 (80) -> 外輪廓精修 (85) -> 頂面精修 (89)
        if '頂面' in opName: return (89, -dia)
        if '外' in opName or '輪廓' in opName: return (85, -dia)
        return (80, -dia)

    # 9) 其他未分類
    return (90, dia)

def reorder_setup_operations(camSetup) -> int:
    """對 Setup 下所有工序進行排序並調整工序樹，回傳排序的工序個數。"""
    if not camSetup:
        return 0
    allOps = camSetup.allOperations
    if allOps.count <= 1:
        return allOps.count
    opList = [allOps.item(i) for i in range(allOps.count)]
    opList.sort(key=getToolOrder)
    for i in range(1, len(opList)):
        try:
            opList[i].moveAfter(opList[i-1])
        except:
            pass
    return len(opList)
