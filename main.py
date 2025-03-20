from typing import TextIO

from flask import Flask, jsonify, request, send_from_directory
import os
import json
from datetime import datetime
import math
import time
from collections import defaultdict
import traceback
from flasgger import Swagger
import os
import signal
import subprocess
import threading
from flask import Blueprint, current_app, request, jsonify
from functools import wraps

# Create a blueprint for debug endpoints
debug_bp = Blueprint('debug', __name__)


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        # Example: check for a custom API key in headers
        api_key = request.headers.get("X-DEBUG-API-KEY")
        if not api_key or api_key != current_app.config.get("DEBUG_API_KEY"):
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)

    return decorated


def kill_port(port):
    """Kills any process currently using the given TCP port."""
    try:
        # Get the list of process IDs (PIDs) using the port
        result = subprocess.check_output(["lsof", "-ti", f"tcp:{port}"])
        pids = result.decode().strip().split("\n")
        for pid in pids:
            if pid:  # Avoid empty strings
                os.kill(int(pid), signal.SIGKILL)
        print(f"Killed processes on port {port}.")
    except subprocess.CalledProcessError:
        print(f"No processes found on port {port}.")


app = Flask(__name__)
app.config["ADMIN_TOKEN"] = "your-secret-admin-token"
app.config["ENV"] = "development"
app.config["DEBUG"] = True  # Optional, but useful for debugging

# Now register the blueprint if in development mode:
if app.config.get("ENV") == "development":
    app.register_blueprint(debug_bp, url_prefix="/debug")

# swagger = Swagger(app)

swagger_template = {
    "swagger": "2.0",
    "info": {
        "title": "Divalgo API",
        "description": "This is the API documentation for Divalgo API.",
        "version": "1.0.0",
        "termsOfService": "http://divalgo.cloud/terms-of-service",
        "contact": {
            "name": "API Support",
            "email": "support@example.com"
        },
        "license": {
            "name": "MIT",
            "url": "https://opensource.org/licenses/MIT"
        }
    },
    "basePath": "/",  # Base path for your endpoints
    "schemes": [
        "http",
        "https"
    ]
}

swagger_config = {
    "headers": [],
    "specs": [
        {
            "endpoint": "apispec_1",
            "route": "/apispec_1.json",
            "rule_filter": lambda rule: True,  # include all endpoints
            "model_filter": lambda tag: True,  # include all models
        }
    ],
    "static_url_path": "/flasgger_static",
    "swagger_ui": True,
    "specs_route": "/swagger/"
}

# swagger = Swagger(app, config=swagger_config, template=swagger_template)

# swagger = Swagger(app, template=swagger_template, config=swagger_config)

swagger = Swagger(app, template=swagger_template)

# Define Bühlmann tissue compartments
buhlmann_tissues = [
    {"tissue": 1, "half_time": 4, "M-value": 1.57},
    {"tissue": 2, "half_time": 8, "M-value": 1.42},
    {"tissue": 3, "half_time": 12.5, "M-value": 1.34},
    {"tissue": 4, "half_time": 18.5, "M-value": 1.28},
    {"tissue": 5, "half_time": 27, "M-value": 1.23},
    {"tissue": 6, "half_time": 38.3, "M-value": 1.20},
    {"tissue": 7, "half_time": 54.3, "M-value": 1.17},
    {"tissue": 8, "half_time": 77, "M-value": 1.14},
    {"tissue": 9, "half_time": 109, "M-value": 1.11},
    {"tissue": 10, "half_time": 146, "M-value": 1.08}
]

# Initialize persistent tissue state and last update time
tissue_state = {tissue["tissue"]: 0.0 for tissue in buhlmann_tissues}
last_update_time = time.time()

# Global dive log (in-memory) for debugging
dive_log = []


@app.route('/api/v1/update_tissue_state', methods=['GET'])
def update_tissue_state_endpoint():
    """
    Update the tissue state for each compartment based on current dive parameters.
    ---
    tags:
      - Tissue State
    produces:
      - application/json
    responses:
      200:
        description: Tissue state updated successfully.
        schema:
          type: object
          properties:
            message:
              type: string
              description: Confirmation message.
              example: "Tissue state updated successfully."
            tissue_state:
              type: object
              description: Updated tissue state values for each compartment.
              example:
                A: 1.23
                B: 2.34
    """
    update_tissue_state()
    return jsonify({
        "message": "Tissue state updated successfully.",
        "tissue_state": tissue_state
    })


def update_tissue_state():
    """
    Example endpoint returning a message.
    ---
    responses:
      200:
        description: A successful response
        schema:
          type: object
          properties:
            message:
              type: string
              example: Hello, world!
    """
    global tissue_state, last_update_time

    current_time = time.time()
    dt_sec = current_time - last_update_time
    dt_min = dt_sec / 60.0  # convert seconds to minutes
    last_update_time = current_time

    # Get current depth from state
    d = float(state.get("depth", 0))
    surface_pressure = 1.0
    # Calculate ambient pressure at current depth (assuming 1 atm per 10 m)
    pressure_at_depth = surface_pressure + (d / 10)
    inert_gas_pressure = pressure_at_depth * (state.get("nitrogen_fraction", 0.79) + state.get("helium_fraction", 0.0))

    # Update each tissue compartment based on dt
    for tissue in buhlmann_tissues:
        tissue_id = tissue["tissue"]
        half_time = tissue["half_time"]
        k = math.log(2) / half_time
        p_old = tissue_state[tissue_id]
        p_new = inert_gas_pressure + (p_old - inert_gas_pressure) * math.exp(-k * dt_min)
        tissue_state[tissue_id] = p_new


@app.route('/api/v1/padi_ndl_lookup', methods=['GET'])
def padi_ndl_lookup_endpoint():
    """
    Lookup the residual no-decompression limit (NDL) using the PADI Recreational Dive Planner.
    ---
    tags:
      - NDL Calculation
    produces:
      - application/json
    responses:
      200:
        description: Returns the residual NDL in minutes based on the current depth and time at depth.
        schema:
          type: object
          properties:
            residual_ndl:
              type: number
              description: The residual no-decompression limit (NDL) in minutes.
              example: 30.5
    """
    result = _padi_ndl_lookup()
    return jsonify({"residual_ndl": result})


def _padi_ndl_lookup():
    """
    Example endpoint returning a message.
    ---
    responses:
      200:
        description: A successful response
        schema:
          type: object
          properties:
            message:
              type: string
              example: Hello, world!
    """
    # global ndl_max
    """
    Calculate the residual no-decompression limit (NDL) based on the PADI Recreational Dive Planner.

    This version uses a table where depths are specified in meters.
    The table below is based on the conversion of the following values from feet:

         Depth (ft) : NDL_max (min)
           40       : 205    --> 12.2 m : 205 min
           50       : 147    --> 15.2 m : 147 min
           60       : 100    --> 18.3 m : 100 min
           70       : 65     --> 21.3 m : 65 min
           80       : 45     --> 24.4 m : 45 min
           90       : 35     --> 27.4 m : 35 min
           100      : 25     --> 30.5 m : 25 min
           110      : 20     --> 33.5 m : 20 min
           120      : 15     --> 36.6 m : 15 min
           130      : 10     --> 39.6 m : 10 min
           140      : 5      --> 42.7 m : 5 min

    The function looks up (or linearly interpolates) the maximum allowed bottom time (NDL_max)
    for the current depth (in meters) stored in the global `state`. It then subtracts the
    actual bottom time (in minutes) to yield the residual NDL.
    """
    # Get the current depth in meters
    depth_m = state.get("depth", 0)

    # Define the PADI table with depths in meters and NDL_max in minutes.
    padi_table = {
        12.2: 205,
        15.2: 147,
        18.3: 100,
        21.3: 65,
        24.4: 45,
        27.4: 35,
        30.5: 25,
        33.5: 20,
        36.6: 15,
        39.6: 10,
        42.7: 5,
    }

    # Get sorted depth values from the table.
    depths = sorted(padi_table.keys())

    # If the current depth is shallower than the shallowest table entry, use that value.
    if depth_m <= depths[0]:
        ndl_max = padi_table[depths[0]]
    # If the current depth exceeds the deepest entry, use the minimum available NDL.
    elif depth_m >= depths[-1]:
        ndl_max = padi_table[depths[-1]]
    else:
        # Otherwise, interpolate linearly between the two nearest depths.
        for i in range(1, len(depths)):
            if depth_m < depths[i]:
                lower_depth = depths[i - 1]
                upper_depth = depths[i]
                lower_ndl = padi_table[lower_depth]
                upper_ndl = padi_table[upper_depth]
                fraction = (depth_m - lower_depth) / (upper_depth - lower_depth)
                ndl_max = lower_ndl + fraction * (upper_ndl - lower_ndl)
                break

    # Get the actual bottom time (in minutes) from the state (time_at_depth is in seconds)
    actual_bottom_time = state.get("time_at_depth", 0) / 60.0

    # Residual NDL is the maximum allowed time minus the actual bottom time.
    residual_ndl = ndl_max - actual_bottom_time

    return round(residual_ndl, 2)


