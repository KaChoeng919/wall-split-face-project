# 模組：自動分割 Revit 牆體面基於相連房間高度
# 版本：1.8
# 作者：Kenneth Law
# 描述：遍歷所有牆體，對於每個垂直面，找相連房間，從房間的 "Headroom Requirement" 參數獲取高度（Text 轉 float，mm 轉 ft），並分割面從底部到該高度。
# 依賴：Revit 2023, Dynamo 2.16.2, IronPython
# 注意：需在 Dynamo 中運行；測試於樣本模型。日誌將寫入指定路徑。優化 CurveLoop 以確保連續閉合，避免不連續錯誤。

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
                height_mm = float(value)  # 轉換 Text 為 float (mm)
                height_ft = height_mm * MM_TO_FEET  # 轉內部單位 ft
                return height_ft
            except ValueError:
                logs.append("Invalid height value '{}' for room {}".format(value if value else "None", room.Id))
                return None
        else:
            logs.append("Parameter 'Headroom Requirement' not found or invalid for room {}".format(room.Id))
    return None

def create_split_profile(face, height):
    """創建 CurveLoop 輪廓：從底部邊偏移到高度（處理短曲線和連續性）"""
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
        bottom_loop = CurveLoop()
        for curve in curves:
            p1, p2 = curve.GetEndPoint(0), curve.GetEndPoint(1)
            if abs(p1.Z - min_z) < TOLERANCE and abs(p2.Z - min_z) < TOLERANCE:
                dist = p1.DistanceTo(p2)
                if dist < TOLERANCE:
                    logs.append("Skipping short bottom curve: Distance {} ft < tolerance.".format(dist))
                    continue
                bottom_loop.Append(curve.Clone())
        
        if bottom_loop.NumberOfCurves() == 0:
            logs.append("Invalid profile: No valid bottom curves found.")
            return None
        
        # 創建頂部 CurveLoop：偏移底部到 new_height_z
        offset_transform = Transform.CreateTranslation(XYZ(0, 0, height))
        top_loop = CurveLoop.CreateViaTransform(bottom_loop, offset_transform)
        
        # 連接垂直線：底部端點到頂部
        bottom_curves = list(bottom_loop)
        top_curves = list(top_loop)
        vertical_lines = []
        for i in range(len(bottom_curves)):
            p_bottom_start = bottom_curves[i].GetEndPoint(0)
            p_top_start = top_curves[i].GetEndPoint(0)
            dist_start = p_bottom_start.DistanceTo(p_top_start)
            if dist_start >= TOLERANCE:
                vertical_start = Line.CreateBound(p_bottom_start, p_top_start)
                vertical_lines.append(vertical_start)
            else:
                logs.append("Skipping short vertical start: Distance {} ft < tolerance.".format(dist_start))
            
            p_bottom_end = bottom_curves[i].GetEndPoint(1)
            p_top_end = top_curves[i].GetEndPoint(1)
            dist_end = p_bottom_end.DistanceTo(p_top_end)
            if dist_end >= TOLERANCE:
                vertical_end = Line.CreateBound(p_bottom_end, p_top_end)
                vertical_lines.append(vertical_end)
            else:
                logs.append("Skipping short vertical end: Distance {} ft < tolerance.".format(dist_end))
        
        # 組裝最終 CurveLoop：底部 + 垂直 + 頂部反轉 + 垂直反轉
        profile = CurveLoop()
        for c in bottom_curves:
            profile.Append(c)
        for v in vertical_lines:
            profile.Append(v)
        for t in reversed(top_curves):  # 反轉頂部方向以閉合
            profile.Append(t.CreateReversed())
        for v in reversed(vertical_lines):  # 反轉垂直以閉合
            profile.Append(v.CreateReversed())
        
        # 驗證連續性和閉合
        if not profile.IsClosed() or not profile.IsPlanar():
            logs.append("Invalid CurveLoop: Not closed or planar. Endpoints may not connect.")
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
