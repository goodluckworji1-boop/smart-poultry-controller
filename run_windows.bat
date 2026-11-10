@echo off
title Smart Poultry House Controller
cd /d "%~dp0"
echo Installing required Python packages (first run needs internet)...
python -m pip install -r requirements.txt
if not exist model\poultry_dnn.joblib (
  echo Training the deep neural network...
  python dnn_model.py
)
start "" http://127.0.0.1:5000
python app.py
pause
