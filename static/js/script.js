// ----- Global Variables & Initialization -----
let startTime = Date.now();
let depthStartTime = Date.now();

// Generate a unique client UUID
const clientUUID = generateUUID();
console.log("Generated Client UUID:", clientUUID);

// Common headers for API requests
const headers = {
  "Client-UUID": clientUUID,
  "Content-Type": "application/json"
};

// Global diver state (and gas mix properties)
let state = {
  oxygen_fraction: 0.21, // default Air
  nitrogen_fraction: 0.79, // default Air
  // ... other diver state properties are updated elsewhere
};

// ----- Timer Functions -----
function updateTimers() {
  const elapsedTime = Math.floor((Date.now() - startTime) / 1000);
  const timeAtDepth = Math.floor((Date.now() - depthStartTime) / 1000);
  const timeEl = document.getElementById("time");
  const depthTimeEl = document.getElementById("depth-time");
  if (timeEl) timeEl.innerText = elapsedTime;
  if (depthTimeEl) depthTimeEl.innerText = timeAtDepth;
  fetchNDL();
}
setInterval(updateTimers, 1000);

// ----- Utility: UUID Generation -----
function generateUUID() {
  if (window.crypto && crypto.randomUUID) {
    return crypto.randomUUID(); // Modern browsers
  } else {
    // Fallback method
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
      let r = Math.random() * 16 | 0,
          v = c === 'x' ? r : (r & 0x3 | 0x8);
      return v.toString(16);
    });
  }
}

// ----- API Functions -----
async function fetchState() {
  try {
    const response = await fetch("/state", { headers });
    const data = await response.json();
    updateDiverDisplay(data);
  } catch (error) {
    console.error("Error fetching state:", error);
  }
}
fetchState(); // Call on page load

async function dive() {
  try {
    const response = await fetch("/dive", {
      method: "POST",
      headers: {
        "Client-UUID": clientUUID,
        "Content-Type": "application/json"
      }
    });
    const data = await response.json();
    console.log("Diving:", data);
    updateDiverDisplay(data);
    logDiveData(data);
  } catch (error) {
    console.error("Error diving:", error);
  }
}

async function ascend() {
  try {
    const response = await fetch("/ascend", {
      method: "POST",
      headers: {
        "Client-UUID": clientUUID,
        "Content-Type": "application/json"
      }
    });
    const data = await response.json();
    console.log("Ascending:", data);
    updateDiverDisplay(data);
    logDiveData(data);
  } catch (error) {
    console.error("Error ascending:", error);
  }
}

async function fetchLogs() {
  try {
    const response = await fetch("/logs", {
      method: "GET",
      headers
    });
    const data = await response.json();
    console.log("Logs:", data);
  } catch (error) {
    console.error("Error fetching logs:", error);
  }
}

async function sendRequest(endpoint, method = "GET", body = null) {
  const options = { method, headers };
  if (body) options.body = JSON.stringify(body);
  const response = await fetch(endpoint, options);
  return response.json();
}

// ----- UI Update Functions -----
let previousDepth = null;
const oceanHeight = 400;
let maxDepth = 100;

function updateDiverDisplay(data) {
  if (!data) return;

  const depthEl = document.getElementById("depth");
  const pressureEl = document.getElementById("pressure");
  const toxicityEl = document.getElementById("toxicity");
  const ndlEl = document.getElementById("ndl");
  const rgbmEl = document.getElementById("rgbm");

  if (depthEl) depthEl.innerText = data.depth;
  if (pressureEl) pressureEl.innerText = data.pressure.toFixed(2);
  if (toxicityEl) toxicityEl.innerText = data.oxygen_toxicity.toFixed(4);
  if (ndlEl) ndlEl.innerText = data.ndl.toFixed(2);

  // For RGBM, if at surface (depth === 0) use default value
  if (rgbmEl) {
    if (data.depth === 0) {
      rgbmEl.innerText = "1.00";
    } else {
      rgbmEl.innerText = data.rgbm_factor.toFixed(5);
    }
  }

  // Reset the depth timer if the depth has changed
  if (data.depth !== previousDepth) {
    depthStartTime = Date.now();
    previousDepth = data.depth;
  }

  // Animate diver image movement
  const diver = document.getElementById("diver");
  if (diver) {
    const newPosition = (data.depth / maxDepth) * oceanHeight;
    diver.style.transition = "top 1s ease-in-out";
    diver.style.top = `${newPosition}px`;
  }
}