@app.route('/api/v1/log_dive', methods=['POST'])
def log_dive_endpoint():
    """
    Log a dive event.
    ---
    tags:
      - Dive Logs
    consumes:
      - application/json
    parameters:
      - in: body
        name: body
        description: Dive event parameters.
        required: true
        schema:
          type: object
          properties:
            depth:
              type: number
              description: Current dive depth in meters.
              example: 30
            pressure:
              type: number
              description: Ambient pressure in ATA.
              example: 4.0
            o2_toxicity:
              type: number
              description: Calculated oxygen toxicity.
              example: 0.84
            ndl:
              type: number
              description: No-decompression limit in minutes.
              example: 35.0
            rgbm_factor:
              type: number
              description: Current RGBM factor.
              example: 1.0
            time_elapsed:
              type: number
              description: Total dive time in seconds.
              example: 600
            time_at_depth:
              type: number
              description: Time spent at the current depth in seconds.
              example: 120
    responses:
      200:
        description: Dive event logged successfully.
        schema:
          type: object
          properties:
            message:
              type: string
              example: "Dive event logged successfully."
      400:
        description: Missing or invalid input data.
        schema:
          type: object
          properties:
            error:
              type: string
              example: "Missing JSON data"
      500:
        description: Internal server error.
        schema:
          type: object
          properties:
            error:
              type: string
              example: "Internal server error"
            message:
              type: string
              example: "Detailed error message"
    """
    data = request.get_json()
    if not data:
        return jsonify({"error": "Missing JSON data"}), 400

    try:
        depth = float(data.get("depth"))
        pressure = float(data.get("pressure"))
        o2_toxicity = float(data.get("o2_toxicity"))
        ndl = float(data.get("ndl"))
        rgbm_factor = float(data.get("rgbm_factor"))
        time_elapsed = float(data.get("time_elapsed"))
        time_at_depth = float(data.get("time_at_depth"))
    except (ValueError, TypeError) as e:
        return jsonify({"error": "Invalid input", "message": str(e)}), 400

    log_dive(depth, pressure, o2_toxicity, ndl, rgbm_factor, time_elapsed, time_at_depth)
    return jsonify({"message": "Dive event logged successfully."})


def log_dive(depth, pressure, o2_toxicity, ndl, rgbm_factor, time_elapsed, time_at_depth):
    """
    A simple hello endpoint.
    ---
    responses:
      200:
        description: Returns a greeting message.
        schema:
          type: object
          properties:
            message:
              type: string
              example: Hello, world!
    """
    entry = {
        "Depth": depth,
        "Pressure": pressure,
        "Oxygen Toxicity": o2_toxicity,
        "NDL": ndl,
        "RGBM Factor": rgbm_factor,
        "Time Elapsed": time_elapsed,
        "Time at Depth": time_at_depth
    }
    dive_log.append(entry)


@app.route('/api/v1/get_log_filename', methods=['GET'])
def get_log_filename_endpoint():
    """
    Retrieve the log filename for a given client.
    ---
    tags:
      - Dive Logs
    produces:
      - application/json
    parameters:
      - name: Client-UUID
        in: header
        type: string
        required: true
        description: Unique identifier for the client whose log filename is requested.
    responses:
      200:
        description: Returns the path to the client's dive log file.
        schema:
          type: object
          properties:
            log_filename:
              type: string
              description: The file path for the client's dive log.
              example: "static/logs/dive_log_12345.json"
      400:
        description: Missing Client-UUID header.
        schema:
          type: object
          properties:
            error:
              type: string
              example: "Missing Client-UUID header"
    """
    client_uuid = request.headers.get('Client-UUID')
    if not client_uuid or "\x00" in client_uuid:
        return jsonify({"status": "error", "message": "Missing or invalid Client-UUID header"}), 400

    filename = get_log_filename(client_uuid)
    return jsonify({"log_filename": filename})


def get_log_filename(client_uuid):
    """
    Example endpoint returning a message.
    ---
    responses:
      200:
        description: A successful response
        schema:
          type: object
          properties:
            message:
              type: string
              example: Hello, world!
    """
    log_dir = "static/logs"
    os.makedirs(log_dir, exist_ok=True)
    return os.path.join(log_dir, f"dive_log_{client_uuid}.json")


@app.route('/api/v1/ensure_log_file', methods=['POST'])
def ensure_log_file_endpoint():
    """
    Ensure that the dive log file for a client exists and is valid.
    ---
    tags:
      - Dive Logs
    consumes:
      - application/json
    parameters:
      - name: Client-UUID
        in: header
        type: string
        required: true
        description: Unique identifier for the client whose log file should be ensured.
    responses:
      200:
        description: Log file exists and is valid (or was reset if corrupted).
        schema:
          type: object
          properties:
            message:
              type: string
              description: Confirmation message.
              example: "Log file ensured successfully."
      400:
        description: Missing Client-UUID header.
        schema:
          type: object
          properties:
            error:
              type: string
              example: "Missing Client-UUID header"
      500:
        description: Internal server error.
        schema:
          type: object
          properties:
            error:
              type: string
              example: "Internal server error"
            message:
              type: string
              example: "Detailed error message"
    """
    client_uuid = request.headers.get('Client-UUID')
    if not client_uuid or "\x00" in client_uuid:
        return jsonify({"status": "error", "message": "Missing or invalid Client-UUID header"}), 400

    try:
        ensure_log_file(client_uuid)
        return jsonify({"message": "Log file ensured successfully."})
    except Exception as e:
        return jsonify({"error": "Internal server error", "message": str(e)}), 500


def ensure_log_file(client_uuid):
    """
    Example endpoint returning a message.
    ---
    responses:
      200:
        description: A successful response
        schema:
          type: object
          properties:
            message:
              type: string
              example: Hello, world!
    """
    log_file = get_log_filename(client_uuid)
    if not os.path.exists(log_file):
        with open(log_file, "w") as file:
            json.dump([], file)
    else:
        try:
            with open(log_file, "r") as file:
                json.load(file)
        except json.JSONDecodeError:
            with open(log_file, "w") as file:
                json.dump([], file)


@app.route('/api/v1/load_dive_logs', methods=['GET'])
def load_dive_logs_endpoint():
    """
    Load dive logs for a given client.
    ---
    tags:
      - Dive Logs
    produces:
      - application/json
    parameters:
      - name: Client-UUID
        in: header
        type: string
        required: true
        description: Unique identifier for the client whose dive logs are to be loaded.
    responses:
      200:
        description: A JSON array of dive log entries.
        schema:
          type: array
          items:
            type: object
            # Optionally, you can define the dive log properties here.
            # For example:
            # properties:
            #   timestamp:
            #     type: string
            #     description: Time when the log entry was recorded.
            #     example: "2025-03-11 14:30:00"
            #   depth:
            #     type: number
            #     description: Depth in meters.
            #     example: 30
      400:
        description: Missing Client-UUID header.
        schema:
          type: object
          properties:
            error:
              type: string
              example: "Missing Client-UUID"
      500:
        description: Error loading dive logs.
        schema:
          type: object
          properties:
            error:
              type: string
              example: "Internal server error"
            message:
              type: string
              example: "Detailed error message"
    """
    client_uuid = request.headers.get('Client-UUID')
    if not client_uuid or "\x00" in client_uuid:
        return jsonify({"status": "error", "message": "Missing or invalid Client-UUID header"}), 400

    try:
        logs = load_dive_logs(client_uuid)
        return jsonify(logs)
    except Exception as e:
        return jsonify({"error": "Internal server error", "message": str(e)}), 500


def load_dive_logs(client_uuid):
    """
    Example endpoint returning a message.
    ---
    responses:
      200:
        description: A successful response
        schema:
          type: object
          properties:
            message:
              type: string
              example: Hello, world!
    """
    log_file = get_log_filename(client_uuid)
    if not os.path.exists(log_file):
        ensure_log_file(client_uuid)
    try:
        with open(log_file, "r") as file:
            return json.load(file)
    except json.JSONDecodeError:
        print("Warning: Log file corrupted. Resetting...")
        ensure_log_file(client_uuid)
        return []


@app.route('/api/v1/save_dive_log', methods=['POST'])
def save_dive_log_endpoint():
    """
    Save a dive log entry for a specified client.
    ---
    tags:
      - Dive Logs
    consumes:
      - application/json
    parameters:
      - name: Client-UUID
        in: header
        type: string
        required: true
        description: Unique identifier for the client.
      - in: body
        name: body
        description: Dive log entry details.
        required: true
        schema:
          type: object
          properties:
            depth:
              type: number
              description: Current dive depth in meters.
              example: 30
            pressure:
              type: number
              description: Ambient pressure in ATA.
              example: 4.0
            oxygen_toxicity:
              type: number
              description: Calculated oxygen toxicity.
              example: 0.84
            ndl:
              type: number
              description: No-decompression limit in minutes.
              example: 35.0
            rgbm_factor:
              type: number
              description: Current RGBM factor.
              example: 1.0
            total_time:
              type: number
              description: Total dive time in seconds.
              example: 600
            time_at_depth:
              type: number
              description: Time spent at the current depth in seconds.
              example: 120
            # Additional fields can be added here as needed.
    responses:
      200:
        description: Dive log saved successfully.
        schema:
          type: object
          properties:
            message:
              type: string
              example: "Dive log saved successfully."
      400:
        description: Missing or invalid input.
        schema:
          type: object
          properties:
            error:
              type: string
              example: "Missing Client-UUID header"
      500:
        description: Internal server error.
        schema:
          type: object
          properties:
            error:
              type: string
              example: "Internal server error"
            message:
              type: string
              example: "Detailed error message"
    """
    client_uuid = request.headers.get('Client-UUID')
    if not client_uuid or "\x00" in client_uuid:
        return jsonify({"status": "error", "message": "Missing or invalid Client-UUID header"}), 400

    entry = request.get_json()
    if not entry:
        return jsonify({"error": "Missing JSON data"}), 400

    save_dive_log(client_uuid, entry)
    return jsonify({"message": "Dive log saved successfully."})


