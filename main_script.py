# main_script.py: 主腳本，用於Dynamo中運行Revit牆體面分割邏輯
import clr
clr.AddReference('RevitAPI')
clr.AddReference('RevitServices')
import RevitServices
from RevitServices.Persistence import DocumentManager
from RevitServices.Transactions import TransactionManager
from Autodesk.Revit.DB import *
from Autodesk.Revit.DB.Architecture import *

import os
import datetime
import json  # 用於載入配置

from utils import get_side_faces, get_adjacent_rooms, calculate_room_height, calculate_split_height, create_model_curve_on_face

doc = DocumentManager.Instance.CurrentDBDocument

# 載入配置
config_path = os.path.join(os.path.dirname(__file__), 'config.json')
with open(config_path, 'r') as f:
    config = json.load(f)
offset_distance = config['offset_distance']

# 輸出變數：成功和失敗記錄
success_log = []
failed_log = []

# 開始事務
TransactionManager.Instance.EnsureInTransaction(doc)

try:
    # 收集所有牆體
    wall_collector = FilteredElementCollector(doc).OfClass(Wall).WhereElementIsNotElementType()
    walls = wall_collector.ToElements()
    
    for wall in walls:
        try:
            side_faces = get_side_faces(wall)
            if not side_faces:
                failed_log.append("Wall ID {}: No side faces found.".format(wall.Id))
                continue
            
            success_log.append("Wall ID {}: Found {} side faces.".format(wall.Id, len(side_faces)))
            
            for face in side_faces:
                try:
                    rooms = get_adjacent_rooms(doc, face, offset_distance)
                    if not rooms:
                        failed_log.append("Wall ID {} Face: No adjacent rooms found at offset {}. Try increasing offset.".format(wall.Id, offset_distance))
                        continue
                    
                    for room in rooms:
                        try:
                            height = calculate_room_height(room)
                            split_height = calculate_split_height(wall, height)
                            create_model_curve_on_face(doc, face, split_height)
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

# 寫入LOG
log_path = config['log_path']
if not os.path.exists(log_path):
    os.makedirs(log_path)

timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

success_file = os.path.join(log_path, "success_log.txt")
with open(success_file, "w") as f:
    f.write("Run Time: {}\n".format(timestamp))
    for entry in success_log:
        f.write(entry + "\n")

failed_file = os.path.join(log_path, "failed_log.txt")
with open(failed_file, "w") as f:
    f.write("Run Time: {}\n".format(timestamp))
    for entry in failed_log:
        f.write(entry + "\n")

# Dynamo輸出
OUT = success_log, failed_log
