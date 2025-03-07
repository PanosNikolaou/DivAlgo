from flask import Flask, jsonify, request, send_from_directory
import os
import json
from datetime import datetime
import math
import time
from collections import defaultdict
import traceback
from flasgger import Swagger

app = Flask(__name__)
swagger = Swagger(app)

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

# Global dive log (in-memory) for debugging
dive_log = []


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


def get_log_filename(client_uuid):
    log_dir = "static/logs"
    os.makedirs(log_dir, exist_ok=True)
    return os.path.join(log_dir, f"dive_log_{client_uuid}.json")


def ensure_log_file(client_uuid):
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


def load_dive_logs(client_uuid):
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


def save_dive_log(client_uuid, entry):
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

    print(
        f"📝 Saved Log Entry: Depth={entry['depth']}m, Time at Depth={entry['time_at_depth']} sec, RGBM={entry['rgbm_factor']:.5f}")
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
    "ndl": 60,
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


def calculate_accumulated_ndl():
    """
    Calculate the accumulated NDL using the Bühlmann decompression model equations.

    For each tissue compartment, the tissue tension is updated using:
        P(t) = P_A + (P(0) - P_A) * exp(-k*t)
    where k = ln(2)/half_time and P_A is the ambient pressure at the compartment's depth.

    When the tissue compartment includes Bühlmann coefficients (a and b), the maximum allowed
    tissue tension is:
        P_max = (P_A - a) / b
    and the additional time Δt allowed is obtained by solving:
        P_A - (P_A - P_current) * exp(-k*Δt) = P_max,
    which yields:
        Δt = -1/k * ln((P_A - P_max) / (P_A - P_current))

    Negative Δt values indicate that the tissue is already over its limit.
    If a and b are not provided, a simplified approach using an M-value is used.
    """
    # Initialize tissue gas tensions for each compartment (starting at 0)
    tissue_tensions = {tissue["tissue"]: 0.0 for tissue in buhlmann_tissues}
    surface_pressure = 1.0

    # Process each dive log entry sequentially.
    for entry in dive_log:
        # Support both "depth" and "Depth", similarly for time at depth.
        d = float(entry.get("depth", entry.get("Depth", 0)))
        t_sec = float(entry.get("time_at_depth", entry.get("Time at Depth", 0)))
        t_min = t_sec / 60.0  # Convert seconds to minutes

        # Calculate ambient pressure at the segment's depth.
        pressure_at_depth = surface_pressure + (d / 10)
        inert_gas_pressure = pressure_at_depth * (state.get("nitrogen_fraction", 0.79) +
                                                    state.get("helium_fraction", 0.0))
        # Update each tissue compartment tension using exponential uptake:
        for tissue in buhlmann_tissues:
            tissue_id = tissue["tissue"]
            half_time = tissue["half_time"]
            k = math.log(2) / half_time
            P_old = tissue_tensions[tissue_id]
            # Equation: P(t) = P_A + (P(0) - P_A) * exp(-k*t)
            P_new = inert_gas_pressure + (P_old - inert_gas_pressure) * math.exp(-k * t_min)
            tissue_tensions[tissue_id] = P_new

    # Calculate the additional time (NDL) allowed at the current depth for each tissue.
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
            P_max = (ambient_pressure - a) / b
            numerator = ambient_pressure - P_max
            denominator = ambient_pressure - current_tension
            if denominator == 0:
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
            if denominator == 0:
                ndl = 0
            else:
                try:
                    ratio = numerator / denominator
                    ndl = -1 / k * math.log(ratio)
                except Exception:
                    ndl = 0
        ndl_values.append(ndl)

    # Combine negative NDL values if any exist, otherwise use the smallest positive value.
    negatives = [ndl for ndl in ndl_values if ndl < 0]
    if negatives:
        accumulated_ndl = sum(negatives)
    else:
        accumulated_ndl = min(ndl_values) if ndl_values else 0
    return round(accumulated_ndl, 2)


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


@app.route('/calculate_ndl_stops', methods=['POST'])
def calculate_ndl_stops():
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
              f"RGBM={rgbm_factor}, Time Elapsed={time_elapsed}, Time at Depth={time_at_depth}, O2={oxygen_fraction}, N₂={nitrogen_fraction}, He={helium_fraction}")

        stops = generate_decompression_stops(ndl, depth, pressure, oxygen_toxicity, rgbm_factor, time_elapsed,
                                             time_at_depth)
        return jsonify({"stops": stops})

    except Exception as e:
        print(f"❌ Error processing request: {str(e)}")
        traceback.print_exc()
        return jsonify({"error": "Internal server error", "message": str(e)}), 500


def generate_decompression_stops(ndl, depth, pressure, oxygen_toxicity, rgbm_factor, time_elapsed, time_at_depth):
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


