# DivePlanner API

## 📌 Overview
DivePlanner is a Flask-based API designed to assist with dive planning by simulating depth, time at depth, no-decompression limits (NDL), decompression stops, and gas mixture calculations. It includes models like **Bühlmann ZH-L16** and **RGBM** for dive calculations.

## 🚀 Features
- **Dive Simulation**: Track depth, pressure, NDL, and RGBM factors.
- **Dive Logging**: Store and retrieve dive logs.
- **Decompression Stops Calculation**: Generate decompression stops when needed.
- **Gas Mixture Customization**: Modify oxygen, nitrogen, and helium fractions.
- **Oxygen Toxicity Analysis**: Calculate Partial Pressure of Oxygen (PPO₂) and risk levels.
- **Dynamic Dive State**: Update time at depth and RGBM factor automatically.
- **Customizable Decompression Models**: Support for Bühlmann, RGBM, VPM, and more.
- **Web-Based Interface**: Interactive frontend for visualization and control.

---

## 📦 Installation
### 1️⃣ Clone the Repository
```bash
git clone https://github.com/your-repo/diveplanner.git
cd diveplanner
```

### 2️⃣ Set Up Virtual Environment
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows use: venv\Scripts\activate
```

### 3️⃣ Install Dependencies
```bash
pip install -r requirements.txt
```

---

## 🔥 Usage
### 1️⃣ Run the API
```bash
python app.py
```
By default, the API runs on **http://127.0.0.1:5000/**

### 2️⃣ Open the Web Interface
Navigate to:
```
http://127.0.0.1:5000/
```
The **frontend** provides an interactive UI for:
- Visualizing depth, NDL, and oxygen toxicity.
- Switching gas mixtures.
- Logging and reviewing dive data.
- Switching decompression models.

### 3️⃣ Test API with Curl or Postman
#### Get Dive State:
```bash
curl -X GET http://127.0.0.1:5000/state
```
#### Start a Dive:
```bash
curl -X POST http://127.0.0.1:5000/dive -H "Client-UUID: 12345"
```
#### Ascend:
```bash
curl -X POST http://127.0.0.1:5000/ascend -H "Client-UUID: 12345"
```
#### Retrieve Logs:
```bash
curl -X GET http://127.0.0.1:5000/logs -H "Client-UUID: 12345"
```
#### Update Gas Mixture:
```bash
curl -X POST http://127.0.0.1:5000/update_gas_mix -H "Content-Type: application/json" -d '{
    "oxygen_fraction": 0.32,
    "nitrogen_fraction": 0.68,
    "helium_fraction": 0.0
}'
```

---

## 🌊 API Endpoints
| Method | Endpoint | Description |
|--------|----------------------|------------------------------|
| `GET` | `/state` | Get the current dive state |
| `POST` | `/dive` | Simulate a dive descent |
| `POST` | `/ascend` | Simulate an ascent |
| `GET` | `/logs` | Retrieve dive logs |
| `POST` | `/calculate_ndl_stops` | Calculate decompression stops |
| `POST` | `/update_gas_mix` | Modify oxygen/nitrogen/helium levels |
| `POST` | `/set-deco-model` | Change decompression model |
| `POST` | `/reset` | Reset dive simulation |

---

## 🌍 Web Interface Features
The frontend (`diveplanner.html`) provides:
- **Live Dive Data**: Displays real-time values for depth, pressure, oxygen toxicity, NDL, and RGBM factors.
- **Diver Animation**: Visual representation of depth changes.
- **Decompression Model Selection**: Choose between Bühlmann, RGBM, VPM, or custom models.
- **Gas Mixture Customization**: Select different breathing gases for accurate dive calculations.
- **Dive Log Display**: View and track dive history.
- **Oxygen Toxicity Table**: Reference table for PPO₂ risk analysis.
- **NDL & Graphs Section**: Interactive visualization of decompression limits.

---

## ⚙️ Configuration
- Modify `state` dictionary in `app.py` to change initial dive settings.
- Logs are stored in `static/logs/`.
- The frontend is located in `static/` and can be customized in `static/css/styles.css` and `static/js/script.js`.

---

## 🛠 Technologies Used
- **Python** (Flask, JSON, threading)
- **Mathematical Models**: Bühlmann ZH-L16, RGBM
- **REST API**
- **Frontend**: HTML, CSS, JavaScript (Chart.js for visualization)

---

## 📜 License
MIT License © 2025

---

## 💬 Contact
For issues, suggestions, or contributions, open an issue in the repository or contact **panagiotisnikolaou1982@gmail.com**.

---

🚀 **Happy Diving & Stay Safe!** 🏊‍♂️

