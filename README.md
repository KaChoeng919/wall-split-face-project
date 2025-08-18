# Revit Wall Face Splitter

## 目的
這個 Python 腳本在 Dynamo 中自動化 Revit 模型的牆體面分割：基於相連房間高度，從底部分割出區域。適合建築自動化，如材料應用。

## 安裝
- Revit 2023 和 Dynamo 2.16.2。
- 在 Dynamo 中創建 Python Script 節點，貼上腳本。
- 無額外依賴；使用標準 Revit API。

## 使用指示
1. 打開 Revit 模型。
2. 在 Dynamo 中載入腳本。
3. 運行；輸出日誌顯示結果。
4. 測試於簡單模型，避免複雜幾何。

## 依賴項
- Autodesk.Revit.DB
- RevitServices

貢獻歡迎！報告問題於 Issues。