def save_dive_log(client_uuid, entry):
    """
    Example endpoint returning a message.
    ---
    responses:
      200:
        description: A successful response
        schema:
          type: object
          properties:
            message:
              type: string
              example: Hello, world!
    """
    log_file = get_log_filename(client_uuid)
    logs = load_dive_logs(client_uuid)

    # Reset values at surface
    if entry["depth"] == 0:
        entry["time_at_depth"] = 0
        entry["rgbm_factor"] = 1.0

    logs.append(entry)
    temp_file = log_file + ".tmp"
    with open(temp_file, "w") as file:
        json.dump(logs, file, indent=4)
    os.replace(temp_file, log_file)

    # Print all fields in the log entry
    print("📝 Saved Log Entry:")
    for key, value in entry.items():
        print(f"{key}: {value}")

    # Call log_dive with the required fields
    log_dive(entry['depth'], entry['pressure'], entry['oxygen_toxicity'], entry['ndl'],
             entry['rgbm_factor'], entry['total_time'], entry['time_at_depth'])


# Global diver state
state = {
    "depth": 0,
    "last_depth": 0,
    "time_elapsed": 0,
    "time_at_depth": 0,
    "depth_start_time": time.time(),
    "depth_durations": defaultdict(float),  # Changed to defaultdict to avoid KeyError
    "ndl": -999,
    "rgbm_factor": 1.0,
    "pressure": 1.0,
    "oxygen_toxicity": 0.21,
    "oxygen_fraction": 0.21,
    "nitrogen_fraction": 0.79,
    "helium_fraction": 0.0,  # Added explicit helium_fraction initialization
    "selected_deco_model": "bühlmann",
    "use_rgbm_for_ndl": False,
    "dive_start_time": None  # Initialize dive_start_time
}


@app.route('/api/v1/calculate_rgbm', methods=['GET'])
def calculate_rgbm_endpoint():
    """
    Calculate the RGBM factor using the current dive state.
    ---
    tags:
      - NDL Calculation
    produces:
      - application/json
    responses:
      200:
        description: The calculated RGBM factor based on the current dive state.
        schema:
          type: object
          properties:
            rgbm_factor:
              type: number
              description: The RGBM factor, adjusted based on depth, time at depth, and gas mix.
              example: 1.23456
    """
    factor = calculate_rgbm()
    return jsonify({"rgbm_factor": factor})


def calculate_rgbm():
    """
    Calculate the RGBM factor with higher precision, using the global `state` structure.
    """
    depth = state["depth"]
    time_at_depth = state["time_at_depth"]
    oxygen_fraction = state["oxygen_fraction"]
    nitrogen_fraction = state["nitrogen_fraction"]
    helium_fraction = state.get("helium_fraction", 0.0)  # Default to 0 if not set

    # Prevent division by zero for time_at_depth
    if time_at_depth < 0.1:
        time_at_depth = 0.1

    inert_gas_fraction = nitrogen_fraction + helium_fraction  # Inert gas load in the body
    base_rgbm_factor = (1 + time_at_depth / 60) * math.exp(-depth / 100)

    # Adjust RGBM factor based on the gas mix
    gas_penalty_factor = 1 + (inert_gas_fraction - nitrogen_fraction) * 0.2  # Adjust based on inert gas fraction
    state["rgbm_factor"] = round(base_rgbm_factor * gas_penalty_factor, 5)

    print(f"🌊 Depth: {depth}m, Time: {time_at_depth}s, RGBM Factor: {state['rgbm_factor']}, "
          f"Gas Mix: O₂={oxygen_fraction}, N₂={nitrogen_fraction}, He={helium_fraction}")

    return state["rgbm_factor"]


@app.route('/api/v1/calculate_accumulated_ndl', methods=['GET'])
def calculate_accumulated_ndl_endpoint():
    """
    Calculate the accumulated no-decompression limit (NDL) based on the dive log and current state.
    ---
    tags:
      - NDL Calculation
    produces:
      - application/json
    responses:
      200:
        description: The accumulated NDL value, calculated using either the Bühlmann decompression model equations or the PADI Recreational Dive Planner method, optionally adjusted by the RGBM factor.
        schema:
          type: object
          properties:
            accumulated_ndl:
              type: number
              description: The accumulated no-decompression limit in minutes.
              example: 35.0
    """
    ndl_result = calculate_accumulated_ndl()
    return jsonify({"accumulated_ndl": ndl_result})


def calculate_accumulated_ndl():
    """
    Calculate the accumulated NDL using either the Bühlmann decompression model equations
    or the PADI Recreational Dive Planner table, depending on a flag in the state.

    For each tissue compartment, the tissue tension is updated using:
        P(t+Δt) = P_A + (P(t) - P_A)*exp(-k*Δt)
    where k = ln(2)/half_time and P_A is the ambient pressure at the compartment's depth.

    When the tissue compartment includes Bühlmann coefficients (a and b), the maximum allowed
    tissue tension is:
        p_max = (P_A - a) / b
    and the additional time Δt allowed is obtained by solving:
        P_A - (P_A - P_current)*exp(-k*Δt) = p_max,
    which yields:
        Δt = -1/k * ln((P_A - p_max) / (P_A - P_current))

    Negative Δt values indicate that the tissue is already over its limit.
    If state["use_padi_ndl"] is True, the PADI table-based residual NDL is returned.

    Finally, if state["use_rgbm_for_ndl"] is True, the resulting NDL is divided by the current rgbm_factor.
    """
    # Use the PADI Recreational Dive Planner method if indicated.
    if state.get("use_padi_ndl", False):
        ndl_result = _padi_ndl_lookup()
    else:
        # Ensure we have some log entries.
        if not dive_log:
            ndl_result = 0
        else:
            # Initialize tissue gas tensions for each compartment (starting at 0)
            tissue_tensions = {tissue["tissue"]: 0.0 for tissue in buhlmann_tissues}
            surface_pressure = 1.0

            # Sort the dive log by cumulative time at depth.
            sorted_log = sorted(dive_log, key=lambda e: float(e.get("time_at_depth", e.get("Time at Depth", 0))))
            previous_time = 0.0

            for entry in sorted_log:
                # Extract current cumulative time (in seconds)
                current_time = float(entry.get("time_at_depth", entry.get("Time at Depth", 0)))
                dt = (current_time - previous_time) / 60.0  # convert difference to minutes
                previous_time = current_time
                if dt <= 0:
                    continue  # Skip if no time has elapsed

                # Get the depth for this log entry
                d = float(entry.get("depth", entry.get("Depth", 0)))
                # Ambient pressure at this segment (1 atm at surface + 1 atm per 10 m)
                pressure_at_depth = surface_pressure + (d / 10)
                inert_gas_pressure = pressure_at_depth * (state.get("nitrogen_fraction", 0.79) +
                                                          state.get("helium_fraction", 0.0))
                # Update each tissue compartment using the time increment dt:
                for tissue in buhlmann_tissues:
                    tissue_id = tissue["tissue"]
                    half_time = tissue["half_time"]
                    k = math.log(2) / half_time
                    p_old = tissue_tensions[tissue_id]
                    # Equation: P(t+dt) = P_A + (P(t) - P_A)*exp(-k*dt)
                    p_new = inert_gas_pressure + (p_old - inert_gas_pressure) * math.exp(-k * dt)
                    tissue_tensions[tissue_id] = p_new

            # Now, using the final tissue tensions, compute the allowed additional time (NDL)
            current_depth = state["depth"]
            ambient_pressure = surface_pressure + (current_depth / 10)
            ndl_values = []

            for tissue in buhlmann_tissues:
                tissue_id = tissue["tissue"]
                half_time = tissue["half_time"]
                k = math.log(2) / half_time
                current_tension = tissue_tensions[tissue_id]
                # If Bühlmann coefficients are provided, use them.
                a = tissue.get("a")
                b = tissue.get("b")
                if a is not None and b is not None:
                    # Maximum allowable tissue tension according to Bühlmann:
                    p_max = (ambient_pressure - a) / b
                    numerator = ambient_pressure - p_max
                    denominator = ambient_pressure - current_tension
                    if denominator <= 0:
                        ndl = 0
                    else:
                        try:
                            ratio = numerator / denominator
                            ndl = -1 / k * math.log(ratio)
                        except Exception:
                            ndl = 0
                else:
                    # Fallback: use the simplified M-value method.
                    max_tension = tissue.get("M-value", 1.0) * surface_pressure
                    numerator = ambient_pressure - max_tension
                    denominator = ambient_pressure - current_tension
                    if denominator <= 0:
                        ndl = 0
                    else:
                        try:
                            ratio = numerator / denominator
                            ndl = -1 / k * math.log(ratio)
                        except Exception:
                            ndl = 0
                ndl_values.append(ndl)

            # Combine negative NDL values if any exist; otherwise, choose the smallest positive value.
            negatives = [ndl for ndl in ndl_values if ndl < 0]
            if negatives:
                ndl_result = sum(negatives)
            else:
                ndl_result = min(ndl_values) if ndl_values else 0

    # Integrate RGBM adjustment if enabled.
    if state.get("use_rgbm_for_ndl", False):
        rgbm_factor = state.get("rgbm_factor", 1.0)
        if rgbm_factor > 0:
            ndl_result = ndl_result * (1 / rgbm_factor)

    return round(ndl_result, 2)


