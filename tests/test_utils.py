# test_utils.py: 單元測試（需mock Revit API）
import unittest
from utils import calculate_room_height  # 假設mock room

class MockRoom(object):
    def __init__(self, unbounded_height=0, base_offset=0, limit_offset=0, level_elev=0, upper_level_elev=10):
        self.UnboundedHeight = unbounded_height
        self.BaseOffset = base_offset
        self.LimitOffset = limit_offset
        self.Level = MockLevel(level_elev)
        self.UpperLimit = MockLevel(upper_level_elev)

class MockLevel(object):
    def __init__(self, elevation):
        self.Elevation = elevation

class TestUtils(unittest.TestCase):
    def test_calculate_room_height(self):
        room = MockRoom(unbounded_height=0, base_offset=1, limit_offset=2, level_elev=0, upper_level_elev=10)
        height = calculate_room_height(room)
        self.assertEqual(height, 11)  # (10 + 2) - (0 + 1) = 11

if __name__ == '__main__':
    unittest.main()
