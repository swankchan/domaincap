# 1. 使用 Playwright 官方提供的 Python 環境（已內建所有瀏覽器所需的系統依賴）
FROM mcr.microsoft.com/playwright/python:v1.58.0-jammy

# 2. 設定容器內的工作目錄
WORKDIR /app

# 3. 複製 Python 依賴清單並安裝
# 建議先建立 requirements.txt，內容包含 flask, playwright 等
COPY requirements.txt .
RUN pip install -r requirements.txt
RUN python -m playwright install chromium firefox webkit

# 4. 複製專案的所有原始碼到容器中
COPY . .

# 5. 建立用於儲存截圖的資料夾（對應 app.py 中的 UPLOAD_FOLDER）
RUN mkdir -p screenshots

# 6. 開放 Flask 運作的 Port (與 app.py 的 port 5001 一致)
EXPOSE 5001

# 7. 設定環境變數，確保 Python 輸出能即時顯示在 Docker 紀錄中
ENV PYTHONUNBUFFERED=1

# 8. 啟動 Flask 應用程式
CMD ["python", "app.py"]