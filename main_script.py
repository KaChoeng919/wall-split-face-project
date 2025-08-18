# 模組：自動分割 Revit 牆體面基於相連房間高度
# 版本：1.4
# 作者：Kenneth Law
# 描述：遍歷所有牆體，對於每個垂直面，找相連房間，從房間的 "Headroom Requirement" 參數獲取高度（Text 轉 float），並分割面從底部到該高度。
# 依賴：Revit 2023, Dynamo 2.16.2, IronPython
# 注意：需在 Dynamo 中運行；測試於樣本模型。日誌將寫入指定路徑。增加 EPSILON 以改善房間偵測。

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

# 獲取當前文檔
doc = DocumentManager.Instance.CurrentDBDocument
uidoc = DocumentManager.Instance.CurrentUIApplication.ActiveUIDocument

# 定義常量
EPSILON = 0.1  # 更新：增加偏移用於找房間（單位依項目，通常英尺）
logs = []  # 日誌列表：成功/失敗記錄
log_dir = r"D:\Users\User\Desktop\test\Wall Split Face"  # 指定 LOG 目錄
log_file_name = "log.txt"  # 指定檔案名
log_path = os.path.join(log_dir, log_file_name)  # 完整路徑

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
    """找相連房間：從面點沿法線偏移，獲取房間"""
    uv = UV(0.5, 0.5)  # 面中心UV
    point_on_face = face.Evaluate(uv)  # 獲取點
    normal = face.FaceNormal  # 獲取法線
    # 偏移到房間側（法線指向外，偏移正方向進入房間）
    offset_vector = normal.Multiply(EPSILON)
    offset_point = point_on_face.Add(offset_vector)
    room = doc.GetRoomAtPoint(offset_point)
    if room:
        return room
    # 如果無，試反方向（視牆方向）
    offset_vector_rev = normal.Multiply(-EPSILON)
    offset_point_rev = point_on_face.Add(offset_vector_rev)
    room_rev = doc.GetRoomAtPoint(offset_point_rev)
    if not room_rev:
        # 更新：添加詳細日誌以除錯
        logs.append("Debug: No room at point {} with offset {} or -{}".format(point_on_face, EPSILON, EPSILON))
    return room_rev

def calculate_room_height(room):
    """從房間的 'Headroom Requirement' 參數（Text, Instance）計算高度"""
    if room:
        param = room.LookupParameter("Headroom Requirement")  # 查找參數
        if param and param.StorageType == StorageType.String:
            value = param.AsString()
            try:
                height = float(value)  # 轉換 Text 為 float
                return height
            except ValueError:
                # 更新：記錄實際值以診斷
                logs.append("Invalid height value '{}' for room {}".format(value if value else "None", room.Id))
                return None
        else:
            logs.append("Parameter 'Headroom Requirement' not found or invalid for room {}".format(room.Id))
    return None

def create_split_profile(face, height):
    """創建 CurveLoop 輪廓：從底部到高度的矩形（簡化假設矩形面）"""
    # 獲取面邊界邊
    edge_loop = face.EdgeLoops.get_Item(0)  # 假設單一閉合邊界
    curves = [edge.AsCurve() for edge in edge_loop]
    
    # 找最小/最大 Z，假設垂直矩形
    min_z = min(curve.GetEndPoint(0).Z for curve in curves)
    max_z = max(curve.GetEndPoint(0).Z for curve in curves)
    
    if height >= (max_z - min_z) or height <= 0:
        return None  # 無效高度
    
    new_height_z = min_z + height
    
    # 創建新輪廓：底部線、左右垂直、頂部水平（需調整點）
    points = [curve.GetEndPoint(0) for curve in curves] + [curves[0].GetEndPoint(0)]  # 閉合點
    bottom_left = min(points, key=lambda p: p.X + p.Y)  # 簡化查找角點
    bottom_right = max(points, key=lambda p: p.X - p.Y)
    top_left = min(points, key=lambda p: -p.X + p.Y)
    top_right = max(points, key=lambda p: p.X + p.Y)
    
    # 調整頂點到新高度
    new_top_left = XYZ(top_left.X, top_left.Y, new_height_z)
    new_top_right = XYZ(top_right.X, top_right.Y, new_height_z)
    
    # 創建曲線
    bottom = Line.CreateBound(bottom_left, bottom_right)
    left = Line.CreateBound(bottom_left, new_top_left)
    top = Line.CreateBound(new_top_left, new_top_right)
    right = Line.CreateBound(new_top_right, bottom_right)
    
    profile = CurveLoop()
    profile.Append(bottom)
    profile.Append(right)
    profile.Append(top)
    profile.Append(left)
    return profile

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
