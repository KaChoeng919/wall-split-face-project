# Wall Split Face Project

## 概述
這是Revit Dynamo Python腳本項目，用於自動處理模型中所有牆體：對每個側面識別相連房間，計算高度，並創建水平ModelCurve作為Split Face邊界。

## 安裝
1. 在Dynamo中開啟Revit模型。
2. 載入`main_script.py`作為自訂節點或直接運行。
3. 確保config.json存在並調整參數。

## 使用
- 在Dynamo中連接輸出到其他節點。
- 檢查LOG文件於config.json指定的路徑。

## 依賴
- Revit 2023
- Dynamo 2.16.2
- IronPython 2.7

## 貢獻
歡迎PR。
