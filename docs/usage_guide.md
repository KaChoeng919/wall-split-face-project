# 使用指南

## 腳本邏輯
1. 收集牆體。
2. 提取側面。
3. 找相連房間（使用偏移點）。
4. 計算高度。
5. 創建ModelCurve於高度處。

## 範例
在Dynamo中運行`main_script.py`，輸出LOG顯示結果。

## 錯誤排除
- 無房間：增大offset_distance。
- 曲線失敗：檢查面幾何。
