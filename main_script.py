# 模組：自動分割 Revit 牆體面基於相連房間高度
# 版本：1.7
# 作者：Kenneth Law
# 描述：遍歷所有牆體，對於每個垂直面，找相連房間，從房間的 "Headroom Requirement" 參數獲取高度（Text 轉 float，假設 mm 轉 ft），並分割面從底部到該高度。
# 依賴：Revit 2023, Dynamo 2.16.2, IronPython
# 注意：需在 Dynamo 中運行；測試於樣本模型。日誌將寫入指定路徑。優化輪廓創建以避免短曲線錯誤。

import clr
import sys
import math
import os  # 用於處理檔案路徑和目錄檢查

# 導入 Revit API 和 Dynamo 模組
clr.AddReference('ProtoGeometry')
from Autodesk.DesignScript.Geometry import *

clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')
from Autodesk.Revit.DB import *
from Autodesk.Revit.DB.Architecture import Room

clr.AddReference('RevitNodes')
import Revit
clr.ImportExtensions(Revit.Elements)
clr.ImportExtensions(Revit.GeometryConversion)

clr.AddReference('RevitServices')
import RevitServices
from RevitServices.Persistence import DocumentManager
from RevitServices.Transactions import TransactionManager

# 獲取當前文檔和應用程式
doc = DocumentManager.Instance.CurrentDBDocument
uidoc = DocumentManager.Instance.CurrentUIApplication.ActiveUIDocument
app = DocumentManager.Instance.CurrentUIApplication.Application

# 定義常量
EPSILONS = [0.01, 0.1, 0.5, 1.0]  # 多偏移嘗試以改善房間偵測
MM_TO_FEET = 1 / 304.8  # 毫米到英尺轉換因子 (Revit 內部單位為 ft)
TOLERANCE = app.ShortCurveTolerance * 1.01  # 短曲線容差（稍大以安全）
logs = []  # 日誌列表：成功/失敗記錄
log_dir = r"D:\Users\User\Desktop\test\Wall Split Face"  # 指定 LOG 目錄
log_file_name = "log.txt"  # 指定檔案名
log_path = os.path.join(log_dir, log_file_name)  # 完整路徑

# 獲取最後階段
phase = doc.Phases.get_Item(doc.Phases.Size - 1) if doc.Phases.Size > 0 else None

def get_vertical_faces(wall):
    """獲取牆體的垂直平面面"""
    options = Options()
    options.ComputeReferences = True
    options.IncludeNonVisibleObjects = True
    geo_elem = wall.get_Geometry(options)
    faces = []
    for geo in geo_elem:
        if isinstance(geo, Solid):
            for face in geo.Faces:
                if isinstance(face, PlanarFace) and math.fabs(face.FaceNormal.DotProduct(XYZ.BasisZ)) < 0.01:  # 垂直面（法線非Z軸）
                    faces.append(face)
    return faces

def get_adjacent_room(face):
    """找相連房間：從面點沿法線偏移，獲取房間（多偏移嘗試和 phase 指定）"""
    uv = UV(0.5, 0.5)  # 面中心UV
    point_on_face = face.Evaluate(uv)  # 獲取點
    normal = face.FaceNormal  # 獲取法線
    for eps in EPSILONS:
        # 正方向偏移
        offset_vector = normal.Multiply(eps)
        offset_point = point_on_face.Add(offset_vector)
        room = doc.GetRoomAtPoint(offset_point, phase)
        if room:
            return room
        # 負方向偏移
        offset_vector_rev = normal.Multiply(-eps)
        offset_point_rev = point_on_face.Add(offset_vector_rev)
        room_rev = doc.GetRoomAtPoint(offset_point_rev, phase)
        if room_rev:
            return room_rev
    # 如果皆無，記錄最後點
    logs.append("Debug: No room at point {} with offsets {} or negatives.".format(point_on_face, EPSILONS))
    return None

def calculate_room_height(room):
    """從房間的 'Headroom Requirement' 參數（Text, Instance）計算高度（轉 ft）"""
    if room:
        param = room.LookupParameter("Headroom Requirement")  # 查找參數
        if param and param.StorageType == StorageType.String:
            value = param.AsString()
            try:
                height_mm = float(value)  # 轉換 Text 為 float (假設 mm)
                height_ft = height_mm * MM_TO_FEET  # 轉內部單位 ft
                return height_ft
            except ValueError:
                logs.append("Invalid height value '{}' for room {}".format(value if value else "None", room.Id))
                return None
        else:
            logs.append("Parameter 'Headroom Requirement' not found or invalid for room {}".format(room.Id))
    return None

