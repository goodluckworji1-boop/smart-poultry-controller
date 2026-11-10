# Improved IoT-Based Smart Poultry House Controller

Python (Flask) backend, deep neural network (multilayer perceptron), MySQL
database and an HTML/CSS/JavaScript dashboard. An ESP32 sensor node (DHT22,
MQ-135, LDR, ultrasonic sensor, 4-channel relay) sends readings as JSON; a
built-in simulator stands in for the hardware during the presentation.

## Quickest: open index.html (no installation, no internet)
Double-click index.html. It opens in the browser and runs the complete
system: login, dashboard, DNN, simulator, alerts, logs, users and model
performance. The trained neural network is built into the page in
JavaScript, and data is kept in the browser's local storage.
Default login: admin / admin123.

The same file runs online through GitHub Pages:
Settings > Pages > Source: Deploy from a branch > Branch: main, folder / (root) > Save.
The site appears at https://<username>.github.io/smart-poultry-controller/

The Python/MySQL version below is the full system, including the
/api/sensor endpoint that the real ESP32 posts to.

## 0. Run online with GitHub Codespaces (nothing to install on the laptop)
1. Open this repository on github.com and sign in.
2. Click the green **Code** button, open the **Codespaces** tab, then
   **Create codespace on main**.
3. Wait 2 to 3 minutes the first time while the libraries install.
   The app starts by itself and the dashboard opens in a new browser tab.
   If it does not open, go to the **Ports** tab and click the globe icon
   beside port 5000.
4. Log in with admin / admin123.
When finished, stop the codespace (Code > Codespaces > ... > Stop) so it
does not use up the free monthly hours. Codespaces needs internet.

## 1. Install on a laptop (once, needs internet)
1. Install Python 3.10 or newer from python.org (tick "Add Python to PATH").
2. Open Command Prompt in this folder and run:
   pip install -r requirements.txt

## 2. Run
Double-click run_windows.bat, or run:
   python dnn_model.py    (trains the DNN; only needed once)
   python app.py
Open http://127.0.0.1:5000 and log in with admin / admin123.

## 3. Use MySQL (as stated in the dissertation)
1. Start XAMPP and click Start beside MySQL.
2. In config.py set DB_ENGINE = "mysql" (password is empty on XAMPP by default).
3. Run python app.py. The database smart_poultry_db and its tables are
   created automatically and can be shown in phpMyAdmin.

## 4. Project files
- app.py: web server, routes, sensor API, control loop, simulator
- dnn_model.py: dataset generation, DNN training, evaluation, prediction
- control.py: converts DNN output into fan/heater/feeder/light commands and alerts
- db.py: MySQL / SQLite storage (users, sensor_logs, alerts)
- esp32_simulator.py: sends JSON packets to /api/sensor like the real ESP32
- esp32_firmware/esp32_poultry_node.ino: Arduino code for the real ESP32 node
- dataset/poultry_environment_dataset.csv: the 8,000-record training dataset
- model/metrics.json: accuracy, precision, recall, F1, confusion matrix

## 5. Suggested defense demonstration (about 6 minutes)
1. Login: show authentication (security design).
2. Users: register a staff member using the user input form.
3. Dashboard: click "Start sensor simulation". Readings arrive every 3 s,
   the DNN classifies the house state and the relays switch automatically.
4. DNN advantage: in "Test the controller", enter 27.5 C, 90% humidity, day 21.
   The temperature is inside the comfort zone, yet the DNN predicts Heat Stress
   because high humidity stops panting. A fixed-threshold controller would do nothing.
5. Ammonia priority: enter 22 C, 60%, ammonia 30 ppm. Ventilation and heater
   switch on together.
6. Manual override: switch to manual and toggle the fan.
7. Alerts: open Alerts and escalate one.
8. Sensor logs: show stored records, filter Critical, export CSV.
9. Model performance: accuracy, per-class results, confusion matrix, loss curve.
10. Optional: run python esp32_simulator.py in a second window to show data
    arriving through the JSON API exactly as from the ESP32.

## 6. Connecting the real ESP32
Open the .ino file in Arduino IDE, install the ESP32 board package,
"DHT sensor library" and "ArduinoJson". Enter the Wi-Fi name/password and the
laptop's IP address (from ipconfig), then upload. Laptop and ESP32 must be on
the same Wi-Fi network.

## 7. Reproducing the Chapter Four results
   python -m unittest -v tests/test_system.py   (17 software test cases)
   python evaluate_system.py                    (response time, data integrity,
                                                  stability comparison -> model/evaluation.json)
Accuracy figures are in model/metrics.json and on the Model performance page.