@app.route('/api/v1/toggle-padi-ndl', methods=['POST'])
def toggle_padi_ndl():
    """
    Toggle PADI NDL table lookup.
    ---
    tags:
      - NDL Calculation
    consumes:
      - application/json
    parameters:
      - in: body
        name: body
        description: JSON payload to toggle the use of the PADI NDL table lookup.
        required: true
        schema:
          type: object
          properties:
            use_padi_ndl:
              type: boolean
              description: Set to true to enable PADI NDL lookup, or false to disable.
              example: true
    responses:
      200:
        description: PADI NDL lookup toggled successfully.
        schema:
          type: object
          properties:
            message:
              type: string
              description: A message indicating the current state of the PADI NDL lookup.
              example: "PADI tables lookup enabled"
            use_padi_ndl:
              type: boolean
              description: The current state of the PADI NDL lookup flag.
              example: true
    """
    data = request.get_json()
    # Update the global state flag for using PADI table lookup
    state["use_padi_ndl"] = data.get("use_padi_ndl", False)
    message = f"PADI tables lookup {'enabled' if state['use_padi_ndl'] else 'disabled'}"
    print(message)
    return jsonify({"message": message, "use_padi_ndl": state["use_padi_ndl"]})


@app.route('/api/v1/update_time_at_depth', methods=['GET'])
def update_time_at_depth_endpoint():
    """
    Update dive time and recalculate time at depth and RGBM factor.
    ---
    tags:
      - Dive State
    produces:
      - application/json
    responses:
      200:
        description: Dive time and RGBM factor updated successfully.
        schema:
          type: object
          properties:
            message:
              type: string
              example: Dive time and RGBM factor updated successfully.
            time_elapsed:
              type: number
              description: The updated total dive time in seconds.
              example: 300.0
            time_at_depth:
              type: number
              description: The updated time spent at the current depth in seconds.
              example: 60.0
            rgbm_factor:
              type: number
              description: The recalculated RGBM factor.
              example: 1.05
    """
    update_time_at_depth()
    return jsonify({
        "message": "Dive time and RGBM factor updated successfully.",
        "time_elapsed": state["time_elapsed"],
        "time_at_depth": state["time_at_depth"],
        "rgbm_factor": state["rgbm_factor"]
    })


def update_time_at_depth():
    """Update dive time and recalc time at depth and RGBM factor."""
    now = time.time()

    # Initialize dive_start_time if not set
    if state["dive_start_time"] is None:
        state["dive_start_time"] = now

    state["time_elapsed"] = now - state["dive_start_time"]

    # If at surface, reset time_at_depth and RGBM factor
    if state["depth"] == 0:
        state["depth_start_time"] = now
        state["time_at_depth"] = 0
        state["rgbm_factor"] = 1.0
        return

    elapsed_at_depth = now - state["depth_start_time"]
    # No need to check existence with defaultdict
    state["depth_durations"][state["depth"]] += elapsed_at_depth
    state["time_at_depth"] = round(state["depth_durations"][state["depth"]], 2)
    state["depth_start_time"] = now
    state["rgbm_factor"] = calculate_rgbm()
    print(
        f"🟢 DEBUG: Depth: {state['depth']}m, Time at Depth: {state['time_at_depth']} sec, RGBM: {state['rgbm_factor']:.5f}")
    state["last_depth"] = state["depth"]