def create_split_profile(face, height):
    """創建 CurveLoop 輪廓：從底部邊偏移到高度（處理短曲線和非矩形）"""
    try:
        # 獲取面邊界邊
        edge_loop = face.EdgeLoops.get_Item(0)  # 假設單一閉合邊界
        curves = [edge.AsCurve() for edge in edge_loop]
        
        # 計算 min/max Z
        all_points = [p for curve in curves for p in [curve.GetEndPoint(0), curve.GetEndPoint(1)]]
        min_z = min(p.Z for p in all_points)
        max_z = max(p.Z for p in all_points)
        wall_height = max_z - min_z
        
        if height >= wall_height or height <= 0:
            logs.append("Invalid profile: Height {} ft exceeds or equals wall height {} ft.".format(height, wall_height))
            return None
        
        new_height_z = min_z + height
        
        # 識別底部曲線：Z 接近 min_z 的邊
        bottom_curves = []
        for curve in curves:
            p1, p2 = curve.GetEndPoint(0), curve.GetEndPoint(1)
            if abs(p1.Z - min_z) < TOLERANCE and abs(p2.Z - min_z) < TOLERANCE:
                bottom_curves.append(curve.Clone())  # 複製底部曲線
        
        if not bottom_curves:
            logs.append("Invalid profile: No bottom curves found.")
            return None
        
        # 創建頂曲線：偏移底部曲線到 new_height_z
        top_curves = []
        for curve in bottom_curves:
            p1, p2 = curve.GetEndPoint(0), curve.GetEndPoint(1)
            new_p1 = XYZ(p1.X, p1.Y, new_height_z)
            new_p2 = XYZ(p2.X, p2.Y, new_height_z)
            dist = p1.DistanceTo(p2)
            if dist < TOLERANCE:
                logs.append("Skipping short bottom/top curve: Distance {} ft < tolerance.".format(dist))
                continue
            top_curve = Line.CreateBound(new_p1, new_p2) if isinstance(curve, Line) else curve.CreateTransformed(Transform.CreateTranslation(XYZ(0, 0, height)))
            top_curves.append(top_curve)
        
        if not top_curves:
            logs.append("Invalid profile: No valid top curves created.")
            return None
        
        # 連接垂直線：底部端點到頂部對應端點
        vertical_lines = []
        bottom_endpoints = [c.GetEndPoint(0) for c in bottom_curves] + [bottom_curves[-1].GetEndPoint(1)]  # 閉合
        top_endpoints = [c.GetEndPoint(0) for c in top_curves] + [top_curves[-1].GetEndPoint(1)]
        for i in range(len(bottom_endpoints) - 1):  # 避免最後閉合
            p_bottom = bottom_endpoints[i]
            p_top = top_endpoints[i]
            dist = p_bottom.DistanceTo(p_top)
            if dist < TOLERANCE:
                logs.append("Skipping short vertical line: Distance {} ft < tolerance.".format(dist))
                continue
            vertical = Line.CreateBound(p_bottom, p_top)
            vertical_lines.append(vertical)
        
        # 組裝 CurveLoop：底部 + 垂直 + 頂部反向 + 垂直反向（確保閉合方向）
        profile = CurveLoop()
        for c in bottom_curves:
            profile.Append(c)
        for v in vertical_lines[::-1]:  # 反向以閉合
            profile.Append(v)
        for t in top_curves[::-1]:  # 反向頂部
            profile.Append(t)
        for v in vertical_lines:
            profile.Append(v)
        
        # 驗證 CurveLoop
        if not profile.IsClosed() or not profile.IsPlanar():
            logs.append("Invalid CurveLoop: Not closed or planar.")
            return None
        
        return profile
    except Exception as e:
        logs.append("Error creating profile: {}".format(str(e)))
        return None

# 主邏輯
TransactionManager.Instance.EnsureInTransaction(doc)

walls = FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Walls).WhereElementIsNotElementType().ToElements()

for wall in walls:
    try:
        faces = get_vertical_faces(wall)
        for face in faces:
            room = get_adjacent_room(face)
            if not room:
                logs.append("Wall {} Face: No adjacent room found.".format(wall.Id))
                continue
            
            height = calculate_room_height(room)
            if not height:
                logs.append("Wall {} Face: Invalid room height from 'Headroom Requirement'.".format(wall.Id))
                continue
            
            profile = create_split_profile(face, height)
            if not profile:
                logs.append("Wall {} Face: Invalid profile for height {}.".format(wall.Id, height))
                continue
            
            new_face = doc.SplitFace(face, profile)
            logs.append("Wall {} Face split successfully at height {}. New face ID: {}".format(wall.Id, height, new_face.Id))
    
    except Exception as e:
        logs.append("Error on Wall {}: {}".format(wall.Id, str(e)))

TransactionManager.Instance.TransactionTaskDone()

# 更新：檢查並創建目錄，寫入日誌到檔案
try:
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)  # 創建目錄如果不存在
    with open(log_path, 'w') as log_file:
        for log in logs:
            log_file.write(log + '\n')
    logs.append("Logs successfully written to {}".format(log_path))
except Exception as e:
    logs.append("Error writing logs: {}".format(str(e)))

# 輸出日誌（Dynamo OUT 仍保留，便於即時檢查）
OUT = logs