function logDiveData(data) {
  const logList = document.getElementById("dive-log");
  const logEntry = document.createElement("li");
  logEntry.textContent = `Depth: ${data.depth} m | Pressure: ${data.pressure.toFixed(2)} atm | Oxygen Toxicity: ${data.oxygen_toxicity.toFixed(2)} PO₂ | NDL: ${data.ndl.toFixed(2)} min | RGBM Factor: ${data.rgbm_factor.toFixed(2)} | Time Elapsed: ${document.getElementById("time").innerText} | Time at Depth: ${document.getElementById("depth-time").innerText}`;
  if (logList) logList.appendChild(logEntry);
  fetchStateAndUpdate();
}

function resetSimulation() {
  fetch('/reset', { method: "POST" })
    .then(() => {
      const logList = document.getElementById("dive-log");
      if (logList) logList.innerHTML = "";
      updateDiverDisplay({
        depth: 0,
        pressure: 1,
        oxygen_toxicity: 0.21,
        ndl: 99,
        rgbm_factor: 1.0,
      });
      const diver = document.getElementById("diver");
      if (diver) diver.style.top = "0px";
      startTime = Date.now();
      depthStartTime = Date.now();
    })
    .catch(error => console.error("Error resetting simulation:", error));
}

// ----- Modal for Oxygen Toxicity Table -----
const infoButton = document.getElementById("info-btn");
const modal = document.getElementById("toxicity-modal");
const closeModal = document.querySelector(".close-btn");

if (infoButton) {
  infoButton.onclick = function() {
    fetchOxygenToxicityTable();
    modal.style.display = "flex";
  };
}

if (closeModal) {
  closeModal.onclick = function() {
    modal.style.display = "none";
  };
}

window.onclick = function(event) {
  if (event.target === modal) {
    modal.style.display = "none";
  }
};