@app.route('/api/v1/calculate_ndl_stops', methods=['POST'])
def calculate_ndl_stops():
    """
    Calculate decompression stops based on dive parameters.
    ---
    tags:
      - Decompression
    consumes:
      - application/json
    parameters:
      - in: body
        name: body
        description: Dive parameters required to calculate decompression stops.
        required: true
        schema:
          type: object
          properties:
            ndl:
              type: number
              description: No-decompression limit in minutes.
              example: -5.0
            depth:
              type: number
              description: Current depth in meters.
              example: 30
            pressure:
              type: number
              description: Ambient pressure in ATA.
              example: 4.0
            oxygen_toxicity:
              type: number
              description: Calculated oxygen toxicity.
              example: 0.84
            rgbm_factor:
              type: number
              description: Current RGBM factor applied to NDL calculation.
              example: 1.0
            time_elapsed:
              type: number
              description: Total elapsed dive time in seconds.
              example: 600
            time_at_depth:
              type: number
              description: Time spent at the current depth in seconds.
              example: 120
            oxygen_fraction:
              type: number
              description: (Optional) Fraction of oxygen in the breathing gas.
              example: 0.21
            nitrogen_fraction:
              type: number
              description: (Optional) Fraction of nitrogen in the breathing gas.
              example: 0.79
            helium_fraction:
              type: number
              description: (Optional) Fraction of helium in the breathing gas.
              example: 0.0
    responses:
      200:
        description: A list of decompression stops with depth, duration, and reason.
        schema:
          type: object
          properties:
            stops:
              type: array
              items:
                type: object
                properties:
                  depth:
                    type: number
                    description: The depth of the decompression stop in meters.
                    example: 20
                  duration:
                    type: number
                    description: The duration of the decompression stop in minutes.
                    example: 10
                  reason:
                    type: string
                    description: The reason for the decompression stop.
                    example: "NDL exceeded"
      400:
        description: Missing or invalid input parameters.
        schema:
          type: object
          properties:
            error:
              type: string
              example: "Missing keys: ndl, depth, pressure, oxygen_toxicity, rgbm_factor, time_elapsed, time_at_depth"
      500:
        description: Internal server error.
        schema:
          type: object
          properties:
            error:
              type: string
              example: "Internal server error"
            message:
              type: string
              example: "Detailed error message"
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON data received"}), 400

        required_keys = ["ndl", "depth", "pressure", "oxygen_toxicity", "rgbm_factor", "time_elapsed", "time_at_depth"]
        missing_keys = [key for key in required_keys if key not in data]
        if missing_keys:
            return jsonify({"error": f"Missing keys: {', '.join(missing_keys)}"}), 400

        ndl = float(data["ndl"])
        depth = float(data["depth"])
        pressure = float(data["pressure"])
        oxygen_toxicity = float(data["oxygen_toxicity"])
        rgbm_factor = float(data["rgbm_factor"])
        time_elapsed = int(data["time_elapsed"])
        time_at_depth = int(data["time_at_depth"])
        # Use default values if gas fractions are not provided
        oxygen_fraction = float(data.get("oxygen_fraction", state.get("oxygen_fraction", 0.21)))
        nitrogen_fraction = float(data.get("nitrogen_fraction", state.get("nitrogen_fraction", 0.79)))
        helium_fraction = float(data.get("helium_fraction", state.get("helium_fraction", 0.0)))

        print(f"📩 Received: NDL={ndl}, Depth={depth}, Pressure={pressure}, O₂ Toxicity={oxygen_toxicity}, "
              f"RGBM={rgbm_factor}, Time Elapsed={time_elapsed}, Time at Depth={time_at_depth}, "
              f"O2={oxygen_fraction}, N₂={nitrogen_fraction}, He={helium_fraction}")

        stops = generate_decompression_stops(ndl, depth, pressure, oxygen_toxicity, rgbm_factor, time_elapsed,
                                             time_at_depth)
        return jsonify({"stops": stops})

    except Exception as e:
        print(f"❌ Error processing request: {str(e)}")
        traceback.print_exc()
        return jsonify({"error": "Internal server error", "message": str(e)}), 500


@app.route('/api/v1/decompression_stops', methods=['POST'])
def get_decompression_stops():
    """
    Generate decompression stops based on dive parameters.
    ---
    tags:
      - Decompression
    consumes:
      - application/json
    parameters:
      - in: body
        name: body
        description: Dive parameters required to generate decompression stops.
        required: true
        schema:
          type: object
          properties:
            ndl:
              type: number
              description: No-decompression limit in minutes.
              example: -5.0
            depth:
              type: number
              description: Current depth in meters.
              example: 30
            pressure:
              type: number
              description: Ambient pressure in ATA.
              example: 4.0
            oxygen_toxicity:
              type: number
              description: Calculated oxygen toxicity based on the current gas mix and pressure.
              example: 0.84
            rgbm_factor:
              type: number
              description: Current RGBM factor applied in NDL calculation.
              example: 1.0
            time_elapsed:
              type: number
              description: Total elapsed dive time in seconds.
              example: 600
            time_at_depth:
              type: number
              description: Time spent at the current depth in seconds.
              example: 120
    responses:
      200:
        description: A list of decompression stops with their depth, duration, and reason.
        schema:
          type: array
          items:
            type: object
            properties:
              depth:
                type: number
                description: The depth at which a decompression stop is required.
                example: 20
              duration:
                type: number
                description: The duration in minutes of the decompression stop.
                example: 10
              reason:
                type: string
                description: The reason for the decompression stop.
                example: "NDL exceeded"
      400:
        description: Invalid or missing input parameters.
        schema:
          type: object
          properties:
            error:
              type: string
              example: "Missing or invalid JSON data"
    """
    data = request.get_json()
    if not data:
        return jsonify({"error": "Missing JSON data"}), 400

    try:
        ndl = float(data.get("ndl"))
        depth = float(data.get("depth"))
        pressure = float(data.get("pressure"))
        oxygen_toxicity = float(data.get("oxygen_toxicity"))
        rgbm_factor = float(data.get("rgbm_factor"))
        time_elapsed = float(data.get("time_elapsed"))
        time_at_depth = float(data.get("time_at_depth"))
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid input. Ensure all parameters are numeric."}), 400

    stops = generate_decompression_stops(ndl, depth, pressure, oxygen_toxicity, rgbm_factor, time_elapsed,
                                         time_at_depth)
    return jsonify(stops)


def generate_decompression_stops(ndl, depth, pressure, oxygen_toxicity, rgbm_factor, time_elapsed, time_at_depth):
    """
    Example endpoint returning a message.
    ---
    responses:
      200:
        description: A successful response
        schema:
          type: object
          properties:
            message:
              type: string
              example: Hello, world!
    """
    """Generate decompression stops based on dive parameters."""
    stops = []
    if ndl <= 0:
        # Start with a reasonable first stop depth
        stop_depth = (depth // 10) * 10 - 10  # Round to nearest 10m and subtract 10

        # Make sure stop_depth is at least 3m and not greater than current depth - 3m
        stop_depth = min(max(3, stop_depth), depth - 3)

        while stop_depth > 0:
            # Calculate stop time based on depth and NDL deficit
            stop_time = max(3, int(abs(ndl) * (1 + (stop_depth / depth) * 0.5)))
            reason = "NDL exceeded" if ndl < 0 else "NDL reached"

            stops.append({
                "depth": stop_depth,
                "duration": stop_time,
                "reason": reason
            })

            # More frequent stops at shallower depths
            if stop_depth > 9:
                stop_depth -= 3
            else:
                stop_depth -= 3

    return stops


@app.route('/api/v1/current_state', methods=['GET'])
def get_current_state_endpoint():
    """
    Retrieve the current dive state.
    ---
    tags:
      - Dive State
    produces:
      - application/json
    responses:
      200:
        description: The current state of the dive, including depth, time, pressures, gas mix, and computed NDL.
        schema:
          type: object
          properties:
            timestamp:
              type: string
              description: The current timestamp.
              example: "2025-03-11 14:30:00"
            depth:
              type: integer
              description: Current dive depth in meters.
              example: 30
            last_depth:
              type: integer
              description: Last recorded dive depth in meters.
              example: 20
            time_elapsed:
              type: number
              description: Total elapsed dive time in seconds.
              example: 600
            total_time:
              type: number
              description: Total dive time in seconds.
              example: 600
            time_at_depth:
              type: number
              description: Time spent at the current depth in seconds.
              example: 120
            depth_start_time:
              type: number
              description: Epoch time when the current depth was reached.
              example: 1616580000.0
            depth_durations:
              type: object
              description: A mapping of depths (in meters) to the duration spent at each depth (in seconds).
              additionalProperties:
                type: number
              example: {"30": 120, "20": 180}
            ndl:
              type: number
              description: Calculated no-decompression limit (NDL) in minutes.
              example: 35.0
            rgbm_factor:
              type: number
              description: Current RGBM factor used in NDL calculation.
              example: 1.0
            pressure:
              type: number
              description: Ambient pressure in ATA at the current depth.
              example: 4.0
            oxygen_toxicity:
              type: number
              description: Computed oxygen toxicity based on the current gas mix and pressure.
              example: 0.84
            oxygen_fraction:
              type: number
              description: Fraction of oxygen in the breathing gas.
              example: 0.21
            nitrogen_fraction:
              type: number
              description: Fraction of nitrogen in the breathing gas.
              example: 0.79
            helium_fraction:
              type: number
              description: Fraction of helium in the breathing gas.
              example: 0.0
            selected_deco_model:
              type: string
              description: The selected decompression model.
              example: "bühlmann"
            use_rgbm_for_ndl:
              type: boolean
              description: Flag indicating if RGBM-based NDL calculation is enabled.
              example: false
            dive_start_time:
              type: number
              description: Epoch time when the dive started.
              example: 1616580000.0
    """
    current_state = get_current_state()
    return jsonify(current_state)


def get_current_state():
    """
    Returns the current state as a dictionary.
    This includes all the fields you want to log.
    """
    update_time_at_depth()  # Ensure state is up-to-date
    return {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "depth": int(state["depth"]),
        "last_depth": int(state["last_depth"]),
        "time_elapsed": state["time_elapsed"],
        "total_time": state["time_elapsed"],
        "time_at_depth": state["time_at_depth"],
        "depth_start_time": state["depth_start_time"],
        "depth_durations": dict(state["depth_durations"]),
        "ndl": _calculate_ndl(state["depth"], state["time_at_depth"] / 60),
        "rgbm_factor": state["rgbm_factor"],
        "pressure": state["pressure"],
        "oxygen_toxicity": state["oxygen_toxicity"],
        "oxygen_fraction": state["oxygen_fraction"],
        "nitrogen_fraction": state["nitrogen_fraction"],
        "helium_fraction": state["helium_fraction"],
        "selected_deco_model": state["selected_deco_model"],
        "use_rgbm_for_ndl": state["use_rgbm_for_ndl"],
        "dive_start_time": state["dive_start_time"]
    }


@app.route('/api/v1/dive', methods=['POST'])
def dive():
    """
    Log a dive event by capturing the current state and updating it for the next depth increment.
    ---
    tags:
      - Dive Operations
    produces:
      - application/json
    parameters:
      - name: Client-UUID
        in: header
        type: string
        required: true
        description: Unique identifier for the client performing the dive.
    responses:
      200:
        description: Updated dive state after logging the dive event.
        schema:
          type: object
          properties:
            depth:
              type: number
              description: Current depth in meters after the dive event.
              example: 40
            last_depth:
              type: number
              description: The depth before the latest dive update.
              example: 30
            pressure:
              type: number
              description: Ambient pressure in ATA.
              example: 5.0
            oxygen_toxicity:
              type: number
              description: Calculated oxygen toxicity based on the current gas mix and pressure.
              example: 1.05
            time_at_depth:
              type: number
              description: Time spent at the current depth in seconds.
              example: 600
            rgbm_factor:
              type: number
              description: Current RGBM factor applied to the NDL calculation.
              example: 1.2
            # Additional state fields can be added here as needed.
      400:
        description: Missing Client-UUID header.
        schema:
          type: object
          properties:
            error:
              type: string
              example: Missing Client-UUID
    """
    client_uuid = request.headers.get('Client-UUID')
    if not client_uuid or "\x00" in client_uuid:
        return jsonify({"status": "error", "message": "Missing or invalid Client-UUID header"}), 400

    if 0 <= state["depth"] < 350:
        # Capture the complete state (and update time if needed)
        current_state = get_current_state()

        # Print all key-value pairs for debugging
        print("📝 Current State:")
        for key, value in current_state.items():
            print(f"{key}: {value}")

        # Use the current state as the log entry
        log_entry = current_state
        save_dive_log(client_uuid, log_entry)

        # Update state for the next depth (if needed)
        state["last_depth"] = state["depth"]
        state["depth"] += 10
        state["pressure"] += 1
        state["depth_start_time"] = time.time()
        # Optionally, initialize the new depth in depth_durations
        state["time_at_depth"] = state["depth_durations"][state["depth"]]
        state["oxygen_toxicity"] = round(state["oxygen_fraction"] * state["pressure"], 2)
        state["rgbm_factor"] = calculate_rgbm()
        print(json.dumps(state, indent=4))

    return jsonify(state)


@app.route('/api/v1/ascend', methods=['POST'])
def ascend():
    """
    Command the diver to ascend by reducing depth.
    ---
    tags:
      - Dive Control
    produces:
      - application/json
    parameters:
      - name: Client-UUID
        in: header
        type: string
        required: true
        description: Unique identifier for the client initiating the ascend command.
    responses:
      200:
        description: Returns the updated dive state after ascending.
        schema:
          type: object
          properties:
            depth:
              type: number
              description: The current depth in meters after ascending.
              example: 20
            pressure:
              type: number
              description: The ambient pressure in ATA at the current depth.
              example: 3.0
            oxygen_toxicity:
              type: number
              description: The calculated oxygen toxicity based on the current gas mix and pressure.
              example: 0.63
            ndl:
              type: number
              description: The current no-decompression limit (NDL) in minutes.
              example: 25.0
            rgbm_factor:
              type: number
              description: The current RGBM factor applied to NDL calculation.
              example: 1.1
            time_elapsed:
              type: number
              description: Total elapsed dive time in seconds.
              example: 300
            time_at_depth:
              type: number
              description: Time spent at the current depth in seconds.
              example: 60
            # Additional state keys may be added here if needed.
      400:
        description: Missing Client-UUID header.
        schema:
          type: object
          properties:
            error:
              type: string
              example: Missing Client-UUID
    """
    client_uuid = request.headers.get('Client-UUID')
    if not client_uuid or "\x00" in client_uuid:
        return jsonify({"status": "error", "message": "Missing or invalid Client-UUID header"}), 400

    if state["depth"] > 0:
        update_time_at_depth()
        state["last_depth"] = state["depth"]
        state["depth"] -= 10
        if state["depth"] < 0:
            state["depth"] = 0
        state["depth_start_time"] = time.time()
        state["time_at_depth"] = state["depth_durations"][state["depth"]]  # Using defaultdict, so no .get() needed

        state["ndl"] = _calculate_ndl(state["depth"], state["time_at_depth"] / 60)
        state["pressure"] = round(1 + (state["depth"] / 10), 2)
        state["oxygen_toxicity"] = round(state["oxygen_fraction"] * state["pressure"], 2)
        state["rgbm_factor"] = calculate_rgbm()

        log_entry = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "depth": state["depth"],
            "pressure": state["pressure"],
            "oxygen_toxicity": state["oxygen_toxicity"],
            "ndl": state["ndl"],
            "rgbm_factor": state["rgbm_factor"],
            "total_time": max(1, round(state["time_elapsed"], 2)),
            "time_at_depth": max(1, round(state["time_at_depth"], 2))
        }
        print(f"Ascending: {log_entry}")
        save_dive_log(client_uuid, log_entry)

    return jsonify(state)


@app.route('/api/v1/logs', methods=['GET'])
def get_logs():
    """
    Retrieve dive logs for a given client.
    ---
    tags:
      - Dive Logs
    produces:
      - application/json
    parameters:
      - name: Client-UUID
        in: header
        type: string
        required: true
        description: Unique identifier for the client whose dive logs are being requested.
    responses:
      200:
        description: A JSON array containing the dive logs.
        schema:
          type: array
          items:
            type: object
            # Define properties of a dive log entry if known, for example:
            # properties:
            #   timestamp:
            #     type: string
            #     description: The time when the log entry was recorded.
            #     example: "2025-03-11 14:30:00"
            #   depth:
            #     type: number
            #     description: The depth recorded in the dive log.
            #     example: 30
            #   pressure:
            #     type: number
            #     description: The ambient pressure in ATA.
            #     example: 4.0
      400:
        description: Missing Client-UUID header.
        schema:
          type: object
          properties:
            error:
              type: string
              example: Missing Client-UUID
    """
    client_uuid = request.headers.get('Client-UUID')
    if not client_uuid or "\x00" in client_uuid:
        return jsonify({"status": "error", "message": "Missing or invalid Client-UUID header"}), 400

    logs = load_dive_logs(client_uuid)
    print(f"Loaded logs: {logs}")
    return jsonify(logs)


@app.route('/api/v1/state', methods=['GET'])
def get_state():
    """
    Retrieve the current dive state.
    ---
    tags:
      - Dive State
    produces:
      - application/json
    responses:
      200:
        description: Dive state information including current depth, pressure, oxygen toxicity, NDL values, and decompression model settings.
        schema:
          type: object
          properties:
            depth:
              type: number
              description: Current depth in meters.
              example: 30
            pressure:
              type: number
              description: Ambient pressure in ATA.
              example: 4.0
            oxygen_toxicity:
              type: number
              description: Calculated oxygen toxicity based on the current gas mix and depth.
              example: 0.84
            oxygen_fraction:
              type: number
              description: Fraction of oxygen in the breathing gas.
              example: 0.21
            nitrogen_fraction:
              type: number
              description: Fraction of nitrogen in the breathing gas.
              example: 0.79
            helium_fraction:
              type: number
              description: Fraction of helium in the breathing gas.
              example: 0.0
            ndl:
              type: number
              description: Calculated no-decompression limit (NDL) in minutes.
              example: 35.0
            accumulated_ndl:
              type: number
              description: Accumulated NDL based on the entire dive log.
              example: 20.0
            rgbm_factor:
              type: number
              description: Current RGBM factor used in NDL calculation.
              example: 1.2
            time_at_depth_minutes:
              type: number
              description: Time spent at the current depth in minutes.
              example: 15.5
            time_elapsed_minutes:
              type: number
              description: Total elapsed dive time in minutes.
              example: 45.0
            selected_deco_model:
              type: string
              description: The selected decompression model.
              example: bühlmann
            use_rgbm_for_ndl:
              type: boolean
              description: Indicates whether RGBM-based NDL calculation is enabled.
              example: true
            buhlmann_ndl:
              type: object
              description: Details of the Bühlmann model calculations.
              properties:
                gas_type:
                  type: string
                  description: Composition of the breathing gas.
                  example: "21% O₂, 79% N₂, 0% He"
                hlf_times:
                  type: array
                  items:
                    type: number
                  description: List of tissue half-times.
                  example: [5, 10, 20, 40]
                compartments:
                  type: array
                  items:
                    type: object
                  description: Tissue compartments used in the Bühlmann decompression model.
    """
    # Update time tracking before returning state
    update_time_at_depth()

    log_entry = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "depth": state["depth"],
        "pressure": state["pressure"],
        "oxygen_toxicity": state["oxygen_toxicity"],
        "ndl": state["ndl"],
        "rgbm_factor": state["rgbm_factor"],
        "total_time": max(1, round(state["time_elapsed"], 2)),
        "time_at_depth": max(1, round(state["time_at_depth"], 2)),
        "oxygen_fraction": state.get("oxygen_fraction", 0.21),
        "nitrogen_fraction": state.get("nitrogen_fraction", 0.79),
        "helium_fraction": state.get("helium_fraction", 0.0)
    }

    print(f"Logging State: {log_entry}")
    log_dive(log_entry['depth'], log_entry['pressure'], log_entry['oxygen_toxicity'],
             log_entry['ndl'], log_entry['rgbm_factor'], log_entry['total_time'], log_entry['time_at_depth'])

    depth = state["depth"]
    pressure = state["pressure"]
    oxygen_toxicity = state["oxygen_toxicity"]
    time_at_depth_sec = state["time_at_depth"]
    time_elapsed_sec = state["time_elapsed"]
    rgbm_factor = state["rgbm_factor"]
    selected_deco_model = state.get("selected_deco_model", "bühlmann")
    oxygen_fraction = state.get("oxygen_fraction", 0.21)
    nitrogen_fraction = state.get("nitrogen_fraction", 0.79)
    helium_fraction = state.get("helium_fraction", 0.0)

    time_at_depth_min = round(time_at_depth_sec / 60, 2)
    time_elapsed_min = round(time_elapsed_sec / 60, 2)

    # Ensure a minimum value for time_at_depth_min to avoid division by zero issues
    if time_at_depth_min < 0.01:
        time_at_depth_min = 0.01

    # Calculate current NDL based on the current depth and time at that depth
    ndl_value = _calculate_ndl(depth, time_at_depth_min, oxygen_fraction, nitrogen_fraction, helium_fraction)
    # Recalculate RGBM factor (if needed)
    state["rgbm_factor"] = calculate_rgbm()

    # Compute the accumulated NDL based on the entire dive log
    accumulated_ndl = calculate_accumulated_ndl()

    # Optionally adjust NDL if RGBM-based adjustment is enabled
    if state.get("use_rgbm_for_ndl", False):
        if state["rgbm_factor"] > 0:
            ndl_value *= (1 / state["rgbm_factor"])
        ndl_value = round(ndl_value, 2)

    return jsonify({
        "depth": depth,
        "pressure": pressure,
        "oxygen_toxicity": oxygen_toxicity,
        "oxygen_fraction": oxygen_fraction,
        "nitrogen_fraction": nitrogen_fraction,
        "helium_fraction": helium_fraction,
        "ndl": ndl_value,
        "accumulated_ndl": accumulated_ndl,
        "rgbm_factor": rgbm_factor,
        "time_at_depth_minutes": time_at_depth_min,
        "time_elapsed_minutes": time_elapsed_min,
        "selected_deco_model": selected_deco_model,
        "use_rgbm_for_ndl": state.get("use_rgbm_for_ndl", False),
        "buhlmann_ndl": {
            "gas_type": f"{oxygen_fraction * 100:.0f}% O₂, {nitrogen_fraction * 100:.0f}% N₂, {helium_fraction * 100:.0f}% He",
            "hlf_times": [tissue["half_time"] for tissue in buhlmann_tissues],
            "compartments": buhlmann_tissues
        }
    })


@app.route('/api/v1/toggle-rgbm-ndl', methods=['POST'])
def toggle_rgbm_ndl():
    """
    Toggle RGBM-based NDL calculation.
    ---
    tags:
      - NDL Calculation
    consumes:
      - application/json
    parameters:
      - in: body
        name: body
        description: JSON payload to toggle RGBM-based NDL calculation.
        required: true
        schema:
          type: object
          properties:
            use_rgbm:
              type: boolean
              description: Set to true to enable RGBM-based NDL calculation; false to disable.
              example: true
    responses:
      200:
        description: Returns a message indicating whether RGBM-based NDL calculation is enabled or disabled.
        schema:
          type: object
          properties:
            message:
              type: string
              example: RGBM-based NDL calculation enabled
    """
    data = request.json
    state["use_rgbm_for_ndl"] = data.get("use_rgbm", False)
    return jsonify({"message": f"RGBM-based NDL calculation {'enabled' if state['use_rgbm_for_ndl'] else 'disabled'}"})


# Global variable for smoothed NDL (initialize to a high value)
smoothed_ndl = 200


@app.route('/api/v1/compute_ndl', methods=['GET'])
def compute_ndl_endpoint():
    """
    Compute the no-decompression limit (NDL) based on the current state.
    ---
    tags:
      - NDL Calculation
    produces:
      - application/json
    responses:
      200:
        description: Returns the computed and smoothed NDL value.
        schema:
          type: object
          properties:
            ndl:
              type: number
              description: The computed no-decompression limit in minutes.
              example: 35.0
    """
    ndl = compute_ndl()  # Call your compute_ndl function
    return jsonify({"ndl": ndl})


def compute_ndl():
    global smoothed_ndl

    surface_pressure = 1.0
    current_depth = state.get("depth", 0)
    ambient_pressure = surface_pressure + (current_depth / 10)
    ndl_values = []

    for tissue in buhlmann_tissues:
        tissue_id = tissue["tissue"]
        half_time = tissue["half_time"]
        k = math.log(2) / half_time
        current_tension = tissue_state[tissue_id]

        # Use Bühlmann coefficients if available, otherwise use the M-value.
        a = tissue.get("a")
        b = tissue.get("b")
        if a is not None and b is not None:
            p_max = (ambient_pressure - a) / b
            numerator = ambient_pressure - p_max
            denominator = ambient_pressure - current_tension
            if denominator <= 0:
                ndl = 0
            else:
                try:
                    ratio = numerator / denominator
                    ndl = -1 / k * math.log(ratio)
                except Exception:
                    ndl = 0
        else:
            max_tension = tissue.get("M-value", 1.0) * surface_pressure
            numerator = ambient_pressure - max_tension
            denominator = ambient_pressure - current_tension
            if denominator <= 0:
                ndl = 0
            else:
                try:
                    ratio = numerator / denominator
                    ndl = -1 / k * math.log(ratio)
                except Exception:
                    ndl = 0
        ndl_values.append(ndl)

    # Combine negative values if present, otherwise choose the minimum positive value
    negatives = [ndl for ndl in ndl_values if ndl < 0]
    if negatives:
        accumulated_ndl = sum(negatives)
    else:
        accumulated_ndl = min(ndl_values) if ndl_values else 0

    # Apply RGBM adjustment if enabled
    if state.get("use_rgbm_for_ndl", False):
        rgbm_factor = state.get("rgbm_factor", 1.0)
        if rgbm_factor > 0:
            accumulated_ndl *= (1 / rgbm_factor)

    # Smooth the NDL output using exponential smoothing.
    alpha = 0.1  # smoothing factor: smaller values yield smoother, slower updates.
    smoothed_ndl = smoothed_ndl + alpha * (accumulated_ndl - smoothed_ndl)

    return round(smoothed_ndl, 2)


@app.route('/api/v1/calculate_ndl', methods=['POST'])
# @admin_required
def calculate_ndl_endpoint():
    """
    Calculate the no-decompression limit (NDL) for a dive.
    ---
    tags:
      - NDL Calculation
    consumes:
      - application/json
    parameters:
      - in: header
        name: Client-UUID
        type: string
        required: true
        description: Unique identifier for the client performing the dive.
      - in: header
        name: X-Admin-Token
        type: string
        required: true
        description: Admin token required to access this endpoint.
      - in: body
        name: body
        description: Dive parameters required to calculate the NDL.
        required: true
        schema:
          type: object
          properties:
            depth:
              type: number
              description: Current dive depth in meters.
              example: 30
              minimum: 0
              maximum: 350
            time_at_depth_minutes:
              type: number
              description: Time spent at depth in minutes.
              example: 20
              minimum: 0.1
            oxygen_fraction:
              type: number
              description: Fraction of oxygen in the breathing gas.
              example: 0.21
              minimum: 0
              maximum: 1
            nitrogen_fraction:
              type: number
              description: Fraction of nitrogen in the breathing gas.
              example: 0.79
              minimum: 0
              maximum: 1
            helium_fraction:
              type: number
              description: Fraction of helium in the breathing gas.
              example: 0.0
              minimum: 0
              maximum: 1
    responses:
      200:
        description: The calculated no-decompression limit (NDL) in minutes.
        schema:
          type: object
          properties:
            ndl:
              type: number
              description: The calculated no-decompression limit (NDL).
              example: 35.0
      400:
        description: Missing or invalid input.
        schema:
          type: object
          properties:
            error:
              type: string
              example: "Missing JSON data"
      401:
        description: Unauthorized access.
        schema:
          type: object
          properties:
            error:
              type: string
              example: "Unauthorized"
    """
    data = request.get_json()
    if not data:
        return jsonify({"error": "Missing JSON data"}), 400

    try:
        depth = float(data.get("depth"))
        time_at_depth_minutes = float(data.get("time_at_depth_minutes"))
        oxygen_fraction = float(data.get("oxygen_fraction", 0.21))
        nitrogen_fraction = float(data.get("nitrogen_fraction", 0.79))
        helium_fraction = float(data.get("helium_fraction", 0.0))
    except (TypeError, ValueError) as e:
        return jsonify({"error": "Invalid input", "message": str(e)}), 400

    # Check for invalid values
    if time_at_depth_minutes <= 0:
        return jsonify({"error": "time_at_depth_minutes must be greater than 0"}), 400

    ndl_value = _calculate_ndl(depth, time_at_depth_minutes, oxygen_fraction, nitrogen_fraction, helium_fraction)
    return jsonify({"ndl": ndl_value})


@app.route('/api/v1/_calculate_ndl', methods=['POST'])
def _calculate_ndl(depth, time_at_depth_minutes, oxygen_fraction=0.21, nitrogen_fraction=0.79, helium_fraction=0.0):
    """
    Calculate the no-decompression limit (NDL) for a given depth and time at depth.
    ---
    tags:
      - NDL Calculation
    consumes:
      - application/json
    parameters:
      - in: body
        name: body
        description: JSON payload containing the depth (in meters), time at depth (in minutes), and optional gas fractions.
        required: true
        schema:
          type: object
          properties:
            depth:
              type: number
              description: Depth in meters.
              example: 30
            time_at_depth_minutes:
              type: number
              description: Time spent at depth in minutes.
              example: 20
            oxygen_fraction:
              type: number
              description: Oxygen fraction (optional, default is 0.21).
              example: 0.21
            nitrogen_fraction:
              type: number
              description: Nitrogen fraction (optional, default is 0.79).
              example: 0.79
            helium_fraction:
              type: number
              description: Helium fraction (optional, default is 0.0).
              example: 0.0
    responses:
      200:
        description: Calculated NDL value.
        schema:
          type: object
          properties:
            ndl:
              type: number
              description: The no-decompression limit in minutes.
              example: 35.0
      400:
        description: Invalid or missing input data.
        schema:
          type: object
          properties:
            error:
              type: string
              example: Missing JSON data
    """
    """Calculate NDL using an adapted Bühlmann ZH-L16 model.
       time_at_depth_minutes is expected in minutes.
       Inert gas loading is computed from nitrogen and helium.
    """
    # Ensure time_at_depth_minutes is positive to avoid math domain errors
    time_at_depth_minutes = max(0.01, round(time_at_depth_minutes, 2))
    surface_pressure = 1.0
    pressure_at_depth = surface_pressure + (depth / 10)

    # Inert gases for decompression are typically nitrogen and helium.
    inert_gas_fraction = nitrogen_fraction + helium_fraction
    inert_gas_pressure = pressure_at_depth * inert_gas_fraction

    # Log the fractions used.
    print(
        f"Oxygen Fraction: {oxygen_fraction}, Nitrogen Fraction: {nitrogen_fraction}, Helium Fraction: {helium_fraction}")
    print(f"🌊 Depth: {depth}m, 🔺 Pressure: {pressure_at_depth:.2f} ATA, 🧪 Inert Gas Pressure: {inert_gas_pressure:.3f}")

    ndl = float("inf")
    limiting_tissue = None

    for tissue in buhlmann_tissues:
        half_time = tissue["half_time"]
        m_value = tissue["M-value"]
        k = math.log(2) / half_time

        # Calculate inert gas loading in the tissue using the inert gas pressure.
        inert_gas_loading = inert_gas_pressure * (1 - math.exp(-k * time_at_depth_minutes))
        max_inert_tension = m_value * surface_pressure

        print(f"📊 Tissue {tissue['tissue']}: Half-Time {half_time} min, M-Value {m_value}")
        print(f"   → Inert Gas Loading: {inert_gas_loading:.5f}")
        print(f"   → Max Inert Tension: {max_inert_tension:.5f}")

        try:
            # Check for negative or zero result in the logarithm
            log_arg = 1 - (max_inert_tension / inert_gas_pressure)
            if log_arg <= 0:
                print(f"🚨 Log argument <= 0 in tissue {tissue['tissue']}: {log_arg}")
                continue

            compartment_ndl = (math.log(log_arg) / -k) - time_at_depth_minutes
            if compartment_ndl < ndl:
                ndl = compartment_ndl
                limiting_tissue = tissue["tissue"]
                print(f"🔄 New limiting compartment: {tissue['tissue']} (NDL: {ndl:.2f} min)")
        except (ValueError, ZeroDivisionError) as e:
            print(f"🚨 Error in tissue {tissue['tissue']}: {str(e)}")
            continue

    deco_required = False  # Flag to indicate decompression is required

    # Handle extreme values
    if math.isinf(ndl) or ndl > 999:
        ndl = 999
        print(f"⚠️ NDL was infinity or too large, setting to {ndl:.2f} minutes")

    # Allow negative NDL and set deco_required flag
    if ndl < 0:
        deco_required = True
        print(f"⚠️ Negative NDL calculated: {ndl:.2f} minutes. Decompression required.")

    # Apply RGBM adjustment if enabled
    if state.get("use_rgbm_for_ndl", False):
        rgbm_factor = state.get("rgbm_factor", 1)
        if rgbm_factor > 0:
            ndl /= rgbm_factor  # Adjust NDL using RGBM factor
            ndl = round(ndl, 2)  # Keep precision

    print(f"✅ Final Computed NDL: {ndl:.2f} minutes (Limited by Tissue {limiting_tissue})\n")
    # return {"ndl": round(ndl, 2), "deco_required": deco_required}

    return round(ndl, 2)


@app.route('/')
def serve_frontend():
    return send_from_directory('static', 'divalgo.html')


@app.route('/api/v1/reset', methods=['POST'])
def reset():
    """
    Reset the simulation state.
    ---
    tags:
      - Simulation
    produces:
      - application/json
    responses:
      200:
        description: Simulation state reset successfully.
        schema:
          type: object
          properties:
            message:
              type: string
              example: Simulation reset successfully
    """
    global state
    state = {
        "depth": 0,
        "last_depth": 0,
        "time_elapsed": 0,
        "time_at_depth": 0,
        "depth_start_time": time.time(),
        "depth_durations": defaultdict(float),  # Use defaultdict to avoid KeyErrors
        "ndl": -999,
        "rgbm_factor": 1.0,
        "pressure": 1.0,
        "oxygen_toxicity": 0.21,
        "oxygen_fraction": 0.21,
        "nitrogen_fraction": 0.79,
        "helium_fraction": 0.0,
        "selected_deco_model": "bühlmann",
        "use_rgbm_for_ndl": False,
        "dive_start_time": None  # Reset dive_start_time
    }
    return jsonify({"message": "Simulation reset successfully"})


@app.route('/api/v1/oxygen-toxicity-table', methods=['GET'])
def get_oxygen_toxicity_table():
    """
    Retrieve the oxygen toxicity table based on depth.
    ---
    tags:
      - Oxygen Toxicity
    produces:
      - application/json
    responses:
      200:
        description: A JSON array of objects containing oxygen toxicity data for various depths.
        schema:
          type: array
          items:
            type: object
            properties:
              Depth (m):
                type: integer
                description: The depth in meters.
                example: 0
              Absolute Pressure (ATA):
                type: number
                format: float
                description: The calculated absolute pressure in atmospheres.
                example: 1.0
              PPO₂ in Air (bar):
                type: number
                format: float
                description: Partial pressure of oxygen when breathing air.
                example: 0.21
              PPO₂ in 100% O₂ (bar):
                type: number
                format: float
                description: Partial pressure of oxygen when breathing pure oxygen.
                example: 1.0
              Oxygen Toxicity Risk:
                type: string
                description: The assessed risk level based on oxygen toxicity.
                example: Safe
    """
    table = []
    for depth in range(0, 110, 10):
        absolute_pressure = round(1 + (depth / 10), 2)
        ppo2_air = round(absolute_pressure * 0.21, 2)
        ppo2_oxygen = round(absolute_pressure * 1.0, 2)
        if ppo2_oxygen <= 1.6:
            risk_level = "Safe"
        elif 1.6 < ppo2_oxygen <= 2.0:
            risk_level = "Moderate (CNS risk)"
        elif 2.0 < ppo2_oxygen <= 3.0:
            risk_level = "Severe (Convulsions likely)"
        elif 3.0 < ppo2_oxygen <= 5.0:
            risk_level = "High (Extreme CNS risk)"
        else:
            risk_level = "Fatal (Beyond safe limits)"

        table.append({
            "Depth (m)": depth,
            "Absolute Pressure (ATA)": absolute_pressure,
            "PPO₂ in Air (bar)": ppo2_air,
            "PPO₂ in 100% O₂ (bar)": ppo2_oxygen,
            "Oxygen Toxicity Risk": risk_level
        })

    return jsonify(table)


@app.route('/api/v1/set-deco-model', methods=['POST'])
def set_deco_model():
    """
    Set the decompression model.
    ---
    tags:
      - Decompression
    consumes:
      - application/json
    parameters:
      - in: body
        name: body
        description: JSON payload to set the decompression model.
        required: true
        schema:
          type: object
          properties:
            deco_model:
              type: string
              description: The decompression model to set. Valid values buhlmann, rgbm, vpm, deepstops, custom.
              example: rgbm
    responses:
      200:
        description: Decompression model set successfully.
        schema:
          type: object
          properties:
            message:
              type: string
              example: Decompression model set to rgbm
      400:
        description: Invalid decompression model.
        schema:
          type: object
          properties:
            error:
              type: string
              example: Invalid decompression model
    """
    data = request.json
    selected_model = data.get("deco_model")
    if selected_model not in ["bühlmann", "rgbm", "vpm", "deepstops", "custom"]:
        return jsonify({"error": "Invalid decompression model"}), 400
    state["selected_deco_model"] = selected_model
    return jsonify({"message": f"Decompression model set to {selected_model}"}), 200


@app.route('/api/v1//update_gas_mix', methods=['POST'])
def update_gas_mix():
    """
    Update gas mix values and recalculate oxygen toxicity.
    ---
    tags:
      - Gas Mix
    consumes:
      - application/json
    parameters:
      - in: body
        name: body
        description: Gas mix values.
        required: true
        schema:
          type: object
          required:
            - oxygen_fraction
            - nitrogen_fraction
            - helium_fraction
          properties:
            oxygen_fraction:
              type: number
              description: Oxygen fraction.
              example: 0.21
              minimum: 0.0
              maximum: 1.0
            nitrogen_fraction:
              type: number
              description: Nitrogen fraction.
              example: 0.79
              minimum: 0.0
              maximum: 1.0
            helium_fraction:
              type: number
              description: Helium fraction.
              example: 0.0
              minimum: 0.0
              maximum: 1.0
    responses:
      200:
        description: Gas mix updated successfully.
        schema:
          type: object
          properties:
            message:
              type: string
              example: Gas mix updated
            oxygen_fraction:
              type: number
              format: float
              example: 0.30
            nitrogen_fraction:
              type: number
              format: float
              example: 0.60
            helium_fraction:
              type: number
              format: float
              example: 0.10
            oxygen_toxicity:
              type: number
              format: float
              example: 1.50
      400:
        description: No JSON data received or invalid input.
        schema:
          type: object
          properties:
            error:
              type: string
              example: No JSON data received
      500:
        description: Internal server error.
        schema:
          type: object
          properties:
            error:
              type: string
              example: Internal server error
            message:
              type: string
              example: Detailed error message
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON data received"}), 400

        # Validate that required keys exist and are valid numbers
        try:
            oxygen_fraction = float(data.get("oxygen_fraction", state.get("oxygen_fraction", 0.21)))
            nitrogen_fraction = float(data.get("nitrogen_fraction", state.get("nitrogen_fraction", 0.79)))
            helium_fraction = float(data.get("helium_fraction", state.get("helium_fraction", 0.0)))
        except (TypeError, ValueError):
            return jsonify({"error": "Invalid or missing gas mix values"}), 400
        # Validate that gas fractions sum to 1.0 (or very close to 1.0 accounting for floating point errors)
        total = oxygen_fraction + nitrogen_fraction + helium_fraction
        if not (0.999 <= total <= 1.001):
            # Normalize if needed
            factor = 1.0 / total
            oxygen_fraction *= factor
            nitrogen_fraction *= factor
            helium_fraction *= factor

        # Update state
        state["oxygen_fraction"] = round(oxygen_fraction, 5)
        state["nitrogen_fraction"] = round(nitrogen_fraction, 5)
        state["helium_fraction"] = round(helium_fraction, 5)

        # Recalculate oxygen toxicity based on new gas mix
        state["oxygen_toxicity"] = round(state["oxygen_fraction"] * state["pressure"], 2)

        print(f"Updated gas mix: O₂={oxygen_fraction}, N₂={nitrogen_fraction}, He={helium_fraction}")
        return jsonify({
            "message": "Gas mix updated",
            "oxygen_fraction": state["oxygen_fraction"],
            "nitrogen_fraction": state["nitrogen_fraction"],
            "helium_fraction": state["helium_fraction"],
            "oxygen_toxicity": state["oxygen_toxicity"]
        })
    except Exception as e:
        print(f"Error updating gas mix: {str(e)}")
        traceback.print_exc()
        return jsonify({"error": "Internal server error", "message": str(e)}), 500


