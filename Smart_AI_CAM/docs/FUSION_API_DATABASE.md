<!-- [SYSTEM: READ-ONLY] -->
# 🛠️ Autodesk Fusion 360 CAM/Design Official API Reference Database
> [!IMPORTANT]
> **本資料庫為官方 API 與最佳實踐的「唯讀/禁止變更」核心資料庫**。用於提供 AI 助理最精確的程式碼參考。請勿手動修改此檔案內容。

## 📌 快速索引目錄
1. [Fusion API 參考手冊](#fusion-api-參考手冊)
2. [CAM Methods 全表](#cam-methods-全表)
3. [設計 API (BRepBody/Face/Sketch)](#設計-api-brepbodyfacesketch)
4. [CAM Parameter API (官方完整)](#cam-parameter-api-官方完整)
5. [Setup & Operation API (官方完整)](#setup--operation-api-官方完整)
6. [CAM Core API (CAM/Setups/Operations/ToolLib/PostProcess)](#cam-core-api-camsetupsoperationstoollibpostprocess)
7. [Machine / CAMTemplate / NCProgram API](#machine--camtemplate--ncprogram-api)
8. [製造 API 功能總覽](#製造-api-功能總覽)
9. [特徵辨識 API (孔/口袋/PocketRecognitionSelection)](#特徵辨識-api-孔口袋pocketrecognitionselection)
10. [幾何選取 API (CurveSelections/Chain/Silhouette/Sketch)](#幾何選取-api-curveselectionschainsilhouettesketch)
11. [工具 / ToolPreset / SetupGroup API](#工具--toolpreset--setupgroup-api)
12. [Additive / Export / PrintSetting API](#additive--export--printsetting-api)

---


<a name="fusion-api-參考手冊"></a>
## 📚 Fusion API 參考手冊
Fusion API 參考手冊
# 將幾何特徵帶入 CAM 工序 — 完整參考清單

> [!NOTE]
> 用途：作為孔/槽識別與插件升級的長期基礎規範。

> [!NOTE]
> [打開：附錄 CAM Methods 全表](reference_cam_methods.html) ｜ [打開：設計 API（BRepBody/Face/Sketch）](reference_design_api.html) ｜ [打開： CAM Parameter API（官方完整）](reference_cam_api.html) ｜ [打開：Setup & Operation API（官方完整）](reference_setup_operation.html) ｜ [打開：CAM Core API（CAM/Setups/Operations/ToolLib/PostProcess）](reference_cam_core.html) ｜ [打開：Machine / CAMTemplate / NCProgram API](reference_machine_template.html) ｜ [打開：製造 API 功能總覽（資料夾/陣列/ManufacturingModel/ToolLibraries）](reference_manufacturing_overview.html) ｜ [打開：特徵辨識 API（孔/嘴袋/PocketRecognitionSelection）](reference_recognition.html) ｜ [打開：幾何選取 API（CurveSelections/Chain/FaceContour/Silhouette/Sketch/MachiningTime）](reference_geometry_selection.html) ｜ [打開：工具 / ToolPreset / SetupGroup API](reference_tool_preset.html) ｜ [打開：Additive / Export / PrintSetting API](reference_additive_export.html) 

## 先備：dump_params（必備工具）

```python
def dump_params(op):
 params = op.parameters
 for i in range(params.count):
 p = params.item(i)
 print(f"[{i:03d}] {p.name:<42s} {type(p.value).__name__:<36s} expr={p.expression}")```

## 方式一：holeFaces 直接帶入孔面

```python
holeMode = params.itemByName('holeMode')
holeFaces = params.itemByName('holeFaces')
vec = holeFaces.value.value
vec.push_back(faces[0])
holeFaces.value.value = vec
holeMode.expression = "'selection-faces'"```

## 方式二：holePoints 用點座標帶入

```python
holePoints = params.itemByName('holePoints')
vec = holePoints.value.value
vec.push_back(some_vertex_or_point)
holePoints.value.value = vec
holeMode.expression = "'selection-points'"```

## 方式三：直徑範圍自動比對

```python
holeMode.expression = "'diameter'"
params.itemByName('holeDiameterMinimum').expression = '5mm'
params.itemByName('holeDiameterMaximum').expression = '10mm'```

## 方式四：CadContours2dParameterValue（輪廓幾何）

```python
geo_param = params.itemByName('geometries')
cad_val = adsk.cam.CadContours2dParameterValue.cast(geo_param.value)
curves = cad_val.getCurveSelections()
new_sel = adsk.cam.CadCurve.createFaceContour(face)
curves.add(new_sel)
cad_val.applyCurveSelections(curves)```

## 方式五：Hole Signature XML（模板自動比對）

```python
template = adsk.cam.CAMTemplate.createFromFile(path)
template.setHoleSignatureXML(xml_str)
input_obj = adsk.cam.CreateFromCAMTemplateInput.create()
input_obj.camTemplate = template
setup.createFromCAMTemplate2(input_obj)```

## 方式六：expression 直接寫（Choice / Boolean / Float）

```python
params.itemByName('cycleType').expression = "'drilling'"
params.itemByName('holeMode').expression = "'selection-faces'"
params.itemByName('selectSameDiameter').expression = 'true'
params.itemByName('topHeight_mode').expression = "'from hole top'"```

## 選擇指引

- 有 holeMode：孔面→方式一；點→方式二；直徑批次→方式三。
- 有 geometries：輪廓/挖槽/面輪廓→方式四。
- 模板整模型匹配→方式五（Hole Signature XML）。
- 模式/開關/數值→方式六（expression）。

> [!IMPORTANT]
> 本頁作為未來識別策略與插件升級的基礎參考，先 dump_params 再落地。

## 方式七：topHeight_mode / bottomHeight_mode（高度定義）

```python
params.itemByName('topHeight_mode').expression = "'from hole top'"
params.itemByName('topHeight_offset').expression = '0mm'
params.itemByName('bottomHeight_mode').expression = "'from hole bottom'"
params.itemByName('bottomHeight_offset').expression = '0mm'
# mode: 'model top' | 'from hole top' | 'from hole bottom' | 'from setup top' | 'from stock top'```

## 方式八：stockOffsets（餘量設定）

```python
params.itemByName('stockOffsets').expression = '0mm'
params.itemByName('stockToLeaveFloor').expression = '0mm'
params.itemByName('stockToLeaveSide').expression = '0mm'
params.itemByName('roughingStockToLeave').expression = '0.3mm'```

## 方式九：setup.models body 映射（Occurrence -> native）

```python
root = design.rootComponent
for i in range(setup.models.count):
 b = adsk.fusion.BRepBody.cast(setup.models.item(i))
 bname = b.name or ''
 native = None
 for ri in range(root.bRepBodies.count):
 rb = root.bRepBodies.item(ri)
 if (rb.name or '') == bname:
 native = rb; break
 target = native if native else b
 # target 可安全傳入 sketch.project(edge)```



---


<a name="cam-methods-全表"></a>
## 📚 CAM Methods 全表
CAM Methods Appendix
# 附錄：CAM Methods 全表

> [!NOTE]
> 用於快速查表、複製 expression 與比對模板策略。

## holeMode 全表
````````
| 值 | 說明 |
| --- | --- |
| | |
| 'selection-faces' | 直接指定孔面 |
| 'selection-points' | 以點座標指定 |
| 'diameter' | 按直徑範圍自動比對 |
| 'unmachined' | 未加工孔 |

## geometryType 全表
``````
| 值 | 說明 |
| --- | --- |
| | |
| 'chains' | 曲線鏈 |
| 'pockets' | 挖槽區域 |
| 'face_contours' | 面輪廓 |

## cycleType 常用全表
````````````````
| 值 | 說明 |
| --- | --- |
| | |
| 'drilling' | 標準鑽孔 |
| 'chip-breaking' | 斷屑 |
| 'deep-drilling' | 深孔 |
| 'break-through-drilling' | 穿透 |
| 'tapping' | 攻牙 |
| 'bore-milling' | 搪孔/鉸孔相關 |
| 'circular-pocket-milling' | 圓弧挖槽 |
| 'thread-milling' | 螺紋銑 |

## 示例：選孔面 + 設 cycle

```python
holeMode = params.itemByName('holeMode')
holeFaces = params.itemByName('holeFaces')
cycleType = params.itemByName('cycleType')

vec = holeFaces.value.value
vec.push_back(face)
holeFaces.value.value = vec

holeMode.expression = "'selection-faces'"
cycleType.expression = "'drilling'"```

## 示例：2D 輪廓 geometries

```python
geo_param = params.itemByName('geometries')
cad_val = adsk.cam.CadContours2dParameterValue.cast(geo_param.value)
curves = cad_val.getCurveSelections()
curves.add(adsk.cam.CadCurve.createFaceContour(face))
cad_val.applyCurveSelections(curves)
params.itemByName('geometryType').expression = "'face_contours'"```

## topHeight_mode / bottomHeight_mode 全表
````````````
| 值 | 說明 |
| --- | --- |
| | |
| 'model top' | 模型最高點 |
| 'from hole top' | 從孔頂面偏移 |
| 'from hole bottom' | 從孔底面偏移 |
| 'from setup top' | 從 Setup 頂偏移 |
| 'from stock top' | 從毛料頂偏移 |
| 'from selected contour' | 從選取輪廓偏移 |

## selectSameDiameter / 直徑深度範圍參數
````````````
| 參數名 | 型態 | 說明 |
| --- | --- | --- |
| | | |
| selectSameDiameter | Boolean | 自動選同直徑孔 |
| selectSameDepth | Boolean | 自動選同深度孔 |
| holeDiameterMinimum | Float (mm) | 直徑下限 |
| holeDiameterMaximum | Float (mm) | 直徑上限 |
| holeDepthMinimum | Float (mm) | 深度下限 |
| holeDepthMaximum | Float (mm) | 深度上限 |

## stockOffsets 相關參數
``````````
| 參數名 | 說明 |
| --- | --- |
| | |
| stockOffsets | 整體餘量 |
| stockToLeaveSide | 側面精銑餘量 |
| stockToLeaveFloor | 底面精銑餘量 |
| roughingStockToLeave | 粗銑保留量 |
| finishingStockToLeave | 精銑保留量 |

## 示例：孔直徑批次自動選取

```python
params.itemByName('holeMode').expression = "'diameter'"
params.itemByName('holeDiameterMinimum').expression = '4.9mm'
params.itemByName('holeDiameterMaximum').expression = '5.1mm'
params.itemByName('selectSameDiameter').expression = 'true'
params.itemByName('cycleType').expression = "'drilling'"```

## 示例：topHeight + bottomHeight 精確高度

```python
params.itemByName('topHeight_mode').expression = "'from hole top'"
params.itemByName('topHeight_offset').expression = '2mm'
params.itemByName('bottomHeight_mode').expression = "'from hole bottom'"
params.itemByName('bottomHeight_offset').expression = '0mm'```



---


<a name="設計-api-brepbodyfacesketch"></a>
## 📚 設計 API (BRepBody/Face/Sketch)
設計 API 參考
# 設計 API 參考 — BRepBody / BRepFace / Sketch

> [!NOTE]
> 幾何識別、投影草圖與特徵讀取常用 API 速查。

## BRepBody 常用屬性
````````````
| 屬性 / 方法 | 型態 | 說明 |
| --- | --- | --- |
| | | |
| body.name | str | Body 名稱（Occurrence 映射用） |
| body.faces | BRepFaces | 面集合 |
| body.edges | BRepEdges | 邊集合 |
| body.boundingBox | BoundingBox3D | AABB（cm） |
| body.entityToken | str | 唯一識別碼（修改後失效） |
| body.isVisible | bool | 可見性 |

## BRepFace 常用屬性
````````````
| 屬性 / 方法 | 型態 | 說明 |
| --- | --- | --- |
| | | |
| face.geometry.surfaceType | SurfaceTypes | 面型枚舉 |
| face.loops | BRepLoops | 迴圈集合 |
| face.boundingBox | BoundingBox3D | 面包圍盒（cm） |
| face.entityToken | str | 唯一識別碼 |
| adsk.core.Plane.cast(face.geometry).normal | Vector3D | 平面法向量 |
| adsk.core.Cylinder.cast(face.geometry).radius | float cm | 圓柱半徑 |

## BRepLoop / BRepEdge 常用屬性
``````````````
| 屬性 | 說明 |
| --- | --- |
| | |
| loop.isOuter | True = 外圈 |
| loop.coEdges | CoEdge 集合，.edge 為 BRepEdge |
| edge.geometry.curveType | Line3DCurveType / Arc3DCurveType … |
| edge.length | float cm |
| edge.startVertex.geometry | Point3D 起點 |
| adsk.core.Arc3D.cast(edge.geometry).radius | 弧半徑 cm |
| adsk.core.Arc3D.cast(edge.geometry).center | 弧中心點 cm |

## SurfaceTypes 枚舉
````````````
| 常數 | 說明 |
| --- | --- |
| | |
| PlaneSurfaceType | 平面 |
| CylinderSurfaceType | 圓柱面（孔壁） |
| ConeSurfaceType | 錐面（倒角孔） |
| SphereSurfaceType | 球面 |
| TorusSurfaceType | 環面 |
| NurbsSurfaceType | 自由曲面 |

## Curve3DTypes 枚舉
````````
| 常數 | 說明 |
| --- | --- |
| | |
| Line3DCurveType | 直線 |
| Arc3DCurveType | 弧（含圓） |
| EllipticalArc3DCurveType | 橢圓弧 |
| NurbsCurve3DType | NURBS 曲線 |

## root.findBRepUsingRay

```python
entities = root.findBRepUsingRay(
 start_point, # Point3D
 ray_direction, # Vector3D
 adsk.fusion.BRepEntityTypes.BRepFaceEntityType,
 0.001, # ray_radius cm
 False, # include_invisible
 hit_pts, # ObjectCollection
)
# item(0) = 最近命中面；回傳空 = miss```

## Sketch 投影 API

```python
sk = root.sketches.add(planar_face)
oc = sk.project(edge) # 回傳 ObjectCollection
# 判斷物件類型
if adsk.fusion.SketchCircle.cast(oc.item(i)): ...
if adsk.fusion.SketchArc.cast(oc.item(i)): ...
if adsk.fusion.SketchLine.cast(oc.item(i)): ...
# 注意：project() 只接受 native body 的邊```

## units 換算（內部單位 = cm）
````````
| 換算 | 公式 |
| --- | --- |
| | |
| cm → mm | x * 10.0 |
| mm → cm | x / 10.0 |
| cm² → mm² | x * 100.0 |
| cm³ → mm³ | x * 1000.0 |

> [!IMPORTANT]
> 重要限制：
-`sketch.project(edge)`對 Occurrence proxy 回傳 None，需映射至 root.bRepBodies
-`SketchPoint.isVisible`不存在，孤立點用 deleteMe() 清除
-`entityToken`模型修改後失效，操作後需重查
- Assembly 設計不可創建/修改/刪除幾何




---


<a name="cam-parameter-api-官方完整"></a>
## 📚 CAM Parameter API (官方完整)
CAM Parameter API
# CAM Parameter API — 官方完整參考 (adsk.cam)

> [!NOTE]
> 來源：Fusion API Documentation (live query)。所有類別、屬性、方法均來自官方 API。

## CAMParameter — 單一參數物件

> [!NOTE]
> Base class for representing parameter of an operation.

### Properties
``````````````````````````
| 屬性 | 說明 |
| --- | --- |
| | |
| name | Gets the name (internal name) of the parameter |
| title | Returns the title as seen in the user interface |
| fullTitle | Returns the full title as seen in the user interface |
| expression | Gets and sets the value expression of the parameter |
| value | Returns ParameterValue subclass object (get/set value) |
| isEnabled | Gets if this parameter is enabled |
| isEditable | Returns whether expression/value can be modified |
| isVisible | Gets if this parameter is visible in the UI |
| isDeprecated | Gets if this parameter is deprecated |
| error | Returns message for any active error on this parameter |
| warning | Returns message for any active warning |
| userDefaultExpression | Gets/sets the user default expression |
| systemDefaultExpression | Returns the system default expression (read-only) |

### Methods
``
| 方法 | 說明 |
| --- | --- |
| | |
| saveExpressionAsUserDefault() | Saves the current expression as user default value |

## CAMParameters — 參數集合

> [!NOTE]
> Collection providing access to parameters of an existing operation.
````````
| 成員 | 說明 |
| --- | --- |
| | |
| count | The number of items in the collection |
| item(index) | Returns parameter at specified index |
| itemByName(name) | Returns parameter by internal name |
| resetToSystemDefaults() | Resets each parameter to its system default |

## ParameterValue 子類別

> [!NOTE]
> Base class: ParameterValue (has .parent property). Cast via adsk.cam.XxxParameterValue.cast(param.value)
``````````
| 類別 | value 屬性 / 方法 | 說明 |
| --- | --- | --- |
| | | |
| BooleanParameterValue | value: bool | Boolean parameter |
| FloatParameterValue | value: float (internal units) | type: FloatParameterValueTypes | Float / physical quantity parameter |
| ChoiceParameterValue | value: str | getChoices() -> list | String choice (enum) parameter |
| CadContours2dParameterValue | getCurveSelections() | applyCurveSelections(curves) | 2D geometry contour parameter. Must re-apply after model update. |
| CadMachineAvoidGroupsParameterValue | getMachineAvoidGroups() | applyMachineAvoidGroups(groups) | Machine avoid groups parameter |

## FloatParameterValueTypes — 物理量型別枚舉
````````````````````````
| 常數 | 單位 | 說明 |
| --- | --- | --- |
| | | |
| UnspecifiedValueType | — | Unspecified, can represent any type |
| LengthValueType | cm | Length |
| AngleValueType | rad | Angle |
| LinearVelocityValueType | mm/min | Linear velocity (feed rate) |
| RotationalVelocityValueType | rpm | Rotational velocity (spindle speed) |
| TimeValueType | s | Time |
| WeightValueType | kg | Weight |
| PowerValueType | W | Power |
| FlowRateValueType | l/min | Flow rate |
| AreaValueType | cm² | Area |
| VolumeValueType | cm³ | Volume |
| TemperatureValueType | °C | Temperature |

## 使用範例

```python

# dump all parameters of an operation
def dump_params(op):
 params = op.parameters
 for i in range(params.count):
 p = params.item(i)
 print(f"[{i:03d}] {p.name:<42s} expr={p.expression} editable={p.isEditable}")

# set by expression (works for Boolean / Choice / Float)
p = op.parameters.itemByName('cycleType')
if p and p.isEditable:
 p.expression = "'drilling'"

# read float value in internal units
fv = adsk.cam.FloatParameterValue.cast(op.parameters.itemByName('spindleSpeed').value)
print(fv.value, fv.type) # rpm

# set 2D geometry
cv = adsk.cam.CadContours2dParameterValue.cast(op.parameters.itemByName('geometries').value)
curves = cv.getCurveSelections()
curves.add(adsk.cam.CadCurve.createFaceContour(face))
cv.applyCurveSelections(curves)
```



---


<a name="setup--operation-api-官方完整"></a>
## 📚 Setup & Operation API (官方完整)
Setup & Operation API
# Setup & Operation API — 官方完整參考 (adsk.cam)

> [!NOTE]
> 來源：Fusion API Documentation (live query)

## Setup — Properties
``````````````````````````````````
| 屬性 | 說明 |
| --- | --- |
| | |
| operationType | Gets the Operation Type (OperationTypes enum) |
| isActive | Gets if this setup is active |
| operations | Returns Operations collection (immediate) |
| folders | Returns Folders collection |
| patterns | Returns Patterns collection |
| children | Returns immediate child operations/folders/patterns in browser order |
| allOperations | ObjectCollection of ALL operations in this setup (recursive) |
| models | Gets/sets input models: ObjectCollection of Occurrence/BRepBody/MeshBody |
| fixtures | Gets/sets fixtures: ObjectCollection of Occurrence/BRepBody/MeshBody |
| stockSolids | Gets/sets stock solid models |
| machine | Gets/sets Machine associated with the setup |
| stockMode | Gets/sets stock mode (SetupStockModes enum) |
| workCoordinateSystem | Gets WCS as 4x4 matrix. Use getAsCoordinateSystem() for origin/axes. |
| fixtureEnabled | Enables/disables fixture use for this setup |
| printSetting | Gets/sets PrintSetting (additive only) |
| visibilityManager | Visibility manager for this setup |
| stockMaterial | Gets/sets stock material |

## Setup — Methods
````````````````````````
| 方法 | 說明 |
| --- | --- |
| | |
| activate() | Sets this setup as the default container |
| createFromTemplate(path) | Add operations from template file |
| createFromTemplateXML(xml) | Add operations from template XML string |
| createFromCAMTemplate(template) | Create operations from CAMTemplate object |
| createFromCAMTemplate2(input) | Create operations from CAMTemplate (new CreateFromCAMTemplateInput pattern) |
| additiveContainerByType(type) | Returns additive container by type |
| deleteMe() | Deletes the setup from the document |
| duplicate() | Duplicate after itself |
| moveBefore(op) / moveAfter(op) / moveInto(container) | Move in the browser tree |
| copyBefore(op) / copyAfter(op) / copyInto(container) | Duplicate to position in tree |
| hasMissingReferences() | Check for missing references |
| removeReferences(entity) | Remove entity from operation and all descendants |

## SetupStockModes 枚舉
````````````````
| 常數 | 說明 |
| --- | --- |
| | |
| FixedBoxStock | Fixed Size Box |
| RelativeBoxStock | Relative Size Box |
| FixedCylinderStock | Fixed Size Cylinder |
| RelativeCylinderStock | Relative Size Cylinder |
| FixedTubeStock | Fixed Size Tube |
| RelativeTubeStock | Relative Size Tube |
| SolidStock | From Solid (body) |
| PreviousSetupStock | From Preceding Setup |

## OperationTypes 枚舉 (Setup.operationType)
````````
| 常數 | 說明 |
| --- | --- |
| | |
| MillingOperation | Milling |
| TurningOperation | Turning |
| JetOperation | Jet (waterjet/laser/plasma) |
| AdditiveOperation | Additive |

## Operation — Properties
````````````````````````
| 屬性 | 說明 |
| --- | --- |
| | |
| strategyType | Gets strategy type (OperationStrategyTypes enum) |
| isToolpathValid | Gets if toolpath is currently valid |
| isGenerating | Gets if operation is being generated |
| parent | Returns parent Setup, Folder or Pattern |
| hasToolpath | Gets if a toolpath exists (has been generated) |
| operationState | Gets current state (OperationStates enum) |
| generatingProgress | Gets generation progress value (0.0-1.0) |
| toolJson | Get/set tool in JSON format |
| toolPresetId | Get/set id of tool preset to be used |
| tool | Get/set tool for this operation |
| toolPreset | Get/set tool preset |
| referenceTool | Get/set reference tool |

## OperationStates 枚舉
````````
| 常數 | 說明 |
| --- | --- |
| | |
| IsValidOperationState | Valid and up to date; toolpath exists if applicable |
| IsInvalidOperationState | Operation or toolpath is invalid |
| SuppressedOperationState | Suppressed; no toolpath |
| NoToolpathOperationState | Toolpath does not exist (not yet generated) |

## OperationStrategyTypes — 2D
``````````````````````
| 常數 | 說明 |
| --- | --- |
| | |
| AdaptiveClearing2D | 2D adaptive roughing |
| Pocket2D | 2D pocket roughing |
| Face | 2D facing |
| Contour2D | 2D contour |
| Slot | 2D slot center-line milling |
| Trace | 2D trace along contours |
| Thread | 2D thread milling |
| Bore | 2D bore milling (cylindrical geometry) |
| Circular | 2D circular pocket milling |
| Engrave | 2D engrave / V-chamfer wall |
| Chamfer2D | 2D chamfer contours |

## OperationStrategyTypes — 3D
````````````````````````````````
| 常數 | 說明 |
| --- | --- |
| | |
| AdaptiveClearing | 3D adaptive roughing |
| PocketClearing | 3D conventional roughing |
| Parallel | 3D parallel finishing |
| Contour | 3D contour finishing (steep walls) |
| Horizontal | 3D horizontal flat area clearing |
| Scallop | 3D scallop finishing |
| Spiral | 3D spiral finishing |
| Pencil | 3D pencil corner finishing |
| Ramp | 3D ramp finishing |
| Radial | 3D radial finishing |
| MorphedSpiral | 3D morphed spiral |
| Projection | 3D projected finishing |
| SteepAndShallow | 3D steep+shallow auto finishing |
| Flow | 3D flow-surface finishing |
| Morph | 3D morph finishing |
| RestFinishing | 3D rest material finishing |

## OperationStrategyTypes — Multi-axis
````````
| 常數 | 說明 |
| --- | --- |
| | |
| RotaryFinishing | Multi-axis rotary finishing |
| Swarf | Multi-axis swarf |
| MultiAxisContour | Multi-axis contour |
| MultiAxisMorph | Multi-axis morph |

## OperationStrategyTypes — Drilling / Jet
````
| 常數 | 說明 |
| --- | --- |
| | |
| Drilling | Drilling / tapping / hole making |
| Jet2D | 2D waterjet / laser / plasma |

## OperationStrategyTypes — Turning
````````````````
| 常數 | 說明 |
| --- | --- |
| | |
| TurningFace | Turning face |
| TurningProfile | Turning profile roughing/finishing |
| TurningGroove | Turning groove |
| TurningThread | Turning thread |
| TurningChamfer | Turning chamfer |
| TurningPart | Turning cutoff |
| TurningProfileGroove | Turning groove profiling |
| TurningStockTransfer | Turning stock transfer (no toolpath) |

## OperationStrategyTypes — Probe / Inspection
``````````````
| 常數 | 說明 |
| --- | --- |
| | |
| ProbeWCS | Probe WCS |
| ProbeGeometry | Probe geometry |
| SurfaceInspection | Surface inspection with probe |
| ManualInspection | Manual inspection |
| PartAlignment | Part alignment |
| PathMeasure | Surface inspection with results folder |
| ManualMeasure | Recorded manual inspection results |




---


<a name="cam-core-api-camsetupsoperationstoollibpostprocess"></a>
## 📚 CAM Core API (CAM/Setups/Operations/ToolLib/PostProcess)
CAM Core API
# CAM Core API — 官方完整參考 (adsk.cam)

> [!NOTE]
> 來源：Fusion API Documentation (live query). 涵蓋 CAM / Setups / Operations / ToolLibrary / PostProcessInput

## CAM — Properties
``````````````````````````````````
| 屬性 | 說明 |
| --- | --- |
| | |
| setups | Returns the Setups collection |
| allOperations | ObjectCollection of ALL operations in the document |
| genericPostFolder | Gets the installed post folder path |
| personalPostFolder | Gets the personal post folder path |
| temporaryFolder | Gets the folder for temporary files |
| documentToolLibrary | Gets the document ToolLibrary |
| allMachines | Array of all machines in the document |
| ncPrograms | Returns collection of NC programs |
| manufacturingModels | Returns collection of manufacturing models |
| exportManager | Returns Export Manager |
| importManager | Returns Import Manager |
| inspectionResults | Returns results collection (pathMeasures / manualMeasure) |
| setupGroups | Returns SetupGroups collection |
| customGraphicsGroups | Returns customGraphicsGroups object |
| designRootOccurrence | CAM root component single occurrence referencing Design root |
| flatPatternOccurrences | Read-only list of flat pattern occurrences |
| documentStockMaterialLibrary | Gets the document StockMaterialLibrary |

## CAM — Methods
``````````````````````````````````
| 方法 | 說明 |
| --- | --- |
| | |
| generateToolpath(objects) | Generate/regenerate toolpaths for specified objects (incl. nested) |
| generateAllToolpaths() | Generate/regenerate ALL toolpaths in document |
| clearToolpath(objects) | Clear toolpaths for specified objects |
| clearAllToolpaths() | Clear ALL toolpaths in document |
| checkToolpath(objects) | Check if operations are valid and up to date |
| checkAllToolpaths() | Check ALL operations in document |
| postProcess(objects, input) | Post specified toolpaths to CNC file |
| postProcessAll(input) | Post ALL toolpaths in document |
| generateSetupSheet(objects, format, outputFolder, openInBrowser) | Generate setup sheets for specified objects |
| generateAllSetupSheets(format, outputFolder, openInBrowser) | Generate ALL setup sheets |
| getMachiningTime(objects) | Get machining time for specified objects |
| generateTemplateXML(objects) | Generate template XML string for specified operations/setups/folders |
| checkValidity() | Check if models changed; invalidate affected operations |
| clearMissingReferences() | Clear all missing references from all operations |
| export3MFForDefaultAdditiveSetup(path, supportType) | Export 3MF for default additive setup |
| deleteEntities(entities) | Delete specified entities associated with this product |
| findAttributes(groupName, attributeName) | Find attributes attached to objects |

## Setups 集合
````````````
| 成哣 | 說明 |
| --- | --- |
| | |
| count | Number of setups |
| item(index) | Returns setup at index |
| itemByName(name) | Returns setup by name |
| itemByOperationId(id) | Returns setup by operation id |
| createInput(operationType) | Creates a new SetupInput object |
| add(input) | Creates and adds a new Setup from SetupInput |

## SetupInput 建立 Setup 用

> [!NOTE]
> cam.setups.createInput(operationType) 回傳此物件
``````````````````````
| 屬性 | 說明 |
| --- | --- |
| | |
| name | Name of the new setup |
| operationType | OperationTypes enum |
| models | ObjectCollection of Occurrence/BRepBody/MeshBody |
| stockMode | SetupStockModes enum |
| stockSolids | Array of stock solid models |
| fixtureEnabled | Enable/disable fixture use |
| fixtures | Array of fixture models |
| machine | Machine object |
| printSetting | PrintSetting (additive) |
| parameters | CAMParameters for the setup to be created |
| isUsingPreviousSetupData | Use data from previous setup |

## Operations 集合

> [!NOTE]
> setup.operations / folder.operations / pattern.operations
``````````````
| 成哣 | 說明 |
| --- | --- |
| | |
| count | Number of operations |
| compatibleStrategies | List of strategies compatible with parent setup |
| item(index) | Returns operation at index |
| itemByName(name) | Returns operation by browser name |
| itemByOperationId(id) | Returns operation by operation id |
| createInput(strategy) | Creates a new OperationInput for given strategy |
| add(input) | Creates and adds a new Operation from OperationInput |

## OperationInput 建立 Operation 用

> [!NOTE]
> setup.operations.createInput(strategy) 回傳此物件
``````````````
| 屬性 | 說明 |
| --- | --- |
| | |
| strategy | Current strategy (OperationStrategyTypes) |
| parameters | CAMParameters for the new operation |
| tool | Optionally specify the tool (Tool object) |
| toolPreset | Optionally specify the tool preset |
| displayName | Override default browser-tree display name |
| generationMode | Automatic generation mode during creation |
| referenceTool | Optionally specify reference tool |

## ToolLibrary / DocumentToolLibrary

> [!NOTE]
> cam.documentToolLibrary 為 DocumentToolLibrary，包含以下成哣及 DocumentToolLibrary 副å 功能
``````````````````
| 成哣 | 說明 |
| --- | --- |
| | |
| count | Number of tools in the library |
| item(index) | Get Tool by index |
| add(tool) | Insert tool at end of library |
| remove(index) | Remove tool by index |
| toJson() | Generate JSON string of all tools |
| createQuery() | Create a ToolQuery to search for matching tools |
| updateTool(tool) | Update a tool in the library |
| createFromJson(json) [static] | Create ToolLibrary from JSON string |
| createEmpty() [static] | Create empty ToolLibrary |

### DocumentToolLibrary 額外方法
``````
| 方法 | 說明 |
| --- | --- |
| | |
| operationsByTool(tool) | Returns all operations using the given tool |
| update(tool) | Update tool in document tool library |
| toolsBySetupOrFolder(container) | Returns all tools used in a given setup or folder |

## PostProcessInput

> [!NOTE]
> PostProcessInput.create() 建立。傳入 cam.postProcess() / cam.postProcessAll()
``````````````````
| 屬性 | 說明 |
| --- | --- |
| | |
| programName | Program name or number |
| programComment | Program comment |
| postConfiguration | Full path to post configuration file (.cps) |
| outputFolder | Path for output folder |
| outputUnits | Units option for CNC output |
| isOpenInEditor | Open CNC file in editor after creation |
| areToolChangesMinimized | Reorder operations between setups to minimize tool changes |
| postProperties | List of post properties |
| machine | Machine used for post processing |

## 完整建立流程範例

```python
# 1. Get CAM product
cam = adsk.cam.CAM.cast(doc.products.itemByProductType('CAMProductType'))

# 2. Create Setup
setup_input = cam.setups.createInput(adsk.cam.OperationTypes.MillingOperation)
setup_input.name = 'Setup1'
setup_input.models = models_collection
setup = cam.setups.add(setup_input)

# 3. Create Operation
op_input = setup.operations.createInput(adsk.cam.OperationStrategyTypes.Drilling)
op_input.displayName = 'Drill1'
op = setup.operations.add(op_input)

# 4. Set parameters
op.parameters.itemByName('cycleType').expression = "'drilling'"
op.parameters.itemByName('holeMode').expression = "'selection-faces'"

# 5. Generate toolpath
cam.generateToolpath(op)

# 6. Post process
post_input = adsk.cam.PostProcessInput.create(
 'O0001', 'fanuc', outputFolder, adsk.cam.PostOutputUnitOptions.DocumentUnitsOutput)
cam.postProcess(op, post_input)```



---


<a name="machine--camtemplate--ncprogram-api"></a>
## 📚 Machine / CAMTemplate / NCProgram API
Machine / CAMTemplate / NCProgram API
# Machine / CAMTemplate / NCProgram API — 官方完整參考

> [!NOTE]
> 來源：Fusion API Documentation (live query)

## Machine — Properties
````````````````````
| 成哣 / 屬性 | 說明 |
| --- | --- |
| | |
| vendor | Gets/sets vendor name |
| model | Gets/sets model name |
| description | Gets/sets description |
| id | Gets unique identifier |
| capabilities | Gets capabilities of the machine |
| kinematics | Gets kinematics tree |
| hasPost | Checks if machine has a post assigned |
| postURL | Gets/sets URL of post assigned to this machine |
| elements | Gets list of elements that make up this machine |
| hasSimulationModel | Returns true if machine has a simulation model |

## Machine — Methods & Static
````````````
| 成哣 / 屬性 | 說明 |
| --- | --- |
| | |
| save(filePath) | Saves the Machine to a file |
| equivalentTo(other) | Checks if machine is equivalent to another |
| clearSimulationModel() | Clears the simulation model from the machine |
| Machine.createFromTemplate(template) [static] | Creates a Machine from a template |
| Machine.createFromFile(filePath) [static] | Creates a Machine from a file |
| Machine.create(machineInput) [static] | Creates a machine from MachineInput object |

## MachineCoolant 枚舉
````````````````
| 常數 | 說明 |
| --- | --- |
| | |
| MachineCoolant_FLOOD | Flood coolant |
| MachineCoolant_MIST | Mist coolant |
| MachineCoolant_THROUGH_TOOL | Through tool coolant |
| MachineCoolant_AIR | Air coolant |
| MachineCoolant_AIR_THROUGH_TOOL | Air through tool |
| MachineCoolant_SUCTION | Suction |
| MachineCoolant_FLOOD_MIST | Flood + mist |
| MachineCoolant_FLOOD_THROUGH_TOOL | Flood + through tool |

## MachineAxisTypes 枚舉
````
| 常數 | 說明 |
| --- | --- |
| | |
| LinearMachineAxisType | An axis that moves in a straight line |
| RotaryMachineAxisType | An axis that rotates about a point |

## MachineLibrary — Methods

> [!NOTE]
> 通常由 adsk.cam.CAM.getMachineLibrary() 取得
``````````````````````````
| 成哣 / 屬性 | 說明 |
| --- | --- |
| | |
| createQuery() | Create MachineQuery to search for machines |
| importMachine(machine, url) | Import a machine at a specific location |
| updateMachine(machine, url) | Update a machine in the library |
| machineAtURL(url) | Get specific machine by URL |
| childMachines(parentUrl) | Get all machines under a parent folder URL |
| urlByLocation(location) | Get URL for a given LibraryLocations enum value |
| displayName(url) | Get localized display name for a given URL |
| childFolderURLs(url) | Get all library folders under given URL |
| childAssetURLs(url) | Get all assets under given URL |
| deleteFolder(url) | Delete folder by URL |
| deleteAsset(url) | Delete asset by URL |
| createFolder(url) | Create new folder in the library |
| doesPathExist(url) | Checks if URL points to existing folder or asset |

## CAMTemplate — Properties
``````````
| 成哣 / 屬性 | 說明 |
| --- | --- |
| | |
| name | Gets/sets name of the template |
| description | Gets/sets description |
| isHoleTemplate | Whether this is a hole template |
| operations | Exposes operations in the template |
| attributes | Returns collection of attributes associated with template |

## CAMTemplate — Methods & Static
````````````````
| 成哣 / 屬性 | 說明 |
| --- | --- |
| | |
| save(filePath) | Save CAMTemplate to file |
| getHoleSignatureXML() | Convert hole signature to XML string |
| setHoleSignatureXML(xml) | Provide XML snippet to specify hole signature |
| CAMTemplate.createFromXML(xml) [static] | Create CAMTemplate from XML string |
| CAMTemplate.createFromOperations(operations) [static] | Create template from array of operations |
| CAMTemplate.createHoleTemplateFromOperations(ops) [static] | Create hole CAMTemplate from hole operations |
| CAMTemplate.createFromFile(filePath) [static] | Create CAMTemplate from file on disk |
| CAMTemplate.createEmpty() [static] | Create empty CAMTemplate |

## CreateFromCAMTemplateInput

> [!NOTE]
> 傳入 setup.createFromCAMTemplate2(input)
``````
| 成哣 / 屬性 | 說明 |
| --- | --- |
| | |
| camTemplate | Gets/sets the template to be instantiated |
| mode | Gets/sets the mode used for generation |
| CreateFromCAMTemplateInput.create() [static] | Creates empty input object |

## CAMTemplateOperationInput

> [!NOTE]
> 用於編輯模板內å·¥序參數（與 OperationInput 類似但不完全相同）
````````````````
| 成哣 / 屬性 | 說明 |
| --- | --- |
| | |
| strategy | Current strategy type |
| parameters | CAMParameters for the template operation |
| tool | Optionally specify tool |
| toolPreset | Optionally specify tool preset |
| displayName | Override browser-tree display name |
| geometryIndexCount | Number of geometry indices that can be selected |
| isGeometryIndexEnabled(index) | Get whether geometry index is selected |
| setGeometryIndexEnabled(index, enabled) | Set whether geometry index is selected |

## NCProgram — Properties
````````````
| 成哣 / 屬性 | 說明 |
| --- | --- |
| | |
| operations | Gets/sets operations included in the NC program |
| filteredOperations | Gets all valid operations (filtered) |
| postConfiguration | Gets/sets post configuration |
| machine | Gets/sets machine |
| postParameters | Gets post parameters |
| fusionHubFolder | DataFolder for exported files (if posting to Fusion Hub) |

## NCProgram — Methods
``````````
| 成哣 / 屬性 | 說明 |
| --- | --- |
| | |
| updatePostParameters(input) | Override default post parameters with user input |
| postProcess(options) | Create machine-specific NC code for this NC program |
| deleteMe() | Delete this NC program |
| duplicate() | Duplicate after itself |
| moveBefore(op) / moveAfter(op) / moveInto(container) | Move in browser tree |

## NCPrograms 集合

> [!NOTE]
> cam.ncPrograms 取得
````````````
| 成哣 / 屬性 | 說明 |
| --- | --- |
| | |
| count | Number of NC programs |
| item(index) | Returns NC program at index |
| itemByName(name) | Returns NC program by name |
| itemByOperationId(id) | Returns NC program by operation id |
| createInput() | Create NCProgramInput object |
| add(input) | Creates and adds new NC program |

## NCProgramInput
``````
| 成哣 / 屬性 | 說明 |
| --- | --- |
| | |
| parameters | CAMParameters for the new NC program |
| operations | Operations to include in this NC program |
| displayName | Override browser display name |

## NCProgramPostProcessOptions
````````
| 成哣 / 屬性 | 說明 |
| --- | --- |
| | |
| isFailOnToolNumberDuplication | Abort if two tools share the same tool number |
| postProcessExecutionBehavior | Behavior for operations with errors or out-of-date state |
| fusionHubExecutionBehavior | Behavior for exporting to Fusion Hub |
| NCProgramPostProcessOptions.create() [static] | Create new options object |

## ToolQuery

> [!NOTE]
> toolLibrary.createQuery() 取得。甩0 criteria 時回傳全部工具
``````````
| 成哣 / 屬性 | 說明 |
| --- | --- |
| | |
| vendor | Case-insensitive vendor filter |
| url | Location/folder URL to search in |
| location | LibraryLocations enum â location to search |
| criteria | List of criteria a tool must fulfill |
| execute() | Run query; returns ToolQueryResult vector |

## ToolQueryResult
````````
| 成哣 / 屬性 | 說明 |
| --- | --- |
| | |
| toolLibraryURL | URL of the ToolLibrary asset |
| toolLibrary | ToolLibrary containing the matching tool |
| tool | The matching Tool object |
| toolItemIndex | Index of the tool inside the ToolLibrary |

## 範例：長途寫法

```python
# --- Machine: load from library ---
lib = adsk.cam.MachineLibrary.getMachineLibrary() # or via cam
url = lib.urlByLocation(adsk.cam.LibraryLocations.LocalLibraryLocation)
machines = lib.childMachines(url)

# --- CAMTemplate: create from operations and apply ---
tmpl = adsk.cam.CAMTemplate.createFromOperations([op1, op2])
tmpl.name = 'MyTemplate'
tmpl.save(r'C:/Templates/my.hsmtemplate')

inp = adsk.cam.CreateFromCAMTemplateInput.create()
inp.camTemplate = adsk.cam.CAMTemplate.createFromFile(r'C:/Templates/my.hsmtemplate')
setup.createFromCAMTemplate2(inp)

# --- NCProgram: create and post ---
nc_input = cam.ncPrograms.createInput()
nc_input.displayName = 'Program1'
nc_input.operations = [op1, op2]
nc = cam.ncPrograms.add(nc_input)
opts = adsk.cam.NCProgramPostProcessOptions.create()
nc.postProcess(opts)

# --- ToolQuery: find tool by name ---
q = cam.documentToolLibrary.createQuery()
results = q.execute()
for res in results:
 print(res.tool, res.toolItemIndex)```



---


<a name="製造-api-功能總覽"></a>
## 📚 製造 API 功能總覽
製造 API 功能總覽
# Fusion 製造 API 功能總覽 (adsk.cam)

> [!NOTE]
> 來源：Fusion API Documentation (live query) — 完整製造工作區åª視圖

## ① 製造 API 可以做什麼？
````````````````````````````
| 能力 | API 入口 |
| --- | --- |
| | |
| 建立 Setup | cam.setups.createInput() + cam.setups.add(input) |
| 建立 Operation | setup.operations.createInput(strategy) + .add(input) |
| 建立 Folder | setup.folders.addFolder(name) |
| 建立 NC Program | cam.ncPrograms.createInput() + cam.ncPrograms.add(input) |
| 讀取 / 設定參數 | op.parameters.itemByName(name).expression = ... |
| 產生 / 清除工具路å¾ | cam.generateToolpath(op) / cam.clearToolpath(op) |
| 後è理切å² NC | cam.postProcess(op, PostProcessInput) / cam.postProcessAll(input) |
| 套用模板 | setup.createFromCAMTemplate2(CreateFromCAMTemplateInput) |
| 查詢工具庫 | toolLibrary.createQuery().execute() |
| 載入 / 儲存機器 | Machine.createFromFile() / machine.save() |
| 製造模型 (ManufacturingModel) | cam.manufacturingModels.createInput() + .add(input) |
| 修正工具庫 | cam.documentToolLibrary.add() / .update() / .remove() |
| 找所有工序狀態 | cam.allOperations -> op.operationState |
| 模型有效性檢查 | cam.checkValidity() / cam.checkAllToolpaths() |

## ② 物件樹結構 (browser tree)

```python
CAM
├─ ManufacturingModels (製造模型集合)
└─ Setups
 ├─ Setup
 │ ├─ Operations (工序集合)
 │ │ └─ Operation (單一工序)
 │ ├─ CAMFolders (資料夾集合)
 │ │ └─ CAMFolder
 │ └─ CAMPatterns (陣列集合)
 │ └─ CAMPattern
 └─ NCPrograms (NC 程式集合)
 └─ NCProgram```

## ③ CAMFolder — Properties
``````````````
| 成哣 / 屬性 | 說明 |
| --- | --- |
| | |
| isActive | Gets if this folder is active |
| operations | Operations collection inside this folder |
| folders | Sub-folders collection |
| patterns | Patterns collection |
| children | Immediate child operations/folders/patterns in browser order |
| allOperations | All operations in this folder (recursive) |
| parent | Parent Setup, Folder or Pattern |

## CAMFolder — Methods
````````````````````````
| 成哣 / 屬性 | 說明 |
| --- | --- |
| | |
| addFolder(name) | Create sub-folder with given name |
| activate() | Set as default container |
| createFromTemplate(path) | Add operations from template file |
| createFromTemplateXML(xml) | Add operations from XML string |
| createFromCAMTemplate(tmpl) | Add operations from CAMTemplate |
| createFromCAMTemplate2(input) | Add operations from CAMTemplate (new pattern) |
| deleteMe() | Delete this folder |
| duplicate() | Duplicate after itself |
| moveBefore(op) / moveAfter(op) / moveInto(c) | Move in browser tree |
| copyBefore(op) / copyAfter(op) / copyInto(c) | Copy to position in tree |
| hasMissingReferences() | Check for missing references |
| removeReferences(entity) | Remove entity from this folder and descendants |

## CAMFolders 集合

> [!NOTE]
> setup.folders / camFolder.folders
``````````
| 成哣 / 屬性 | 說明 |
| --- | --- |
| | |
| count | Number of folders |
| item(index) | Returns folder at index |
| itemByName(name) | Returns folder by browser name |
| itemByOperationId(id) | Returns folder by operation id |
| addFolder(name) | Creates and returns a new CAMFolder |

## ④ CAMPattern — Properties
``````````````
| 成哣 / 屬性 | 說明 |
| --- | --- |
| | |
| operations | Operations collection inside this pattern |
| folders | Folders collection inside this pattern |
| patterns | Sub-patterns collection |
| children | Immediate children in browser order |
| allOperations | All operations in this pattern (recursive) |
| parent | Parent Setup, Folder or Pattern |
| parameters | CAMParameters for this pattern |

## CAMPattern — Methods
````````````````
| 成哣 / 屬性 | 說明 |
| --- | --- |
| | |
| activate() | Set as default container |
| createFromTemplate(path) | Add operations from template file |
| createFromCAMTemplate2(input) | Add operations from CAMTemplate |
| deleteMe() | Delete this pattern |
| duplicate() | Duplicate after itself |
| moveBefore(op) / moveAfter(op) / moveInto(c) | Move in browser tree |
| hasMissingReferences() | Check for missing references |
| removeReferences(entity) | Remove entity from pattern and descendants |

## CAMPatterns 集合

> [!NOTE]
> setup.patterns / camFolder.patterns
````````
| 成哣 / 屬性 | 說明 |
| --- | --- |
| | |
| count | Number of patterns |
| item(index) | Returns pattern at index |
| itemByName(name) | Returns pattern by browser name |
| itemByOperationId(id) | Returns pattern by operation id |

## ⑤ ManufacturingModel — Properties

> [!NOTE]
> 一個 ManufacturingModel 是設計場景的衍生，可變更而ä¸影響原始設計
````````
| 成哣 / 屬性 | 說明 |
| --- | --- |
| | |
| name | Gets/sets display name |
| id | Unique identifier within the document |
| isActive | Whether this ManufacturingModel is active in UI |
| occurrence | Returns occurrence for this ManufacturingModel |

## ManufacturingModel — Methods
````````
| 成哣 / 屬性 | 說明 |
| --- | --- |
| | |
| activate() | Makes this ManufacturingModel active in the UI |
| duplicate() | Creates a copy within its parent collection |
| deleteMe() | Deletes this ManufacturingModel |
| syncManufacturingModel() | Checks/syncs changes from original design |

## ManufacturingModels 集合

> [!NOTE]
> cam.manufacturingModels
``````````````
| 成哣 / 屬性 | 說明 |
| --- | --- |
| | |
| count | Number of manufacturing models |
| item(index) | Get ManufacturingModel by index |
| itemByName(name) | Get by browser name (returns all matches) |
| itemById(id) | Get by unique id |
| createInput() | Create ManufacturingModelInput object |
| add(input) | Create and add new ManufacturingModel |
| syncAllManufacturingModels() | Sync all manufacturing models with design changes |

## ⑥ ToolLibraries — Methods

> [!NOTE]
> 管理工具庫集合（區別於 cam.documentToolLibrary 單文件庫）
````````````````````````
| 成哣 / 屬性 | 說明 |
| --- | --- |
| | |
| importToolLibrary(library, url) | Import a ToolLibrary at specific location |
| updateToolLibrary(library, url) | Update ToolLibrary in the collection |
| toolLibraryAtURL(url) | Get ToolLibrary at given URL |
| createQuery() | Create ToolQuery to search across libraries |
| urlByLocation(location) | Get URL for LibraryLocations enum value |
| displayName(url) | Get localized display name for URL |
| childFolderURLs(url) | Get all sub-folder URLs under given URL |
| childAssetURLs(url) | Get all asset URLs under given URL |
| deleteFolder(url) | Delete folder by URL |
| deleteAsset(url) | Delete asset by URL |
| createFolder(url) | Create new folder in the library |
| doesPathExist(url) | Check if URL points to existing folder or asset |

## ⑦ LibraryLocations 枚舉
``````````````
| 常數 | 說明 |
| --- | --- |
| | |
| LocalLibraryLocation | Local machine folder |
| CloudLibraryLocation | Cloud (Fusion Hub) folder |
| Fusion360LibraryLocation | Built-in Fusion 360 library folder |
| HubLibraryLocation | Hub shared library folder |
| ExternalLibraryLocation | External folder not in library |
| NetworkLibraryLocation | Network folder (internal use) |
| OnlineSamplesLibraryLocation | Online samples (internal use) |

## 完整常用範例

```python
import adsk.core, adsk.cam, adsk.fusion

# 取得 CAM 物件
cam = adsk.cam.CAM.cast(doc.products.itemByProductType('CAMProductType'))

# 建立 Setup
si = cam.setups.createInput(adsk.cam.OperationTypes.MillingOperation)
si.name = 'Setup1'
si.models = models # ObjectCollection of BRepBody
setup = cam.setups.add(si)

# 建立 Folder
folder = setup.folders.addFolder('Roughing')

# 建立 Operation 在 Folder 內
oi = folder.operations.createInput(adsk.cam.OperationStrategyTypes.AdaptiveClearing)
op = folder.operations.add(oi)

# 設定參數
op.parameters.itemByName('tolerance').expression = '0.01mm'

# 產生工具路徑
cam.generateToolpath(op)

# 建立 ManufacturingModel
mi = cam.manufacturingModels.createInput()
mi.name = 'Mfg-v1'
mfg = cam.manufacturingModels.add(mi)

# 從工具庫檔載入工具
lib_url = cam.documentToolLibrary.urlByLocation(adsk.cam.LibraryLocations.LocalLibraryLocation)
q = cam.documentToolLibrary.createQuery()
results = q.execute()
for res in results:
 t = res.tool
 print(t)

# 後處理
pi = adsk.cam.PostProcessInput.create('O0001', 'fanuc', output_dir, adsk.cam.PostOutputUnitOptions.DocumentUnitsOutput)
cam.postProcessAll(pi)```



---


<a name="特徵辨識-api-孔口袋pocketrecognitionselection"></a>
## 📚 特徵辨識 API (孔/口袋/PocketRecognitionSelection)
特徵辨識 API
# 特徵辨識 API — 孔 / 嘴袋 / 輪廓 (adsk.cam)

> [!NOTE]
> 來源：Fusion API Documentation (live query)
⚠️ 標註 [Machining Extension] 的方法需要授權。recognizePockets() 基礎版不需要。
## ① 孔辨識 (RecognizedHole)

> [!NOTE]
> 支持對抗層結構：圓柱 + 錐面 + 平面 + 環面，可取得孔簽名 XML。

### 静態方法（入口）
````````
| 屬性 / 方法 | 說明 |
| --- | --- |
| | |
| RecognizedHole.recognizeHoles(body, attackVector) | Returns RecognizedHoles collection from body + attack direction vector |
| RecognizedHole.recognizeHolesWithInput(input) | Returns RecognizedHoles using RecognizedHoleInput (需 Machining Extension) |
| RecognizedHoleGroup.recognizeHoleGroups(body, attackVector) | Returns holes grouped by similar geometry (RecognizedHoleGroups) |
| RecognizedHoleGroup.recognizeHoleGroupsWithInput(input) | Returns hole groups using input object |

### RecognizedHole Properties
``````````````````````
| 屬性 / 方法 | 說明 |
| --- | --- |
| | |
| axis | Unit vector pointing up out of the hole (global coords) |
| top | Point at center of hole top |
| bottom | Point at center of hole bottom |
| topDiameter | Diameter at hole top (cm) = first segment top diameter |
| bottomDiameter | Diameter at hole bottom (cm) = last segment bottom diameter |
| totalLength | Total length of all segments (cm) |
| segmentCount | Number of segments in this hole |
| isThrough | True if this is a through hole |
| isThreaded | True if at least one segment is threaded |
| hasWarnings | True if any warnings associated |
| hasErrors | True if any errors associated |

### RecognizedHole Methods
````
| 屬性 / 方法 | 說明 |
| --- | --- |
| | |
| segment(index) | Returns RecognizedHoleSegment at index |
| getHoleSignatureXML() | Convert hole to XML signature string |

### RecognizedHoleSegment Properties
````````````````````
| 屬性 / 方法 | 說明 |
| --- | --- |
| | |
| holeSegmentType | HoleSegmentType enum: Cylinder / Cone / Flat / Torus |
| face | The model BRepFace this segment references |
| faces | All model faces this segment references |
| topDiameter | Diameter at segment top (cm) |
| bottomDiameter | Diameter at segment bottom (cm) |
| height | Height of segment top to bottom (cm) |
| axis | Unit vector pointing up out of segment |
| isThreaded | True if this segment is threaded |
| threadFeatures | Thread features for this segment (or null) |
| halfAngle | Cone half-angle in radians (Cone segments only) |

### HoleSegmentType 枚舉
````````
| 常數 | 說明 |
| --- | --- |
| | |
| HoleSegmentTypeCylinder | Cylindrical segment (standard hole wall) |
| HoleSegmentTypeCone | Conical segment (countersink, chamfer tip). Has halfAngle. |
| HoleSegmentTypeFlat | Flat segment (counterbore bottom / flat bottom) |
| HoleSegmentTypeTorus | Toroidal segment (fillet between wall and bottom) |

### RecognizedHoleGroup / RecognizedHoleGroups

> [!NOTE]
> 將幾何相似的孔分組，區別不同直徑/深度的孔群
````````
| 屬性 / 方法 | 說明 |
| --- | --- |
| | |
| count | Number of holes in this group |
| hasWarnings | True if any warnings |
| hasErrors | True if any errors |
| item(index) | Returns RecognizedHole at index |

## ② 嘴袋辨識 (RecognizedPocket)

> [!NOTE]
> 外開放 + 封閉嘴袋均支持。返回 edges (boundaries/islands)、深度、底面型別。

### 静態方法（入口）
````
| 屬性 / 方法 | 說明 |
| --- | --- |
| | |
| RecognizedPocket.recognizePockets(body, attackVector) | Returns RecognizedPockets from body + attack vector. Basic API, no extension required. |
| RecognizedPocket.recognizePocketsWithInput(input) | Returns RecognizedPockets using RecognizedPocketInput (Machining Extension 必需) |

### RecognizedPocket Properties
``````````````````
| 屬性 / 方法 | 說明 |
| --- | --- |
| | |
| boundaries | Outer boundaries of pocket as ProfileLoop list (cm) |
| islands | Islands (inner loops) inside pocket as ProfileLoop list (cm) |
| depth | Depth of pocket (cm) |
| isThrough | True if this is a through pocket |
| isClosed | True if pocket is fully closed |
| bottomType | RecognizedPocketBottomType enum |
| faces | All BRepFaces making up this pocket |
| sharedFaces | Faces shared with other pockets |
| attackVector | Attack vector used to recognize this pocket |

### RecognizedPocketBottomType 枚舉
``````````
| 常數 | 說明 |
| --- | --- |
| | |
| RecognizedPocketBottomTypeFlat | Flat bottom, sharp edges at walls |
| RecognizedPocketBottomTypeThrough | No bottom anywhere (through) |
| RecognizedPocketBottomTypeChamfer | Chamfer around all bottom edges |
| RecognizedPocketBottomTypeFillet | Fillet around all bottom edges |
| RecognizedPocketBottomTypeOther | Mixed or other bottom types |

### RecognizedPocketInput [Machining Extension]
````````
| 屬性 / 方法 | 說明 |
| --- | --- |
| | |
| body | The BRepBody on which to recognize pockets |
| attackVectors | Array of attack vectors to use |
| isIncludingBosses | Whether to include bosses in recognized pockets |
| RecognizedPocketInput.create() [static] | Creates a new RecognizedPocketInput object |

## ③ PocketRecognitionSelection (輸入複數筛選條件)

> [!NOTE]
> 用於 geometries 參數的 2D 嘴袋輪廓自動選取
``````````````
| 屬性 / 方法 | 說明 |
| --- | --- |
| | |
| isSetupModelSelected | Include all bodies set as setup models |
| areHolesIncluded | Interpret holes as pockets |
| minimumHoleDiameter | Lower bound for hole diameter (cm) |
| minimumCornerRadius | Smallest corner radius to machine (cm) |
| maximumCornerRadius | Largest corner radius to machine (cm) |
| minimumPocketDepth | Shallowest pocket depth to machine (cm) |
| maximumPocketDepth | Deepest pocket depth to machine (cm) |

## 完整範例

```python
# ===== 孔辨識 =====
attack = adsk.core.Vector3D.create(0, 0, -1) # WCS Z-
holes = adsk.cam.RecognizedHole.recognizeHoles(body, attack)
for i in range(holes.count):
 h = holes.item(i)
 print("axis:", h.axis.x, h.axis.y, h.axis.z)
 print("topDia:", round(h.topDiameter * 10, 3), "mm")
 print("length:", round(h.totalLength * 10, 3), "mm")
 print("through:", h.isThrough)
 for s in range(h.segmentCount):
 seg = h.segment(s)
 print(" seg type:", seg.holeSegmentType)
 if seg.holeSegmentType == adsk.cam.HoleSegmentType.HoleSegmentTypeCone:
 print(" half angle:", round(import_math_degrees(seg.halfAngle), 1), "deg")

# ===== 孔分組 =====
groups = adsk.cam.RecognizedHoleGroup.recognizeHoleGroups(body, attack)
for gi in range(groups.count):
 g = groups.item(gi)
 print("group holes:", g.count)

# ===== 嘴袋辨識 =====
pockets = adsk.cam.RecognizedPocket.recognizePockets(body, attack)
for i in range(pockets.count):
 p = pockets.item(i)
 print("depth:", round(p.depth * 10, 3), "mm")
 print("through:", p.isThrough)
 print("bottomType:", p.bottomType)
 print("faces count:", len(list(p.faces)))

# ===== RecognizedPocketInput (Machining Extension) =====
rpi = adsk.cam.RecognizedPocketInput.create()
rpi.body = body
rpi.attackVectors = [attack]
rpi.isIncludingBosses = False
pockets2 = adsk.cam.RecognizedPocket.recognizePocketsWithInput(rpi)```



---


<a name="幾何選取-api-curveselectionschainsilhouettesketch"></a>
## 📚 幾何選取 API (CurveSelections/Chain/Silhouette/Sketch)
幾何選取 & 加工時間 API
# 幾何選取 & 製造時間 API (adsk.cam)

> [!NOTE]
> 來源：Fusion API Documentation (live query)。涵蓋 CurveSelections / ChainSelection / FaceContourSelection / SilhouetteSelection / SketchSelection / PocketRecognitionSelection / MachiningTime

## ① 幾何選取流程

```python
# 標準流程
geo_param = op.parameters.itemByName('geometries')
cv = adsk.cam.CadContours2dParameterValue.cast(geo_param.value)
sels = cv.getCurveSelections() # CurveSelections

# 新增 Face Contour
fc = sels.createNewFaceContourSelection()
fc.inputGeometry = top_face
fc.loopType = adsk.cam.LoopTypes.OnlyOutsideLoops
cv.applyCurveSelections(sels)

# 新增 Chain (邊尾連)
ch = sels.createNewChainSelection()
ch.inputGeometry = edge
cv.applyCurveSelections(sels)

# 新增 Pocket Recognition Selection
prs = sels.createNewPocketRecognitionSelection()
prs.isSetupModelSelected = True
prs.minimumPocketDepth = 0.2 # cm
prs.maximumPocketDepth = 5.0
cv.applyCurveSelections(sels)```

## ② CurveSelection 基ç¤類

> [!NOTE]
> 所有å­類別的共同屬性
````
| 屬性 / 方法 | 說明 |
| --- | --- |
| | |
| inputGeometry | Get/set input geometry (BRepEdge / BRepFace / BRepBody / Sketch â depends on subclass) |
| outputGeometry | Gets contained curves as raw geometry (read-only) |

## ② CurveSelections 集合

> [!NOTE]
> cv.getCurveSelections() 回傳此物件。修改後必須呼叫 cv.applyCurveSelections(sels) 才生效
``````````````````````
| 屬性 / 方法 | 說明 |
| --- | --- |
| | |
| count | Number of selections |
| item(index) | Returns CurveSelection at index |
| clear() | Clears all entries |
| createNewChainSelection() | Add + return new ChainSelection |
| createNewFaceContourSelection() | Add + return new FaceContourSelection |
| createNewSilhouetteSelection() | Add + return new SilhouetteSelection |
| createNewPocketSelection() | Add + return new pocket selection |
| createNewSketchSelection() | Add + return new SketchSelection |
| createNewPocketRecognitionSelection() | Add + return new PocketRecognitionSelection |
| remove(index) | Remove selection at index |
| removeByObject(sel) | Remove specified selection object |

## ③ ChainSelection

> [!NOTE]
> BRepEdge / Sketch 邊尾連。適用於 2D Contour、Trace、Slot 等
````````````````
| 屬性 / 方法 | 說明 |
| --- | --- |
| | |
| inputGeometry | BRepEdge(s) or sketch geometry |
| isOpen | Get/set if open contour should remain open |
| isOpenAllowed | Whether parent parameter allows open contours |
| isReverted | Get/set if curve direction is reverted |
| extensionMethod | Extension method to use |
| extensionType | Desired extension type |
| startExtensionLength | Extension length at start of open curve (cm) |
| endExtensionLength | Extension length at end of open curve (cm) |

## ④ FaceContourSelection

> [!NOTE]
> BRepFace 輪廓投影。適用於 Face、Pocket 2D、Adaptive 2D 等
````````
| 屬性 / 方法 | 說明 |
| --- | --- |
| | |
| inputGeometry | BRepFace object(s) |
| loopType | LoopTypes enum â AllLoops / OnlyOutsideLoops / OnlyInsideLoops |
| sideType | SideTypes enum â which side of loop to machine |
| isSelectingSamePlaneFaces | Auto-select all coplanar faces |

## ⑤ SilhouetteSelection

> [!NOTE]
> BRepBody 兩影輪廓。適用於外形ç¾層加工
``````````
| 屬性 / 方法 | 說明 |
| --- | --- |
| | |
| inputGeometry | BRepBody object(s) |
| loopType | LoopTypes enum |
| sideType | SideTypes enum |
| isSetupModelSelected | Include all setup model bodies |
| silhouetteTolerance | Distance silhouette can differ from model (cm) |

## ⑥ SketchSelection

> [!NOTE]
> Sketch 物件選取。適用於自定義園弧輪廓
``````
| 屬性 / 方法 | 說明 |
| --- | --- |
| | |
| inputGeometry | Sketch object(s) |
| loopType | LoopTypes enum |
| sideType | SideTypes enum |

## LoopTypes 枚舉
``````
| 常數 | 說明 |
| --- | --- |
| | |
| AllLoops | Inside and outside loops of selected geometry |
| OnlyOutsideLoops | Only outer contours (one per entity) |
| OnlyInsideLoops | Only inner contours (holes/pockets) |

## SideTypes 枚舉
````````
| 常數 | 說明 |
| --- | --- |
| | |
| AlwaysOutsideSideType | Always machine outside |
| AlwaysInsideSideType | Always machine inside |
| StartOutsideSideType | Order: outside â inside â outside â¦ |
| StartInsideSideType | Order: inside â outside â inside â¦ |

## ⑦ MachiningTime — 加工時間結果

> [!NOTE]
> cam.getMachiningTime(objects) 回傳此物件。全部屬性為 read-only
``````````````
| 屬性 / 方法 | 說明 |
| --- | --- |
| | |
| feedDistance | Total feed distance (cm) |
| totalFeedTime | Total feed time (seconds) |
| rapidDistance | Rapid traverse distance (cm) |
| totalRapidTime | Total rapid time (seconds) |
| toolChangeCount | Number of tool changes |
| totalToolChangeTime | Total tool change time (seconds) |
| machiningTime | Total machining time (seconds) |

```python
# 取得加工時間
ops = adsk.core.ObjectCollection.create()
ops.add(setup) # or specific operations
mt = cam.getMachiningTime(ops)
print("machining:", mt.machiningTime, "s")
print("feed dist:", round(mt.feedDistance * 10, 1), "mm")
print("tool changes:", mt.toolChangeCount)```



---


<a name="工具--toolpreset--setupgroup-api"></a>
## 📚 工具 / ToolPreset / SetupGroup API
Tool / Preset / SetupGroup API
# Tool / ToolPreset / SetupGroup API (adsk.cam)

> [!NOTE]
> 來源：Fusion API Documentation (live query)

## ① Tool — Properties

> [!NOTE]
> 工具物件。parameters 包含幾何ï¼diameter / length / flute count 等）。presets 包含材料切å參數。
``````
| 屬性 / 方法 | 說明 |
| --- | --- |
| | |
| parameters | CAMParameters collection for this tool (geometry, body type, etc.) |
| presets | ToolPresets collection â material-specific cutting parameters |
| description | Descriptive text about the tool |

## Tool — Static / Instance Methods
````````
| 屬性 / 方法 | 說明 |
| --- | --- |
| | |
| Tool.createFromJson(json) [static] | Create Tool object from JSON string |
| Tool.createFromP21(p21str) [static] | Create Tool from P21 format string |
| Tool.createFromP21File(path) [static] | Create Tool from P21 file |
| tool.toJson() | Serialize tool to JSON string |

## ② ToolPreset — Properties

> [!NOTE]
> 材料預設。parameters 包含è½é/èµ°åéç/åå±æ·±åº¦等材料ç¸éåæ¸。
``````
| 屬性 / 方法 | 說明 |
| --- | --- |
| | |
| name | Gets/sets preset name |
| id | Gets/sets preset identifier |
| parameters | CAMParameters for this preset (feeds, speeds, etc.) |

## ToolPresets 集合

> [!NOTE]
> tool.presets 取得
``````````
| 屬性 / 方法 | 說明 |
| --- | --- |
| | |
| count | Number of presets |
| item(index) | Get preset by index |
| itemsByName(name) | Search presets by name |
| add() | Create and insert new preset at end |
| remove(index) | Remove preset by index |

## ToolJointType 枚舉

> [!NOTE]
> 工具組件接點座標系型別
``````
| 常數 | 說明 |
| --- | --- |
| | |
| CuttingSideJoint | Attachment point on the cutting/tool side |
| MachineSideJoint | Attachment point on the machine side |
| ToolHolderJoint | Attachment point for the tool holder |

## ③ SetupGroup — Properties & Methods

> [!NOTE]
> 決定同時å 工ç Setup 集合ãcam.setupGroups 取得。
````````````````
| 屬性 / 方法 | 說明 |
| --- | --- |
| | |
| operationType | Gets Operation Type (OperationTypes enum) |
| count | Number of Setups in this group |
| item(index) | Returns Setup at index |
| addSetup(setup) | Adds an existing Setup to this group |
| removeSetup(setup) | Removes Setup from this group |
| deleteMe() | Deletes this SetupGroup |
| duplicate() | Duplicate after itself |
| moveBefore(op) / moveAfter(op) | Move in browser tree |

## SetupGroups 集合
``````````
| 屬性 / 方法 | 說明 |
| --- | --- |
| | |
| count | Number of SetupGroups |
| item(index) | Returns SetupGroup at index |
| itemByName(name) | Returns SetupGroup by name |
| itemByOperationId(id) | Returns SetupGroup by operation id |
| add() | Creates a new SetupGroup |

## 工具常用範例

```python
# 從 documentToolLibrary 取指定工具
lib = cam.documentToolLibrary
for i in range(lib.count):
 t = lib.item(i)
 name_p = t.parameters.itemByName('tool_description')
 dia_p = t.parameters.itemByName('tool_diameter')
 if name_p and dia_p:
 print(name_p.expression, dia_p.expression)

# 將工具指定給 operation
op_input.tool = lib.item(0)
op_input.toolPreset = lib.item(0).presets.item(0)

# 修改 Operation 上的工具
op.tool = new_tool

# 建立 SetupGroup
sg = cam.setupGroups.add()
sg.addSetup(setup1)
sg.addSetup(setup2)```



---


<a name="additive--export--printsetting-api"></a>
## 📚 Additive / Export / PrintSetting API
Additive / Export / PrintSetting API
# Additive / Export / PrintSetting API (adsk.cam)

> [!NOTE]
> 來源：Fusion API Documentation (live query)
⚠️ CAMExportManager 目前僅支持 Additive Setup 匯出
## ① CAMExportManager — Methods

> [!NOTE]
> cam.exportManager 取得
``````````````
| 屬性 / 方法 | 說明 |
| --- | --- |
| | |
| execute(exportOptions) | 按照 exportOptions 執行匯出 |
| executeWithExportFuture(exportOptions) | 执行匯出並回傳 Future 物件 |
| createFormlabsOptions(setup, outputPath) | 建立 Formlabs 匯出選項 |
| create3MFOptions(setup, outputPath) | 建立 3MF 匯出選項 |
| createCAMAdditiveBuildExportOptions(setup, outputPath) | 建立基於 PrintSetting 匯出格式的選項 |
| createAutodeskCLDExportOptions(setup, outputPath) | 建立 Autodesk CLD 匯出選項 |
| createPRMExportOptions(setup, outputPath) | 建立 PRM 匯出選項 |

## ② PrintSetting — Properties

> [!NOTE]
> 列印設定物件，用於 Additive Setup。setup.printSetting 取得。
``````````
| 屬性 / 方法 | 說明 |
| --- | --- |
| | |
| name | 名稱 |
| description | 說明 |
| technology | 技術類型 (FFF / SLS / MPBF 等) |
| id | 唯一識別碼 |
| count | PrintSettingItems 數量 |

## PrintSetting — Methods
``````````````````````
| 屬性 / 方法 | 說明 |
| --- | --- |
| | |
| parameters(type) | 回傳指定類型的 CAMParameters（PrintSettingItemTypes enum） |
| item(index) | 取得 PrintSettingItem at index |
| itemByName(name) | 取得指定名稱的 PrintSettingItem |
| duplicatePrintSettingItem(preset) | 複製 PrintSettingItem |
| deletePrintSettingItem(preset) | 删除 PrintSettingItem |
| setDefaultPrintSettingItem(preset) | 設定預設 PrintSettingItem |
| getDefaultPrintSettingItem() | 取得預設 PrintSettingItem |
| syncWithMachine(machine) | 同步 PrintSetting 與機器的鏠頭選項 |
| isCompatibleWithMachine(machine) | 檢查與機器的相容性 |
| toXML() | 序列化為 XML 內容字串 |
| PrintSetting.createFromXML(xml) [static] | 從 XML 建立 PrintSetting |

## PrintSettingItem

> [!NOTE]
> 對應一個 body preset 的設定項
``````
| 屬性 / 方法 | 說明 |
| --- | --- |
| | |
| name | body preset 名稱 |
| description | body preset 說明 |
| parameters | CAMParameters 用於讀取和編輯值 |

## PrintSettingItemTypes 枚舉
````
| 常數 | 說明 |
| --- | --- |
| | |
| GENERAL | 一般參數類型 |
| EXPORTER | 匯出器參數類型 |

## ③ PrintSettingQuery

> [!NOTE]
> 於 PrintSetting 庫中搜尋符合條件的 PrintSetting
````````````````````
| 屬性 / 方法 | 說明 |
| --- | --- |
| | |
| name | 名稱筛選（case-insensitive） |
| technology | 技術類型筛選 |
| vendor | 廠商筛選 |
| material | MPBF 材料筛選 |
| filamentDiameter | FFF 筆材直徑筛選 |
| layerHeight | 層厂高筛選 |
| url | 搜尋範圍 URL |
| location | LibraryLocations enum |
| machine | 機器相容性筛選 |
| execute() | 執行查詢回傳 PrintSetting 集合 |

## ④ CAMAdditiveContainerTypes 枚舉

> [!NOTE]
> setup.additiveContainerByType(type) 取得對應容器
````````
| 常數 | 說明 |
| --- | --- |
| | |
| SupportCAMAdditiveContainerType | 支撑結構工序的容器 |
| OptimizedOrientationCAMAdditiveContainerType | 最佳方位工序的容器 |
| BodyPresetCAMAdditiveContainerType | 所有 body presets 的容器（不可刪除） |
| AdditiveProcessSimulationCAMAdditiveContainerType | 製程仿真的容器（不可刪除） |

## ⑤ CAM3MFSupportInclusionType 枚舉

> [!NOTE]
> cam.export3MFForDefaultAdditiveSetup(path, supportType) 使用
``````
| 常數 | 說明 |
| --- | --- |
| | |
| NotIncluded | 不包含支撑結構 |
| IncludeAsSupportType | 包含為 3MF support object |
| IncludeAsModelType | 包含為 3MF model object |

## 常用範例

```python
# 取得 PrintSetting 並讀取參數
ps = setup.printSetting
gen_params = ps.parameters(adsk.cam.PrintSettingItemTypes.GENERAL)
for i in range(gen_params.count):
 p = gen_params.item(i)
 print(p.name, p.expression)

# 匯出 3MF
em = cam.exportManager
opts = em.create3MFOptions(setup, r'C:/output/model.3mf')
em.execute(opts)

# 取得支撑結構容器
support_con = setup.additiveContainerByType(
 adsk.cam.CAMAdditiveContainerTypes.SupportCAMAdditiveContainerType)```



---
