# utils.py: 輔助函數模組
from Autodesk.Revit.DB import *

def get_side_faces(wall):
    options = Options()
    options.ComputeReferences = True
    options.IncludeNonVisibleObjects = True
    geometry = wall.get_Geometry(options)
    side_faces = []
    for geo_obj in geometry:
        if isinstance(geo_obj, Solid):
            for face in geo_obj.Faces:
                if abs(face.FaceNormal.Z) < 0.1:
                    side_faces.append(face)
    return side_faces

def get_adjacent_rooms(doc, face, offset_distance):
    normal = face.FaceNormal
    uv_center = UV(0.5, 0.5)
    center_point = face.Evaluate(uv_center)
    offset_vector_inside = normal.Multiply(-offset_distance)
    offset_vector_outside = normal.Multiply(offset_distance)
    sample_point_inside = center_point.Add(offset_vector_inside)
    sample_point_outside = center_point.Add(offset_vector_outside)
    rooms = []
    room_inside = doc.GetRoomAtPoint(sample_point_inside)
    if room_inside:
        rooms.append(room_inside)
    room_outside = doc.GetRoomAtPoint(sample_point_outside)
    if room_outside and room_outside != room_inside:
        rooms.append(room_outside)
    return rooms

def calculate_room_height(room):
    height = room.UnboundedHeight
    if height == 0:
        base_elev = room.Level.Elevation + room.BaseOffset
        upper_elev = room.UpperLimit.Elevation + room.LimitOffset
        height = upper_elev - base_elev
    return height

def calculate_split_height(wall, height):
    wall_base_constraint_id = wall.get_Parameter(BuiltInParameter.WALL_BASE_CONSTRAINT).AsElementId()
    wall_base_level = wall.Document.GetElement(wall_base_constraint_id)
    wall_base_offset = wall.get_Parameter(BuiltInParameter.WALL_BASE_OFFSET).AsDouble()
    return wall_base_level.Elevation + wall_base_offset + height

def create_model_curve_on_face(doc, face, split_height):
    sketch_plane = SketchPlane.Create(doc, face.Reference)
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
        line_start = XYZ(min_xyz.X, (min_xyz.Y + max_xyz.Y)/2, split_height)
        line_end = XYZ(max_xyz.X, (min_xyz.Y + max_xyz.Y)/2, split_height)
        line = Line.CreateBound(line_start, line_end)
        doc.Create.NewModelCurve(line, sketch_plane)