def background_state_update():
    while True:
        update_tissue_state()
        # Optionally update other state values...
        time.sleep(1)  # Update every second


# In-memory store for demonstration purposes
physiology_store = {}


@app.route('/api/v1/update_physiology', methods=['POST'])
def update_physiology():
    """
    Update physiology data for a given client.
    ---
    tags:
      - Physiology
    consumes:
      - application/json
    parameters:
      - name: Client-UUID
        in: header
        type: string
        required: true
        description: Unique identifier for the client.
      - name: body
        in: body
        required: true
        description: JSON payload containing the physiology data.
        schema:
          type: object
          # Define expected fields if known; otherwise, allow additional properties.
          properties:
            heart_rate:
              type: integer
              description: The client’s heart rate.
              example: 70
            blood_pressure:
              type: string
              description: The client’s blood pressure reading.
              example: "120/80"
          additionalProperties: true
    responses:
      200:
        description: Physiology data updated successfully.
        schema:
          type: object
          properties:
            status:
              type: string
              example: success
            message:
              type: string
              example: Physiology data updated
            data:
              type: object
              description: The updated physiology data.
      400:
        description: Missing Client-UUID header or invalid/missing JSON data.
        schema:
          type: object
          properties:
            status:
              type: string
              example: error
            message:
              type: string
              example: Missing Client-UUID header
    """
    # Retrieve the Client-UUID from the headers
    client_uuid = request.headers.get('Client-UUID')
    if not client_uuid or "\x00" in client_uuid:
        return jsonify({"status": "error", "message": "Missing or invalid Client-UUID header"}), 400

    # Get the JSON data from the request
    data = request.get_json()
    if not data:
        return jsonify({"status": "error", "message": "Invalid or missing JSON data"}), 400

    # Log the received data
    app.logger.info(f"Received physiology data from client {client_uuid}: {data}")

    # Optionally, update a global store (or database) keyed by the client UUID
    physiology_store[client_uuid] = data

    # Return a success response with the data that was received
    response_data = {
        "status": "success",
        "message": "Physiology data updated",
        "data": data
    }
    return jsonify(response_data), 200


if __name__ == '__main__':
    threading.Thread(target=background_state_update, daemon=True).start()

    app.run(debug=True)
