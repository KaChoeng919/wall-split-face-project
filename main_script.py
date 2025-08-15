# 導入必要模組
import clr
clr.AddReference('RevitAPI')
clr.AddReference('RevitServices')
import RevitServices
from RevitServices.Persistence import DocumentManager
from RevitServices.Transactions import TransactionManager
from Autodesk.Revit.DB import *
from Autodesk.Revit.DB.Architecture import *
from System.Collections.Generic import List  # 用於ICollection

# 額外導入用於檔案操作和目錄創建
import os
import datetime

doc = DocumentManager.Instance.CurrentDBDocument

# 輸出變數：成功和失敗記錄
success_log = []
failed_log = []

# 開始事務（所有修改需在事務內）
TransactionManager.Instance.EnsureInTransaction(doc)

try:
    # 收集所有牆體（排除幕牆等非標準）
    wall_collector = FilteredElementCollector(doc).OfClass(Wall).WhereElementIsNotElementType()
    walls = wall_collector.ToElements()
    
    for wall in walls:
        try:
            # 獲取牆體的側面（排除頂/底面）
            options = Options()
            options.ComputeReferences = True
            options.IncludeNonVisibleObjects = True
            geometry = wall.get_Geometry(options)
            
            side_faces = []
            for geo_obj in geometry:
                if isinstance(geo_obj, Solid):
                    for face in geo_obj.Faces:
                        # 檢查面法線是否接近水平（側面通常垂直，法線接近水平）
                        if abs(face.FaceNormal.Z) < 0.1:  # 調整閾值以過濾垂直側面
                            side_faces.append(face)
            
            if not side_faces:
                failed_log.append("Wall ID {}: No side faces found.".format(wall.Id))
                continue
            
            # 記錄找到的面數以追蹤
            success_log.append("Wall ID {}: Found {} side faces.".format(wall.Id, len(side_faces)))
            
            for face in side_faces:
                try:
                    # 找相連房間：從面中心偏移小距離，獲取點處房間
                    normal = face.FaceNormal
                    uv_center = UV(0.5, 0.5)
                    center_point = face.Evaluate(uv_center)
                    offset_distance = 0.1  # 英呎，小偏移避免邊界問題；如果仍無房間，試增大到0.5
                    # 使用 Multiply 方法避免運算符錯誤
                    offset_vector_inside = normal.Multiply(-offset_distance)
                    offset_vector_outside = normal.Multiply(offset_distance)
                    sample_point_inside = center_point.Add(offset_vector_inside)
                    sample_point_outside = center_point.Add(offset_vector_outside)
                    
                    # 檢查兩側
                    rooms = []
                    room_inside = doc.GetRoomAtPoint(sample_point_inside)
                    if room_inside:
                        rooms.append(room_inside)
                    room_outside = doc.GetRoomAtPoint(sample_point_outside)
                    if room_outside and room_outside != room_inside:
                        rooms.append(room_outside)
                    
                    if not rooms:
                        failed_log.append("Wall ID {} Face: No adjacent rooms found at offset {}. Try increasing offset.".format(wall.Id, offset_distance))
                        continue
                    
                    for room in rooms:
                        try:
                            # 獲取房間高度（UnboundedHeight若為0，則計算上下限）
                            height = room.UnboundedHeight
                            if height == 0:
                                base_elev = room.Level.Elevation + room.BaseOffset
                                upper_elev = room.UpperLimit.Elevation + room.LimitOffset
                                height = upper_elev - base_elev
                            
                            # 計算分割高度（相對於牆基底，包括偏移）
                            wall_base_constraint_id = wall.get_Parameter(BuiltInParameter.WALL_BASE_CONSTRAINT).AsElementId()
                            wall_base_level = doc.GetElement(wall_base_constraint_id)
                            wall_base_offset = wall.get_Parameter(BuiltInParameter.WALL_BASE_OFFSET).AsDouble()
                            split_height = wall_base_level.Elevation + wall_base_offset + height
                            
                            # 創建 SketchPlane on Face
                            sketch_plane = SketchPlane.Create(doc, face.Reference)
                            
                            # 定義水平線：從面邊界找 min/max，簡化為矩形假設
                            boundary_loops = face.GetEdgesAsCurveLoops()
                            if boundary_loops:
                                min_xyz = XYZ(float('inf'), float('inf'), float('inf'))
                                max_xyz = XYZ(float('-inf'), float('-inf'), float('-inf'))
                                for loop in boundary_loops:
                                    for curve in loop:
                                        start = curve.GetEndPoint(0)
                                        end = curve.GetEndPoint(1)
                                        min_xyz = XYZ(min(min_xyz.X, start.X, end.X), min(min_xyz.Y, start.Y, end.Y), min(min_xyz.Z, start.Z, end.Z))
                                        max_xyz = XYZ(max(max_xyz.X, start.X, end.X), max(max_xyz.Y, start.Y, end.Y), max(max_xyz.Z, start.Z, end.Z))
                                
                                # 創建水平線：假設X為寬度，Y為深度，Z為高度；調整為水平（固定Z）
                                line_start = XYZ(min_xyz.X, (min_xyz.Y + max_xyz.Y)/2, split_height)  # 中Y以居中
                                line_end = XYZ(max_xyz.X, (min_xyz.Y + max_xyz.Y)/2, split_height)
                                line = Line.CreateBound(line_start, line_end)
                                
                                # 創建 ModelCurve
                                model_curve = doc.Create.NewModelCurve(line, sketch_plane)
                                
                                # 記錄成功
                                success_log.append("Wall ID {} Face adjacent to Room '{}': Height = {}, Model Curve created at height {}.".format(wall.Id, room.Name, height, split_height))
                            
                        except Exception as room_ex:
                            failed_log.append("Wall ID {} Room '{}': Error getting height or creating curve - {}".format(wall.Id, room.Name, str(room_ex)))
                
                except Exception as face_ex:
                    failed_log.append("Wall ID {} Face: Error processing face - {}".format(wall.Id, str(face_ex)))
        
        except Exception as wall_ex:
            failed_log.append("Wall ID {}: Error processing wall - {}".format(wall.Id, str(wall_ex)))

except Exception as global_ex:
    failed_log.append("Global error: {}".format(str(global_ex)))

TransactionManager.Instance.TransactionTaskDone()

# 加入 LOG 輸出到指定路徑
log_path = r"D:\Users\User\Desktop\test\Wall Split Face"
if not os.path.exists(log_path):
    os.makedirs(log_path)

timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# 寫入 success_log.txt
success_file = os.path.join(log_path, "success_log.txt")
with open(success_file, "w") as f:
    f.write("Run Time: {}\n".format(timestamp))
    for entry in success_log:
        f.write(entry + "\n")

# 寫入 failed_log.txt
failed_file = os.path.join(log_path, "failed_log.txt")
with open(failed_file, "w") as f:
    f.write("Run Time: {}\n".format(timestamp))
    for entry in failed_log:
        f.write(entry + "\n")

# 輸出到Dynamo: [成功日誌, 失敗日誌]
OUT = success_log, failed_log