async function fetchOxygenToxicityTable() {
  try {
    const response = await fetch("/oxygen-toxicity-table");
    const tableData = await response.json();
    let tbody = document.querySelector("#toxicity-table tbody");
    if (!tbody) {
      tbody = document.createElement("tbody");
      document.getElementById("toxicity-table").appendChild(tbody);
    }
    tbody.innerHTML = "";
    tableData.forEach(row => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${row["Depth (m)"]}</td>
        <td>${row["Absolute Pressure (ATA)"]}</td>
        <td>${row["PPO₂ in Air (bar)"]}</td>
        <td>${row["PPO₂ in 100% O₂ (bar)"]}</td>
        <td>${row["Oxygen Toxicity Risk"]}</td>
      `;
      tbody.appendChild(tr);
    });
  } catch (error) {
    console.error("Error fetching oxygen toxicity table:", error);
  }
}

// ----- Dynamic Page Rendering for NDL & Graphs -----
function renderNDLPage(state) {
  return `
    <div id="ndl-page" class="tab-content">
      <h3>Bühlmann ZH-L16 Decompression Model</h3>
      <div class="ndl-output">
        <p><strong>Current NDL:</strong> <span id="ndl-value">${state.ndl.toFixed(2)}</span> minutes</p>
      </div>
      <table>
        <thead>
          <tr>
            <th>Tissue Compartment</th>
            <th>Half-Time (min)</th>
            <th>M-Value</th>
          </tr>
        </thead>
        <tbody id="compartment-table">
          ${state.buhlmann_ndl.compartments.map(compartment => `
            <tr>
              <td>${compartment.tissue}</td>
              <td>${compartment.half_time}</td>
              <td>${compartment["M-value"]}</td>
            </tr>
          `).join('')}
        </tbody>
      </table>
      <button id="calculate-deco-btn" style="margin-top: 10px;">Calculate Decompression Stops</button>
      <div id="deco-output"></div>
    </div>
  `;
}

function fetchStateAndEnableRGBM() {
    fetch('/state')
    .then(response => response.json())
    .then(state => {
        document.getElementById("ndl-value").textContent = state.ndl.toFixed(2);

        // Enable RGBM checkbox only if state has loaded
        let rgbmCheckbox = document.getElementById("rgbm-checkbox");
        rgbmCheckbox.disabled = false;  // Enable checkbox after state loads
        rgbmCheckbox.checked = state.use_rgbm_for_ndl || false;  // Set checkbox state properly

        console.log("State Loaded:", state);
    })
    .catch(error => console.error("Error fetching state:", error));
}

// Function to toggle RGBM setting
function toggleRGBM() {
    console.log("toggleRGBM");
    let rgbmCheckbox = document.getElementById("rgbm-checkbox");
    let useRGBM = rgbmCheckbox.checked; // Get the current state from the UI

    fetch('/toggle-rgbm-ndl', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ use_rgbm: useRGBM }) // Send the updated state
    })
    .then(response => response.json())
    .then(data => {
        console.log("RGBM NDL Toggle Updated:", data);
        // Do NOT fetch state immediately to prevent overwriting the checkbox
    })
    .catch(error => console.error("Error:", error));
}

// Call this function when the page loads
//window.onload = function () {
//    fetchStateAndEnableRGBM();
//    document.getElementById("rgbm-checkbox").addEventListener("change", toggleRGBM);
//};
//
//
//// Call this function when the page loads
//window.onload = function () {
//    fetchStateAndEnableRGBM();
//};


// Call this function when the page loads
window.onload = function () {
    fetchStateAndEnableRGBM();
};


function renderGraphPage() {
  return `
    <div id="graph-page" class="tab-content" style="display: none;">
      <h3>Dive Analysis Graphs</h3>
      <canvas id="diveGraph"></canvas>
    </div>
  `;
}

function updateNDLContainer(state) {
  const dynamicPages = document.getElementById("dynamic-pages");
  // Render both the NDL page and Graph page
  dynamicPages.innerHTML = renderNDLPage(state) + renderGraphPage();
  // Ensure the NDL page is visible by default
  document.getElementById("ndl-page").style.display = "block";
  const decoBtn = document.getElementById("calculate-deco-btn");
  if (decoBtn) {
    decoBtn.addEventListener("click", fetchDecoStops);
  }
}

// ----- Tab Navigation -----
function openTab(evt, tabName) {
  const tabContents = document.getElementsByClassName("tab-content");
  for (let i = 0; i < tabContents.length; i++) {
    tabContents[i].style.display = "none";
  }
  const tabButtons = document.getElementsByClassName("tab-btn");
  for (let i = 0; i < tabButtons.length; i++) {
    tabButtons[i].classList.remove("active");
  }
  const targetTab = document.getElementById(tabName);
  if (targetTab) {
    targetTab.style.display = "block";
  } else {
    console.error("Tab not found: " + tabName);
  }
  evt.currentTarget.classList.add("active");
}

// ----- Decompression Stops Calculation -----
function fetchDecoStops() {
  const ndl = parseFloat(document.getElementById("ndl-value").innerText);
  const depth = parseFloat(document.getElementById("depth").innerText);
  const pressure = parseFloat(document.getElementById("pressure").innerText);
  const oxygen_toxicity = parseFloat(document.getElementById("toxicity").innerText);
  const rgbm_factor = parseFloat(document.getElementById("rgbm").innerText);
  const time_elapsed = parseInt(document.getElementById("time").innerText, 10);
  const time_at_depth = parseInt(document.getElementById("depth-time").innerText, 10);

  if (isNaN(ndl) || isNaN(depth) || isNaN(pressure) || isNaN(oxygen_toxicity)) {
    console.error("❌ Error: One or more values are invalid. Check UI elements.");
    return;
  }

  console.log("📡 Sending request with:");
  console.log("   NDL:", ndl, "min");
  console.log("   Depth:", depth, "m");
  console.log("   Pressure:", pressure, "atm");
  console.log("   Oxygen Toxicity:", oxygen_toxicity, "PO₂");
  console.log("   RGBM Factor:", rgbm_factor);
  console.log("   Time Elapsed:", time_elapsed, "sec");
  console.log("   Time at Depth:", time_at_depth, "sec");

  fetch('/calculate_ndl_stops', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Client-UUID': clientUUID
    },
    body: JSON.stringify({
      ndl,
      depth,
      pressure,
      oxygen_toxicity,
      rgbm_factor,
      time_elapsed,
      time_at_depth
    })
  })
    .then(response => response.json())
    .then(data => {
      console.log("✅ Response received:", data);
      const decoOutput = document.getElementById("deco-output");
      decoOutput.innerHTML = "<h4>Decompression Stops:</h4>";
      if (!data.stops || data.stops.length === 0) {
        decoOutput.innerHTML += "<p>No decompression required.</p>";
      } else {
        let stopList = "<ul>";
        data.stops.forEach(stop => {
          if (stop.warning) {
            stopList += `<li style="color: red;">⚠️ ${stop.warning}</li>`;
          } else {
            stopList += `<li>📍 Stop at <strong>${stop.depth}m</strong> for <strong>${stop.duration} min</strong> (${stop.reason})</li>`;
          }
        });
        stopList += "</ul>";
        decoOutput.innerHTML += stopList;
      }
    })
    .catch(error => {
      console.error("❌ Error fetching decompression stops:", error);
      document.getElementById("deco-output").innerHTML = "<p style='color: red;'>Error calculating decompression stops.</p>";
    });
}

// ----- NDL Value Animation -----
function updateNDL(ndlValue) {
  const ndlElement = document.getElementById("ndl-value");
  const outputContainer = document.querySelector(".ndl-output");
  if (ndlElement) ndlElement.innerText = ndlValue.toFixed(2);
  if (outputContainer) {
    outputContainer.classList.add("updated");
    setTimeout(() => outputContainer.classList.remove("updated"), 1000);
  }
}

// ----- Fetch NDL Data -----
function fetchNDL() {
  fetch('/state')
    .then(response => response.json())
    .then(state => {
        try {
          if (document.getElementById("ndl-value")) {
            document.getElementById("ndl-value").textContent = state.ndl?.toFixed(2) ?? "N/A";
          } else {
            console.warn("❌ Element with ID 'ndl-value' not found.");
          }

          if (document.getElementById("ndl")) {
            document.getElementById("ndl").textContent = state.accumulated_ndl?.toFixed(2) ?? "N/A";
          } else {
            console.warn("❌ Element with ID 'ndl' not found.");
          }

          if (document.getElementById("rgbm")) {
            document.getElementById("rgbm").textContent = state.rgbm_factor?.toFixed(2) ?? "N/A";
          } else {
            console.warn("❌ Element with ID 'rgbm' not found.");
          }

          if (document.getElementById("oxygen_toxicity")) {
            document.getElementById("oxygen_toxicity").textContent = state.oxygen_toxicity?.toFixed(2) ?? "N/A";
          } else {
            console.warn("❌ Element with ID 'oxygen_toxicity' not found.");
          }
        } catch (error) {
          console.error("🚨 Error updating UI elements:", error);
        }
    })
    .catch(error => console.error("Error fetching NDL:", error));
}

// ----- DOMContentLoaded: Attach Listeners & Initialize -----
document.addEventListener("DOMContentLoaded", function () {
  console.log("✅ Page loaded, initializing event listeners...");

  // Attach change listener for decompression model
  const decoModel = document.getElementById("deco-model");
  if (decoModel) {
    decoModel.addEventListener("change", function () {
      // Show/hide dynamic RGBM options based on selected value
      const rgbmOptions = document.getElementById("rgbm-options");
      if (rgbmOptions) {
        rgbmOptions.style.display = this.value === "rgbm" ? "block" : "none";
      }

      // Send selected model to backend
      fetch("/set-deco-model", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ deco_model: this.value }),
      })
        .then((response) => {
          if (!response.ok) {
            throw new Error(`HTTP error! Status: ${response.status}`);
          }
          return response.json();
        })
        .then((data) => {
          console.log(data.message);
          fetchStateAndUpdate();
        })
        .catch((error) =>
          console.error("Error setting decompression model:", error)
        );
    });
  } else {
    console.error("❌ Decompression model dropdown (ID: 'deco-model') not found.");
  }

  // Preselect the Air card if not already marked (optional if already set in HTML)
  const airCard = document.querySelector(".gas-card.selected");
  if (!airCard) {
    const firstCard = document.querySelector(".gas-card");
    if (firstCard) firstCard.classList.add("selected");
  }

  // Update O₂/N₂ values based on the selected gas card
  updateGasValues();

  // Fetch initial state and update dynamic pages
  fetchStateAndUpdate();

  console.log("✅ All event listeners attached successfully!");
});

function updateGasValues() {
  const selectedCard = document.querySelector('.gas-card.selected');
  if (selectedCard) {
    const gasLabel = selectedCard.querySelector("span").innerText.trim();
    let o2Value, n2Value, heValue;
    switch(gasLabel) {
      case "Air":
        o2Value = 0.21;
        n2Value = 0.79;
        heValue = 0.00;
        break;
      case "EANx32":
        o2Value = 0.32;
        n2Value = 0.68;
        heValue = 0.00;
        break;
      case "EANx36":
        o2Value = 0.36;
        n2Value = 0.64;
        heValue = 0.00;
        break;
      case "EANx40":
      case "Enriched":
        o2Value = 0.40;
        n2Value = 0.60;
        heValue = 0.00;
        break;
      case "Trimix":
        o2Value = 0.18;
        n2Value = 0.45;
        heValue = 0.37;
        break;
      case "Rebreather":
        o2Value = 0.30;
        n2Value = 0.70;
        heValue = 0.00;
        break;
      default:
        o2Value = 0.21;
        n2Value = 0.79;
        heValue = 0.00;
    }
    // Update UI elements
    if (document.getElementById("o2")) {
      document.getElementById("o2").textContent = o2Value.toFixed(2);
    }
    if (document.getElementById("n2")) {
      document.getElementById("n2").textContent = n2Value.toFixed(2);
    }
    if (document.getElementById("he")) {
      document.getElementById("he").textContent = heValue.toFixed(2);
    }
    // Update global state (local JS copy)
    state.oxygen_fraction = o2Value;
    state.nitrogen_fraction = n2Value;
    state.helium_fraction = heValue;
    console.log(`Updated gas mix to ${gasLabel}: O₂ = ${o2Value}, N₂ = ${n2Value}, He = ${heValue}`);

    // Send updated gas mix values to Flask backend
    fetch('/update_gas_mix', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Client-UUID': clientUUID
      },
      body: JSON.stringify({
        oxygen_fraction: o2Value,
        nitrogen_fraction: n2Value,
        helium_fraction: heValue
      })
    })
    .then(response => response.json())
    .then(data => {
      console.log("Gas mix updated on server:", data);
      fetchStateAndUpdate();
    })
    .catch(error => {
      console.error("Error updating gas mix on server:", error);
    });
  }
}


// ----- Fetch State & Update Dynamic Pages -----
let isFetchingState = false;
function fetchStateAndUpdate() {
  if (isFetchingState) return;
  isFetchingState = true;
  fetch('/state')
    .then(response => response.json())
    .then(state => {
      updateNDLContainer(state);
      if (document.getElementById("ndl-value"))
        document.getElementById("ndl-value").textContent = state.ndl.toFixed(2);
    })
    .catch(error => console.error("Error fetching state:", error))
    .finally(() => { isFetchingState = false; });
}

// ----- Gas Mixture Card Selection -----
const gasCards = document.querySelectorAll('.gas-card');
gasCards.forEach(card => {
  card.addEventListener('click', () => {
    gasCards.forEach(c => c.classList.remove('selected'));
    card.classList.add('selected');
    updateGasValues();
  });
});

// ----- Button Click Handlers -----
document.getElementById("dive-btn").onclick = dive;
document.getElementById("ascend-btn").onclick = ascend;
document.getElementById("reset-btn").onclick = resetSimulation;
document.getElementById("rgbm-checkbox").onclick = toggleRGBM;