@app.route('/dive', methods=['POST'])
def dive():
    client_uuid = request.headers.get("Client-UUID")
    if not client_uuid:
        return jsonify({"error": "Missing Client-UUID"}), 400

    if 0 <= state["depth"] < 350:
        update_time_at_depth()
        state["last_depth"] = state["depth"]
        state["depth"] += 10
        state["depth_start_time"] = time.time()
        state["time_at_depth"] = state["depth_durations"][state["depth"]]  # No need for .get() with defaultdict

        # Calculate NDL with proper time conversion (seconds to minutes)
        state["ndl"] = calculate_ndl(state["depth"], state["time_at_depth"] / 60)
        state["pressure"] = round(1 + (state["depth"] / 10), 2)
        state["oxygen_toxicity"] = round(state["oxygen_fraction"] * state["pressure"],
                                         2)  # Fixed to use oxygen_fraction
        state["rgbm_factor"] = calculate_rgbm()

        log_entry = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "depth": state["depth"],
            "pressure": state["pressure"],
            "oxygen_toxicity": state["oxygen_toxicity"],
            "ndl": state["ndl"],
            "rgbm_factor": state["rgbm_factor"],
            "total_time": round(state["time_elapsed"], 2),
            "time_at_depth": round(state["time_at_depth"], 2)
        }
        save_dive_log(client_uuid, log_entry)

    return jsonify(state)


@app.route('/ascend', methods=['POST'])
def ascend():
    client_uuid = request.headers.get("Client-UUID")
    if not client_uuid:
        return jsonify({"error": "Missing Client-UUID"}), 400

    if state["depth"] > 0:
        update_time_at_depth()
        state["last_depth"] = state["depth"]
        state["depth"] -= 10
        if state["depth"] < 0:
            state["depth"] = 0
        state["depth_start_time"] = time.time()
        state["time_at_depth"] = state["depth_durations"][state["depth"]]  # No need for .get() with defaultdict

        state["ndl"] = calculate_ndl(state["depth"], state["time_at_depth"] / 60)
        state["pressure"] = round(1 + (state["depth"] / 10), 2)
        state["oxygen_toxicity"] = round(state["oxygen_fraction"] * state["pressure"],
                                         2)  # Fixed to use oxygen_fraction
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


@app.route('/logs', methods=['GET'])
def get_logs():
    client_uuid = request.headers.get("Client-UUID")
    if not client_uuid:
        return jsonify({"error": "Missing Client-UUID"}), 400

    logs = load_dive_logs(client_uuid)
    print(f"Loaded logs: {logs}")
    return jsonify(logs)


@app.route('/state', methods=['GET'])
def get_state():
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
    ndl_value = calculate_ndl(depth, time_at_depth_min, oxygen_fraction, nitrogen_fraction, helium_fraction)
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
        "accumulated_ndl": accumulated_ndl,  # New field for accumulated NDL
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


@app.route('/toggle-rgbm-ndl', methods=['POST'])
def toggle_rgbm_ndl():
    data = request.json
    state["use_rgbm_for_ndl"] = data.get("use_rgbm", False)
    return jsonify({"message": f"RGBM-based NDL calculation {'enabled' if state['use_rgbm_for_ndl'] else 'disabled'}"})


def calculate_ndl(depth, time_at_depth_minutes, oxygen_fraction=0.21, nitrogen_fraction=0.79, helium_fraction=0.0):
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

    # print(f"✅ Final Computed NDL: {ndl:.2f} minutes (Limited by Tissue {limiting_tissue})\n")
    # return {"ndl": round(ndl, 2), "deco_required": deco_required}

    return round(ndl, 2)


@app.route('/')
def serve_frontend():
    return send_from_directory('static', 'diveplanner.html')


@app.route('/reset', methods=['POST'])
def reset():
    global state
    state = {
        "depth": 0,
        "last_depth": 0,
        "time_elapsed": 0,
        "time_at_depth": 0,
        "depth_start_time": time.time(),
        "depth_durations": defaultdict(float),  # Use defaultdict to avoid KeyErrors
        "ndl": 60,
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


@app.route('/oxygen-toxicity-table', methods=['GET'])
def get_oxygen_toxicity_table():
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


@app.route('/set-deco-model', methods=['POST'])
def set_deco_model():
    data = request.json
    selected_model = data.get("deco_model")
    if selected_model not in ["bühlmann", "rgbm", "vpm", "deepstops", "custom"]:
        return jsonify({"error": "Invalid decompression model"}), 400
    state["selected_deco_model"] = selected_model
    return jsonify({"message": f"Decompression model set to {selected_model}"}), 200


@app.route('/update_gas_mix', methods=['POST'])
def update_gas_mix():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON data received"}), 400

        # Get new gas mix values
        oxygen_fraction = float(data.get("oxygen_fraction", state.get("oxygen_fraction", 0.21)))
        nitrogen_fraction = float(data.get("nitrogen_fraction", state.get("nitrogen_fraction", 0.79)))
        helium_fraction = float(data.get("helium_fraction", state.get("helium_fraction", 0.0)))

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


if __name__ == '__main__':
    # Uncomment the following lines to run background updates if needed:
    # threading.Thread(target=auto_update_rgbm, daemon=True).start()
    # threading.Thread(target=auto_update_state, daemon=True).start()
    app.run(debug=True)