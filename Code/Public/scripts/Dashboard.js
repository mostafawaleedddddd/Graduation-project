let cameras = [];
const cameraPipelines = {};
let currentCameraId = null;
let currentUserEmail = null;

const cameraSelect = document.getElementById("cameraSelect");
const cameraDropdownToggle = document.getElementById("cameraDropdownToggle");
const cameraDropdownLabel = document.getElementById("cameraDropdownLabel");
const cameraDropdownMenu = document.getElementById("cameraDropdownMenu");
const liveFeedImage = document.getElementById("live-feed");
const liveFeedPlaceholder = document.getElementById("liveFeedPlaceholder");
const liveFeedSubtext = document.getElementById("liveFeedSubtext");

function setCameraDropdownLabel(label = "Select Camera") {
  cameraDropdownLabel.textContent = label;
}

function closeCameraDropdown() {
  cameraDropdownMenu.classList.remove("show");
  cameraDropdownToggle.setAttribute("aria-expanded", "false");
}

function openCameraDropdown() {
  cameraDropdownMenu.classList.add("show");
  cameraDropdownToggle.setAttribute("aria-expanded", "true");
}

function renderCameraDropdown() {
  cameraSelect.innerHTML = '<option value="">Select Camera</option>';
  cameraDropdownMenu.innerHTML = "";

  if (cameras.length === 0) {
    const emptyState = document.createElement("div");
    emptyState.className = "camera-dropdown-empty";
    emptyState.textContent = "No cameras added yet";
    cameraDropdownMenu.appendChild(emptyState);
    return;
  }

  cameras.forEach(camera => {
    const option = document.createElement("option");
    option.value = camera.url;
    option.dataset.cameraId = camera.name;
    option.textContent = camera.name;
    cameraSelect.appendChild(option);

    const item = document.createElement("div");
    item.className = "camera-dropdown-item";

    const selectButton = document.createElement("button");
    selectButton.type = "button";
    selectButton.className = "camera-dropdown-select";
    selectButton.textContent = camera.name;
    selectButton.addEventListener("click", () => {
      cameraSelect.value = camera.url;
      setCameraDropdownLabel(camera.name);
      closeCameraDropdown();
      cameraSelect.dispatchEvent(new Event("change"));
    });

    const deleteButton = document.createElement("button");
    deleteButton.type = "button";
    deleteButton.className = "delete-btn camera-delete-btn";
    deleteButton.innerHTML = "&times;";
    deleteButton.title = `Delete ${camera.name}`;
    deleteButton.setAttribute("aria-label", `Delete ${camera.name}`);
    deleteButton.addEventListener("click", event => {
      event.stopPropagation();
      promptDeleteCamera(camera.name);
    });

    item.appendChild(selectButton);
    item.appendChild(deleteButton);
    cameraDropdownMenu.appendChild(item);
  });
}

function openAddCamera() {
  modal.classList.add("show");
}

function closeAddCamera() {
  modal.classList.remove("show");
  document.getElementById("cameraName").value = "";
  document.getElementById("cameraUrl").value = "";
}

function showLiveFeedPlaceholder(title, message) {
  if (currentSplitMode > 1) return; // don't interfere with split mode
  liveFeedPlaceholder.querySelector(".live-feed-placeholder-title").textContent = title;
  liveFeedPlaceholder.querySelector(".live-feed-placeholder-text").textContent = message;
  liveFeedPlaceholder.classList.add("show");
  liveFeedImage.classList.remove("is-active");
  liveFeedImage.removeAttribute("src");
  liveFeedSubtext.textContent = message;
}

function sendAlertEmailToPython(email) {
  if (!email) {
    console.warn('sendAlertEmailToPython called without an email.');
    return;
  }

  fetch('http://127.0.0.1:5000/set_alert_email', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ email })
  })
    .then(res => res.json())
    .then(data => {
      if (!data || data.status !== 'ok') {
        console.warn('Failed to set alert email on Python server', data);
      } else {
        console.log('Alert recipient set on Python server:', email);
      }
    })
    .catch(err => {
      console.error('Error sending alert email to Python server:', err);
    });
}

function showLiveFeedStream(cameraName) {
  liveFeedPlaceholder.classList.remove("show");
  liveFeedImage.classList.add("is-active");
  liveFeedSubtext.textContent = `${cameraName} is streaming`;
}

async function addCamera() {
  const name = document.getElementById("cameraName").value.trim();
  const url = document.getElementById("cameraUrl").value.trim();

  if (!name || !url) {
    openInfoModal("Input Required", "<p style='color: #ffbd2e;'>Please enter both a camera name and URL.</p>");
    return;
  }

  const isValidFormat = /^(rtsp:\/\/|http:\/\/|https:\/\/)((\d{1,3}\.){3}\d{1,3}|localhost|([a-zA-Z0-9-]+\.)+[a-zA-Z]{2,})(:\d+)?(\/.*)?$/.test(url);

  if (!isValidFormat) {
    openInfoModal(
      "Invalid Format",
      `<p style='color: #ff6b6b; margin-bottom: 8px;'>Invalid camera URL format.</p>
       <p style='font-size: 13px; color: #aaa;'>Must start with <b>rtsp://</b>, <b>http://</b>, or <b>https://</b></p>`
    );
    return;
  }

  try {
    const response = await fetch('/user/addCamera', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ name, url })
    });

    const data = await response.json();
    if (!response.ok || !data.success) {
      openInfoModal("Add Camera Failed", `<p style='color: #ff6b6b;'>${data.message || "Failed to add camera."}</p>`);
      return;
    }

    cameras = cameras.filter(camera => camera.name !== name);
    cameras.push({ name, url });
    renderCameraDropdown();
    cameraSelect.value = url;
    setCameraDropdownLabel(name);

    closeAddCamera();
    openInfoModal("Success", `<p>Camera "<b>${name}</b>" added successfully.</p>`);
    cameraSelect.dispatchEvent(new Event("change"));

  } catch (err) {
    console.error(err);
    openInfoModal("Server Error", "<p style='color: #ff6b6b;'>Server error while adding the camera.</p>");
  }
}

function getCurrentPipelineFromBlocks() {
  return Array.from(blocks.values()).map(b => b.type);
}

function clearCanvasBlocks() {
  Array.from(blocks.keys()).forEach(id => deleteBlock(id));
  connections.length = 0;
  drawConnections();
}

async function applyCameraSelection(cameraId, url) {
  currentCameraId = cameraId;

  const body = { camera_id: cameraId };
  if (url) body.url = url;

  await fetch("http://127.0.0.1:5000/set_camera", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  });

  const pipeline = cameraPipelines[cameraId] || [];
  clearCanvasBlocks();
  renderProjectBlocks(pipeline);
  startCamera();
}

function ensureCameraSelected() {
  if (currentCameraId) return true;
  if (cameraSelect && cameraSelect.value) return true;
  // In split mode, consider it valid if at least one panel has a camera
  if (currentSplitMode > 1 && Object.keys(splitCameras).length > 0) return true;
  openInfoModal("Camera Required", "<p style='color: #ffbd2e;'>Please select a camera before adding models or uploading the pipeline.</p>");
  return false;
}

cameraSelect.addEventListener("change", async function () {
  const url = this.value;
  if (!url) return;
  const cameraId = this.selectedOptions[0].dataset.cameraId || url;

  if (currentCameraId) {
    cameraPipelines[currentCameraId] = getCurrentPipelineFromBlocks();
  }

  await applyCameraSelection(cameraId, url);
});

function startCamera() {
  if (!currentCameraId) {
    showLiveFeedPlaceholder("Camera idle", "Select a camera to start streaming");
    return;
  }

  if (currentUserEmail) {
    sendAlertEmailToPython(currentUserEmail);
  }

  const suffix = currentCameraId ? `camera_id=${encodeURIComponent(currentCameraId)}&` : "";
  showLiveFeedStream(currentCameraId);
  liveFeedImage.src = `http://127.0.0.1:5000/video?${suffix}t=${Date.now()}`;
}

async function activateParkingMode() {
  await fetch("http://127.0.0.1:5000/init_parking", { method: "POST" });
  alert("Draw parking areas in the opened window, then press ESC");
  await fetch("http://127.0.0.1:5000/set_pipeline", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ pipeline: ["Parking Management"] })
  });
}

/* ================= CANVAS SYSTEM ================= */
const canvas = document.getElementById('canvas');
const svg = document.getElementById('connectionSvg');
const functionalities = document.querySelectorAll('.functionality');

let blockCount = 0;
const blocks = new Map();
const connections = [];
let draggedBlock = null;
let linking = false;
let linkingFromBlock = null;

const BLOCK_W = 140;
const BLOCK_H = 80;

/* ================= DRAG & DROP FROM SIDEBAR ================= */
canvas.addEventListener('dragover', e => e.preventDefault());
canvas.addEventListener('drop', e => {
  e.preventDefault();
  if (!ensureCameraSelected()) return;
  const type = e.dataTransfer.getData('text/plain');
  if (!type) return;
  const rect = canvas.getBoundingClientRect();
  createBlock(type, e.clientX - rect.left, e.clientY - rect.top);
});

functionalities.forEach(func => {
  func.addEventListener('dragstart', e => {
    e.dataTransfer.setData('text/plain', func.dataset.type);
  });
});

/* ================= BLOCK CREATION ================= */
function createBlock(type, x, y) {
  const id = `block-${blockCount++}`;
  const block = document.createElement('div');
  block.className = 'block';
  block.id = id;

  let extraButtons = "";
  if (type === "Attendance") {
    extraButtons = `
      <button class="list-btn">List</button>
      <button class="images-btn">Classes</button>
    `;
  }

  block.innerHTML = `
    <div class="block-title">${type}</div>
    <div class="block-controls">
      <button class="link-btn">Link</button>
      ${extraButtons}
      <button class="delete-btn">✕</button>
    </div>
    <div class="port top" data-port="top"></div>
    <div class="port bottom" data-port="bottom"></div>
    <div class="port left" data-port="left"></div>
    <div class="port right" data-port="right"></div>
  `;

  const bx = x - 70;
  const by = y - 40;
  block.style.left = `${bx}px`;
  block.style.top = `${by}px`;
  canvas.appendChild(block);

  const w = block.offsetWidth || BLOCK_W;
  const h = block.offsetHeight || BLOCK_H;

  blocks.set(id, { id, type, element: block, x: bx, y: by, w, h });

  block.querySelector('.link-btn').onclick = () => toggleLinking(id);
  block.querySelector('.delete-btn').onclick = () => deleteBlock(id);

  if (type === "Attendance") {
    block.querySelector('.list-btn').onclick = () => showAttendanceList();
    block.querySelector('.images-btn').onclick = () => openAttendanceClassesDropdown(id);
  }

  makeBlockDraggable(id);
  updateLiveFeed(`Added ${type} block`);
  return id;
}

/* ================= BLOCK DRAGGING ================= */
let offsetX, offsetY;
let cachedCanvasRect = null;
let rafPending = false;

function makeBlockDraggable(id) {
  const el = document.getElementById(id);

  el.addEventListener('mousedown', e => {
    if (e.target.tagName === 'BUTTON') return;
    e.preventDefault();
    draggedBlock = id;

    cachedCanvasRect = canvas.getBoundingClientRect();

    const rect = el.getBoundingClientRect();
    offsetX = e.clientX - rect.left;
    offsetY = e.clientY - rect.top;
    el.classList.add('selected');
  });
}

document.addEventListener('mousemove', e => {
  if (!draggedBlock) return;

  const x = e.clientX - cachedCanvasRect.left - offsetX;
  const y = e.clientY - cachedCanvasRect.top - offsetY;

  const b = blocks.get(draggedBlock);
  if (!b) return;

  b.element.style.left = `${x}px`;
  b.element.style.top = `${y}px`;
  b.x = x;
  b.y = y;

  if (!rafPending) {
    rafPending = true;
    requestAnimationFrame(() => {
      drawConnections();
      rafPending = false;
    });
  }
});

document.addEventListener('mouseup', () => {
  if (draggedBlock) {
    document.getElementById(draggedBlock)?.classList.remove('selected');
    draggedBlock = null;
    cachedCanvasRect = null;
    rafPending = false;
  }
});

/* ================= PORT POSITIONS ================= */
function getPortPositionFast(id, port) {
  const b = blocks.get(id);
  const w = b.w || BLOCK_W;
  const h = b.h || BLOCK_H;
  switch (port) {
    case 'top':    return { x: b.x + w / 2, y: b.y - 15 };
    case 'bottom': return { x: b.x + w / 2, y: b.y + h + 15 };
    case 'left':   return { x: b.x - 15,    y: b.y + h / 2 };
    case 'right':  return { x: b.x + w + 15, y: b.y + h / 2 };
  }
}

function getClosestPorts(fromId, toId) {
  const ports = ['top', 'bottom', 'left', 'right'];
  let min = Infinity;
  let fromPort = 'right';
  let toPort = 'left';
  ports.forEach(fp => {
    ports.forEach(tp => {
      const a = getPortPositionFast(fromId, fp);
      const b = getPortPositionFast(toId, tp);
      const d = Math.hypot(a.x - b.x, a.y - b.y);
      if (d < min) { min = d; fromPort = fp; toPort = tp; }
    });
  });
  return { fromPort, toPort };
}

/* ================= LINKING ================= */
function toggleLinking(id) {
  if (!linking) {
    linking = true;
    linkingFromBlock = id;
    document.getElementById(id).querySelector('.link-btn').classList.add('active');
    updateLiveFeed('Select another block to link');
  } else if (linkingFromBlock !== id) {
    createConnection(linkingFromBlock, id);
    document.getElementById(linkingFromBlock).querySelector('.link-btn').classList.remove('active');
    linking = false;
    linkingFromBlock = null;
    updateLiveFeed('Blocks connected');
  }
}

/* ================= CONNECTION LOGIC ================= */
function createConnection(from, to) {
  if (connections.find(c => c.from === from && c.to === to)) return;
  const ports = getClosestPorts(from, to);
  connections.push({ from, to, ...ports });
  drawConnections();
}

function drawConnections() {
  const existingPaths = svg.querySelectorAll('path');
  const validConnections = connections.filter(c => blocks.has(c.from) && blocks.has(c.to));

  for (let i = existingPaths.length - 1; i >= validConnections.length; i--) {
    existingPaths[i].remove();
  }

  validConnections.forEach((c, i) => {
    const ports = getClosestPorts(c.from, c.to);
    c.fromPort = ports.fromPort;
    c.toPort = ports.toPort;

    const a = getPortPositionFast(c.from, c.fromPort);
    const b = getPortPositionFast(c.to, c.toPort);
    const midX = (a.x + b.x) / 2;
    const d = `M ${a.x} ${a.y} C ${midX} ${a.y}, ${midX} ${b.y}, ${b.x} ${b.y}`;

    let path = existingPaths[i];
    if (!path) {
      path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      path.setAttribute('class', 'line');
      svg.appendChild(path);
    }
    path.setAttribute('d', d);
  });
}

function updateConnections() { drawConnections(); }

/* ================= DELETE BLOCK ================= */
function deleteBlock(id) {
  document.getElementById(id).remove();
  blocks.delete(id);
  for (let i = connections.length - 1; i >= 0; i--) {
    if (connections[i].from === id || connections[i].to === id) connections.splice(i, 1);
  }
  drawConnections();
  updateLiveFeed('Block removed');
  updateBackendPipeline();
}

async function updateBackendPipeline() {
  try {
    const pipeline = Array.from(blocks.values()).map(b => b.type);

    const response = await fetch("http://127.0.0.1:5000/set_pipeline", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pipeline, camera_id: currentCameraId || "default" })
    });

    if (!response.ok) throw new Error("Server error");

    const data = await response.json();
    console.log("Backend pipeline updated:", data);

    if (pipeline.length > 0) {
      updateLiveFeed("Pipeline updated: " + pipeline.join(" → "));
    } else {
      updateLiveFeed("All models stopped");
    }

  } catch (err) {
    console.error("Failed to update backend pipeline:", err);
    updateLiveFeed("Backend update failed");
  }
}

/* ================= LIVE FEED LOG ================= */
function updateLiveFeed(msg) {
  const time = new Date().toLocaleTimeString();
  console.log(`[${time}] ${msg}`);
}
updateLiveFeed('System ready');

/* ================= PROJECT FUNCTIONS ================= */
const saveModal = document.getElementById('saveProjectModal');
const projectNameInput = document.getElementById('projectNameInput');

function closeSaveModal() {
  saveModal.classList.remove('show');
  projectNameInput.value = '';
}

function saveProject() {
  const pipeline = Array.from(blocks.values()).map(b => b.type);
  if (pipeline.length === 0) {
    openInfoModal("Warning", "<p style='color: #ffbd2e;'>Cannot save an empty project.</p>");
    return;
  }
  saveModal.classList.add('show');
  projectNameInput.focus();
}

function confirmSaveProject() {
  const name = projectNameInput.value.trim();

  if (!name) {
    openInfoModal("Input Required", "<p>Please enter a valid project name.</p>");
    return;
  }
  const pipeline = Array.from(blocks.values()).map(b => b.type);
  closeSaveModal();
  fetch('/user/projectsCreate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({ name, pipeline })
  })
    .then(res => res.json())
    .then(data => {
      if (data.success) {
        openInfoModal("Success", `<p>Project "<b>${name}</b>" saved successfully.</p>`);
        const okBtn = document.querySelector('#infoModal .btn-primary');
        okBtn.setAttribute("onclick", "closeInfoModalAfterSave()");
        updateLiveFeed(`Project "${name}" saved`);
      } else {
        openInfoModal("Save Failed", `<p style='color: #ff6b6b;'>${data.message || "Failed to save project."}</p>`);
      }
    })
    .catch(err => {
      console.error(err);
      openInfoModal("Server Error", "<p style='color: #ff6b6b;'>Server error while saving project.</p>");
    });
}

async function uploadProject() {
  try {
    const pipeline = Array.from(blocks.values()).map(b => b.type);

    if (!ensureCameraSelected()) return;

    if (pipeline.length === 0) {
      openInfoModal("Warning", "<p style='color: #ffbd2e;'>Pipeline is empty. Please add blocks first.</p>");
      return;
    }

    // ================= VALIDATION RULES =================
    const allowedExact = [
      ["Object Counting", "Gap Detection"],
      ["Tracking", "Attendance"]
    ];

    const isSingle = pipeline.length === 1;

    const isAllowedCombo = allowedExact.some(allowed =>
      allowed.length === pipeline.length &&
      allowed.every(v => pipeline.includes(v))
    );

    const isAllowedSingle =
      isSingle &&
      (
        pipeline[0] === "Object Counting" ||
        pipeline[0] === "Gap Detection" ||
        pipeline[0] === "Tracking" ||
        pipeline[0] === "Attendance" ||
        pipeline[0] === "Security" ||
        pipeline[0] === "Parking Management" ||
        pipeline[0] === "Heatmap" ||
        pipeline[0] === "Color Detection" ||
        pipeline[0] === "Fire & Smoke Detection"
      );

    const isValid = isAllowedSingle || isAllowedCombo;

    if (!isValid) {
      const errorMsg = `
        <p style='color: #ff6b6b; margin-bottom: 10px;'>Invalid pipeline configuration!</p>
        <p><b>Allowed setups:</b></p>
        <ul style='color: #c9d1d9; line-height: 1.6;'>
            <li>Single model only (Tracking, Attendance, Security, Parking, etc.)</li>
            <li>Object Counting + Gap Detection</li>
            <li>Tracking + Attendance</li>
        </ul>
      `;
      openInfoModal("Pipeline Error", errorMsg);
      return;
    }

    // ================= SPLIT MODE: show camera picker =================
    if (currentSplitMode > 1 && Object.keys(splitCameras).length > 0) {
      openSplitUploadModal(pipeline);
      return;
    }

    // ================= SINGLE MODE: send directly =================
    await applyPipelineToCamera(pipeline, [currentCameraId || "default"]);

  } catch (err) {
    console.error(err);
    openInfoModal("Connection Error", "<p style='color: #ff6b6b;'>Backend is not running or unreachable.</p>");
    updateLiveFeed("Backend not running");
  }
}

/* ── Apply pipeline to a list of camera IDs ── */
async function applyPipelineToCamera(pipeline, cameraIds) {
  try {
    const results = await Promise.all(cameraIds.map(camId =>
      fetch("http://127.0.0.1:5000/set_pipeline", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pipeline, camera_id: camId })
      }).then(r => { if (!r.ok) throw new Error("Server error"); return r.json(); })
    ));

    const camList = cameraIds.join(", ");
    openInfoModal("Models Applied", `<p>Successfully applied:<br><b>${pipeline.join(" &rarr; ")}</b><br><span style="color:var(--text-dim);font-size:0.85rem;">Applied to: ${camList}</span></p>`);
    updateLiveFeed("Pipeline applied: " + pipeline.join(" → "));
    console.log("Backend pipelines:", results);

    if (currentSplitMode > 1) {
      for (const [idx, data] of Object.entries(splitCameras)) {
        if (!cameraIds.includes(data.cameraId)) continue;

        // AWAIT register_camera — server must store the URL before
        // the browser requests /video_processed, otherwise stream is empty.
        await fetch("http://127.0.0.1:5000/register_camera", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ camera_id: data.cameraId, url: data.url })
        });

        const cell = splitGrid.querySelector(`.split-cell[data-index="${idx}"]`);
        if (!cell) continue;
        const img  = cell.querySelector('.split-cell-img');
        const idle = cell.querySelector('.split-cell-idle');
        const processedUrl = `http://127.0.0.1:5000/video_processed?camera_id=${encodeURIComponent(data.cameraId)}&t=${Date.now()}`;
        img.src = processedUrl;
        img.classList.add('active');
        if (idle) idle.style.display = 'none';
        if (focusedPanelIndex === parseInt(idx)) {
          splitFocusImg.src = processedUrl;
          splitFocusImg.classList.add('active');
          splitFocusPlaceholder.classList.add('hidden');
        }
      }
      splitPipelineActive = true;
    }
  } catch (err) {
    console.error(err);
    openInfoModal("Connection Error", "<p style='color: #ff6b6b;'>Backend is not running or unreachable.</p>");
    updateLiveFeed("Backend not running");
  }
}

/* ── Split upload modal ── */
let _splitUploadPipeline = [];

function openSplitUploadModal(pipeline) {
  _splitUploadPipeline = pipeline;

  const list = document.getElementById('splitUploadCameraList');
  list.innerHTML = '';

  const entries = Object.entries(splitCameras);
  if (entries.length === 0) {
    list.innerHTML = '<div class="split-upload-empty">No cameras selected in split view.</div>';
  } else {
    entries.forEach(([idx, data]) => {
      const item = document.createElement('div');
      item.className = 'split-upload-camera-item selected'; // default all selected
      item.dataset.cameraId = data.cameraId;

      item.innerHTML = `
        <div class="split-upload-checkbox">✓</div>
        <div class="split-upload-cam-info">
          <span class="split-upload-cam-label">Cam ${parseInt(idx) + 1}</span>
          <span class="split-upload-cam-name">${data.cameraId}</span>
        </div>
      `;

      item.addEventListener('click', () => {
        item.classList.toggle('selected');
      });

      list.appendChild(item);
    });
  }

  document.getElementById('splitUploadModal').classList.add('show');
}

function closeSplitUploadModal() {
  document.getElementById('splitUploadModal').classList.remove('show');
  _splitUploadPipeline = [];
}

async function confirmSplitUpload() {
  const selected = Array.from(
    document.querySelectorAll('.split-upload-camera-item.selected')
  ).map(el => el.dataset.cameraId);

  if (selected.length === 0) {
    openInfoModal("No Camera Selected", "<p style='color: #ffbd2e;'>Please select at least one camera.</p>");
    return;
  }

  // Capture pipeline BEFORE closing the modal — closeSplitUploadModal()
  // resets _splitUploadPipeline to [] which would empty the reference passed below.
  const pipeline = [..._splitUploadPipeline];
  closeSplitUploadModal();
  await applyPipelineToCamera(pipeline, selected);
}

function triggerAttendanceUpload() {
  const input = document.getElementById('attendanceUploadInput');
  if (!input) return;
  input.value = null;
  input.click();
}

const attendanceUploadInput = document.getElementById('attendanceUploadInput');
if (attendanceUploadInput) {
  attendanceUploadInput.addEventListener('change', async () => {
    const files = Array.from(attendanceUploadInput.files || []).filter(file => file.type.startsWith('image/'));
    if (files.length === 0) {
      openInfoModal('Upload Cancelled', '<p>No image selected.</p>');
      return;
    }

    const formData = new FormData();
    files.forEach(file => formData.append('images', file));

    try {
      const response = await fetch('http://127.0.0.1:5000/upload_attendance_images', {
        method: 'POST',
        body: formData
      });
      const data = await response.json();

      if (response.ok && data.status === 'success') {
        openInfoModal('Upload Successful', `<p>Uploaded ${files.length} image(s) to attendance dataset.</p>`);
        updateLiveFeed(`Uploaded ${files.length} attendance image(s)`);
      } else {
        openInfoModal('Upload Failed', `<p style='color: #ff6b6b;'>${data.message || 'Failed to upload attendance image(s).'}</p>`);
      }
    } catch (err) {
      console.error(err);
      openInfoModal('Connection Error', '<p style="color: #ff6b6b;">Unable to reach the attendance server.</p>');
    }
  });
}

/* ================= LOGOUT ================= */
const logoutBtn = document.getElementById("logoutBtn");
if (logoutBtn) {
  logoutBtn.addEventListener("click", async () => {
    try {
      const res = await fetch("/user/logout", { method: "POST", credentials: "include" });
      const data = await res.json();
      if (data.success) window.location.href = "/";
      else alert("Logout failed");
    } catch (err) { console.error(err); alert("Server error during logout"); }
  });
}

/* ================= PROJECTS ================= */
function loadProjects() {
  const select = document.getElementById('projectSelect');
  if (!select) return;
  select.innerHTML = '';
  const defaultOption = document.createElement('option');
  defaultOption.value = '';
  defaultOption.textContent = 'Select Project';
  select.appendChild(defaultOption);

  fetch('/user/Getprojects', { credentials: 'include' })
    .then(res => res.json())
    .then(data => {
      if (!data.success) { alert("Failed to load projects"); return; }
      data.projects.forEach(project => {
        const opt = document.createElement('option');
        opt.value = project._id;
        opt.textContent = project.name;
        select.appendChild(opt);
      });
    })
    .catch(err => console.error("Fetch projects error:", err));
}

function loadProject(projectId) {
  fetch(`/user/projects/${projectId}`, { credentials: 'include' })
    .then(res => res.json())
    .then(data => {
      if (!data.success) { alert("Failed to load project"); return; }
      renderProjectBlocks(data.project.pipeline);
    })
    .catch(err => console.error(err));
}

function promptDeleteCamera(cameraName) {
  openInfoModal('Confirm Delete', `<p>Are you sure you want to delete camera "<b>${cameraName}</b>"? This cannot be undone.</p>`);
  const okBtn = document.querySelector('#infoModal .btn-primary');
  okBtn.innerText = "Delete";
  okBtn.style.backgroundColor = "#ff4d4d";
  okBtn.setAttribute("type", "button");
  okBtn.removeAttribute("onclick");
  okBtn.onclick = event => {
    event.preventDefault();
    event.stopPropagation();
    executeCameraDelete(cameraName);
  };
}

async function executeCameraDelete(cameraName) {
  try {
    const response = await fetch(new URL('/user/deleteCamera', window.location.origin), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ name: cameraName })
    });

    const responseText = await response.text();
    let data;

    try {
      data = responseText ? JSON.parse(responseText) : {};
    } catch (parseError) {
      throw new Error(`Unexpected server response (${response.status}): ${responseText.slice(0, 120)}`);
    }

    const okBtn = document.querySelector('#infoModal .btn-primary');
    okBtn.innerText = "OK";
    okBtn.style.backgroundColor = "";
    okBtn.setAttribute("type", "button");
    okBtn.onclick = event => {
      event.preventDefault();
      closeInfoModal();
    };

    if (!response.ok || !data.success) {
      openInfoModal('Delete Failed', `<p style='color: #ff6b6b;'>${data.message || 'Failed to delete camera.'}</p>`);
      return;
    }

    cameras = cameras.filter(camera => camera.name !== cameraName);
    delete cameraPipelines[cameraName];

    if (currentCameraId === cameraName) {
      currentCameraId = null;
      cameraSelect.value = "";
      setCameraDropdownLabel();
      clearCanvasBlocks();
      showLiveFeedPlaceholder("Camera removed", "Select another camera to continue streaming");
    }

    renderCameraDropdown();
    closeCameraDropdown();
    openInfoModal('Camera Deleted', `<p>Camera "<b>${cameraName}</b>" was deleted successfully.</p>`);
  } catch (err) {
    console.error(err);
    openInfoModal('Delete Failed', `<p style="color: #ff6b6b;">${err.message || 'Unable to delete camera. Please try again.'}</p>`);
  }
}

function deleteSelectedProject() {
  const select = document.getElementById('projectSelect');
  if (!select) return;

  const projectId = select.value;
  if (!projectId) {
    openInfoModal('Delete Project', '<p>Please select a project first.</p>');
    return;
  }

  const projectName = select.selectedOptions[0]?.textContent || 'Selected project';
  openInfoModal('Confirm Delete', `<p>Are you sure you want to delete "<b>${projectName}</b>"? This cannot be undone.</p>`);
  const okBtn = document.querySelector('#infoModal .btn-primary');
  okBtn.innerText = "Delete";
  okBtn.style.backgroundColor = "#ff4d4d";
  okBtn.setAttribute("onclick", `executeProjectDelete('${projectId}', '${projectName}')`);
}

async function executeProjectDelete(projectId, projectName) {
  try {
    const res = await fetch(`/user/projects/${projectId}`, {
      method: 'DELETE',
      credentials: 'include'
    });

    const data = await res.json();
    const okBtn = document.querySelector('#infoModal .btn-primary');
    okBtn.innerText = "OK";
    okBtn.style.backgroundColor = "";
    okBtn.setAttribute("onclick", "closeInfoModal()");

    if (!data.success) {
      openInfoModal('Delete Failed', `<p style='color: #ff6b6b;'>${data.message || 'Failed to delete project.'}</p>`);
      return;
    }
    openInfoModal('Project Deleted', `<p>Project "<b>${projectName}</b>" was deleted successfully.</p>`);

    const successBtn = document.querySelector('#infoModal .btn-primary');
    successBtn.setAttribute("onclick", "location.reload()");

  } catch (err) {
    console.error(err);
    openInfoModal('Delete Failed', '<p style="color: #ff6b6b;">Unable to delete project. Please try again.</p>');
  }
}

function clearCanvasOnly() {
  blocks.forEach(b => b.element.remove());
  blocks.clear();
  connections.length = 0;
  blockCount = 0;
}

function renderProjectBlocks(pipeline) {
  clearCanvasOnly();
  let x = 100, y = 200;
  const orderedBlockIds = [];
  pipeline.forEach(type => {
    const blockId = createBlock(type, x, y);
    orderedBlockIds.push(blockId);
    x += 300;
  });
  requestAnimationFrame(() => {
    orderedBlockIds.forEach(id => {
      const b = blocks.get(id);
      if (b) { b.w = b.element.offsetWidth; b.h = b.element.offsetHeight; }
    });
    autoConnectBlocksInOrder(orderedBlockIds);
    drawConnections();
  });
}

function autoConnectBlocksInOrder(orderedBlockIds) {
  connections.length = 0;
  for (let i = 0; i < orderedBlockIds.length - 1; i++) {
    const fromId = orderedBlockIds[i];
    const toId = orderedBlockIds[i + 1];
    if (blocks.has(fromId) && blocks.has(toId)) createConnection(fromId, toId);
  }
  drawConnections();
}

/* ─── Modal Helper Functions ─── */
const infoModal = document.getElementById('infoModal');
const infoTitle = document.getElementById('infoModalTitle');
const infoContent = document.getElementById('infoModalContent');

function openInfoModal(title, htmlContent) {
  infoTitle.innerText = title;
  infoContent.innerHTML = htmlContent;
  infoModal.classList.add('show');
}

function closeInfoModal() {
  infoModal.classList.remove('show');
}

function closeInfoModalAfterSave() {
  infoModal.classList.remove('show');
  location.reload();
}

window.addEventListener('click', function (event) {
  if (event.target === infoModal) {
    closeInfoModal();
  }
});

/* ─── Attendance List ─── */
async function showAttendanceList() {
  try {
    const res = await fetch("http://127.0.0.1:5000/attendance_results");
    const data = await res.json();

    if (!Array.isArray(data) || data.length === 0) {
      openInfoModal("Attendance List", "<p>No attendance records yet.</p>");
      return;
    }

    let listHTML = '<div class="attendance-list">';
    data.forEach(person => {
      listHTML += `
        <div class="attendance-item">
          <span class="attendance-name">${person.name}</span>
          <span class="attendance-time">${person.time}</span>
        </div>
      `;
    });
    listHTML += '</div>';

    openInfoModal("Attendance List", listHTML);

  } catch (err) {
    console.error(err);
    openInfoModal("Error", "<p style='color: #ff6b6b;'>Failed to fetch attendance list.</p>");
  }
}

/* ═══════════════════════════════════════════════════════
   ATTENDANCE CLASS MANAGER
   Activated ONLY when Attendance is the sole block on canvas
════════════════════════════════════════════════════════ */

/* State for the class modal */
let _attSelectedFiles = [];        // FileList → array of File objects
let _attPendingBlockId = null;     // which block triggered the modal

/* ─── Check if Attendance is standalone ─── */
function isAttendanceAlone() {
  const pipeline = Array.from(blocks.values()).map(b => b.type);
  return pipeline.length === 1 && pipeline[0] === "Attendance";
}

/* ─── "Classes" button on block ─── */
function openAttendanceClassesDropdown(blockId) {
  if (!isAttendanceAlone()) {
    // When combined in a pipeline — original behaviour
    uploadAttendanceImages();
    return;
  }
  _attPendingBlockId = blockId;
  openAttendanceClassDropdownMenu(blockId);
}

/* ─── Build & show inline dropdown next to the block ─── */
let _attDropdownEl = null;

function openAttendanceClassDropdownMenu(blockId) {
  // Remove any existing dropdown
  closeAttendanceDropdownMenu();

  const blockEl = document.getElementById(blockId);
  const blockRect = blockEl.getBoundingClientRect();
  const canvasRect = canvas.getBoundingClientRect();

  const menu = document.createElement('div');
  menu.id = 'attClassDropdown';
  menu.className = 'att-class-dropdown';
  menu.style.left = `${blockRect.right - canvasRect.left + 8}px`;
  menu.style.top  = `${blockRect.top  - canvasRect.top}px`;

  // "+ Add Class" button always at top
  const addItem = document.createElement('button');
  addItem.className = 'att-class-dropdown-item att-class-dropdown-add';
  addItem.innerHTML = '＋ Add Class';
  addItem.onclick = () => {
    closeAttendanceDropdownMenu();
    openAttendanceClassModal();
  };
  menu.appendChild(addItem);

  canvas.appendChild(menu);
  _attDropdownEl = menu;

  // Fetch & render existing classes
  fetch('/user/attendance/classes', { credentials: 'include' })
    .then(r => r.json())
    .then(data => {
      if (!data.success) return;
      data.classes.forEach(cls => {
        const item = document.createElement('div');
        item.className = 'att-class-dropdown-item att-class-dropdown-existing';

        // ── Class name: clicking activates the class for recognition ──
        const nameSpan = document.createElement('span');
        nameSpan.className = 'att-class-dropdown-name';
        nameSpan.textContent = cls.name;
        nameSpan.title = `Activate ${cls.name} for attendance recognition`;
        nameSpan.onclick = async () => {
          closeAttendanceDropdownMenu();
          try {
            const res = await fetch('http://127.0.0.1:5000/set_attendance_class', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ class_name: cls.name })
            });
            const result = await res.json();
            openInfoModal(
              '✅ Class Activated',
              `<p>Recognition is now running for <b>${cls.name}</b>.</p>
               <p style="color:#aaa;font-size:13px;margin-top:6px;">
                 ${result.persons ?? 0} student(s) loaded from dataset.
               </p>`
            );
          } catch (err) {
            console.warn('Could not notify backend of class switch:', err);
            openInfoModal('⚠️ Backend Unreachable', '<p style="color:#ffbd2e;">Class selected but backend did not respond. Make sure the Python server is running.</p>');
          }
        };

        // ── (+) button: opens the add-photos modal ──
        const addPhotosBtn = document.createElement('button');
        addPhotosBtn.className = 'att-class-add-photos-btn';
        addPhotosBtn.innerHTML = '＋';
        addPhotosBtn.title = `Add students to ${cls.name}`;
        addPhotosBtn.onclick = (e) => {
          e.stopPropagation();
          closeAttendanceDropdownMenu();
          openAttendanceClassModal(cls);
        };

        // ── (×) button: delete class ──
        const delBtn = document.createElement('button');
        delBtn.className = 'att-class-dropdown-del';
        delBtn.innerHTML = '&times;';
        delBtn.title = `Delete ${cls.name}`;
        delBtn.onclick = (e) => {
          e.stopPropagation();
          confirmDeleteAttendanceClass(cls._id, cls.name);
        };

        item.appendChild(nameSpan);
        item.appendChild(addPhotosBtn);
        item.appendChild(delBtn);
        menu.appendChild(item);
      });

      if (data.classes.length === 0) {
        const emptyEl = document.createElement('div');
        emptyEl.className = 'att-class-dropdown-empty';
        emptyEl.textContent = 'No classes yet';
        menu.appendChild(emptyEl);
      }
    })
    .catch(err => {
      console.error(err);
      const errEl = document.createElement('div');
      errEl.className = 'att-class-dropdown-empty';
      errEl.textContent = 'Failed to load classes';
      menu.appendChild(errEl);
    });
}

function closeAttendanceDropdownMenu() {
  if (_attDropdownEl) {
    _attDropdownEl.remove();
    _attDropdownEl = null;
  }
}

/* ─── Open class modal (new or existing) ─── */
function openAttendanceClassModal(existingClass = null) {
  _attSelectedFiles = [];
  _attEditingClassId = existingClass ? existingClass._id : null;

  const modal = document.getElementById('attendanceClassModal');
  const nameInput = document.getElementById('attendanceClassName');
  const preview = document.getElementById('attImagePreview');
  const errEl = document.getElementById('attClassError');
  const fileInput = document.getElementById('attImageInput');
  const btnText = document.getElementById('attSaveBtnText');

  nameInput.value = existingClass ? existingClass.name : '';
  preview.innerHTML = '';
  errEl.style.display = 'none';
  fileInput.value = '';

  if (existingClass) {
    // Show existing saved images as thumbnails
    (existingClass.images || []).forEach(img => {
      const thumb = document.createElement('div');
      thumb.className = 'att-thumb att-thumb-saved';
      thumb.innerHTML = `
        <div class="att-thumb-icon">🖼️</div>
        <div class="att-thumb-name">${img.originalName}</div>
      `;
      preview.appendChild(thumb);
    });
    btnText.textContent = 'Add Photos';
    document.querySelector('#attendanceClassModal h3').textContent = `🪪 ${existingClass.name}`;
    nameInput.disabled = true;
    nameInput.style.opacity = '0.5';
  } else {
    btnText.textContent = 'Save Class';
    document.querySelector('#attendanceClassModal h3').textContent = '🪪 Add Attendance Class';
    nameInput.disabled = false;
    nameInput.style.opacity = '1';
  }

  modal.classList.add('show');
}

let _attEditingClassId = null;

function closeAttendanceClassModal() {
  const modal = document.getElementById('attendanceClassModal');
  modal.classList.remove('show');
  _attSelectedFiles = [];
  _attEditingClassId = null;

  const nameInput = document.getElementById('attendanceClassName');
  nameInput.disabled = false;
  nameInput.style.opacity = '1';
  document.getElementById('attImagePreview').innerHTML = '';
  document.getElementById('attClassError').style.display = 'none';
  document.getElementById('attImageInput').value = '';
}

/* ─── File input change → preview ─── */
document.addEventListener('DOMContentLoaded', () => {
  const fileInput = document.getElementById('attImageInput');
  if (fileInput) {
    fileInput.addEventListener('change', () => {
      _attSelectedFiles = Array.from(fileInput.files);
      renderAttImagePreview();
    });
  }

  // Drag & drop on upload zone
  const zone = document.getElementById('attUploadZone');
  if (zone) {
    zone.addEventListener('dragover', e => { e.preventDefault(); zone.classList.add('att-upload-zone-drag'); });
    zone.addEventListener('dragleave', () => zone.classList.remove('att-upload-zone-drag'));
    zone.addEventListener('drop', e => {
      e.preventDefault();
      zone.classList.remove('att-upload-zone-drag');
      const dropped = Array.from(e.dataTransfer.files).filter(f => f.type.startsWith('image/'));
      _attSelectedFiles = [..._attSelectedFiles, ...dropped];
      renderAttImagePreview();
    });
  }

  showLiveFeedPlaceholder("Camera idle", "Select a camera to start streaming");
  loadProjects();

  fetch('/user/getProfile', { credentials: 'include' })
    .then(res => res.json())
    .then(data => {
      if (data.success && data.email) {
        currentUserEmail = data.email;
        sendAlertEmailToPython(data.email);
      } else {
        console.warn('getProfile did not return an email', data);
      }
    })
    .catch(err => {
      console.error('Unable to retrieve current user profile for alert email:', err);
    });

  const dropdown = document.getElementById('projectSelect');
  const deleteBtn = document.getElementById('deleteProjectBtn');
  if (deleteBtn) {
    deleteBtn.disabled = true;
    deleteBtn.style.opacity = '0.5';
  }
  if (!dropdown) return;

  fetch('/user/getCameras')
    .then(res => res.json())
    .then(data => {
      if (!data.success) throw new Error(data.message || 'Failed to fetch cameras');
      cameras = Object.entries(data.cameras || {}).map(([name, url]) => ({ name, url }));
      renderCameraDropdown();
    })
    .catch(err => {
      console.error(err);
      cameras = [];
      renderCameraDropdown();
    });

  fetch('/user/Getprojects')
    .then(res => { if (!res.ok) throw new Error('Failed to fetch projects'); return res.json(); })
    .then(data => {
      dropdown.innerHTML = '';
      if (!data.success || data.projects.length === 0) {
        dropdown.innerHTML = `<option value="">No projects found</option>`;
        return;
      }
      dropdown.innerHTML = `<option value="">Select a project</option>`;
      data.projects.forEach(project => {
        const option = document.createElement('option');
        option.value = project._id;
        option.textContent = project.name;
        dropdown.appendChild(option);
      });
    })
    .catch(err => { console.error(err); dropdown.innerHTML = `<option value="">Error loading projects</option>`; });

  dropdown.addEventListener('change', () => {
    const projectId = dropdown.value;
    const deleteBtn = document.getElementById('deleteProjectBtn');
    if (deleteBtn) {
      deleteBtn.disabled = !projectId;
      deleteBtn.style.opacity = projectId ? '1' : '0.5';
    }
    if (!projectId) return;
    loadProject(projectId);
    localStorage.setItem('activeProjectId', projectId);
  });

  cameraDropdownToggle.addEventListener('click', event => {
    event.stopPropagation();
    const isOpen = cameraDropdownMenu.classList.contains('show');
    if (isOpen) {
      closeCameraDropdown();
      return;
    }
    openCameraDropdown();
  });
});

function renderAttImagePreview() {
  const preview = document.getElementById('attImagePreview');
  // Keep saved thumbs (those without objectURL data), re-add new ones
  const savedThumbs = Array.from(preview.querySelectorAll('.att-thumb-saved'));
  preview.innerHTML = '';
  savedThumbs.forEach(t => preview.appendChild(t));

  _attSelectedFiles.forEach((file, idx) => {
    const url = URL.createObjectURL(file);
    const thumb = document.createElement('div');
    thumb.className = 'att-thumb att-thumb-new';
    thumb.innerHTML = `
      <img src="${url}" alt="${file.name}" class="att-thumb-img">
      <div class="att-thumb-name">${file.name}</div>
      <button class="att-thumb-remove" data-idx="${idx}">&times;</button>
    `;
    preview.appendChild(thumb);
  });

  // Remove buttons
  preview.querySelectorAll('.att-thumb-remove').forEach(btn => {
    btn.addEventListener('click', () => {
      const idx = parseInt(btn.dataset.idx);
      _attSelectedFiles.splice(idx, 1);
      renderAttImagePreview();
    });
  });
}

/* ─── Save / Add photos ─── */
async function saveAttendanceClass() {
  const nameInput = document.getElementById('attendanceClassName');
  const errEl = document.getElementById('attClassError');
  const saveBtn = document.getElementById('attSaveBtn');
  const btnText = document.getElementById('attSaveBtnText');

  errEl.style.display = 'none';

  if (_attEditingClassId) {
    // Adding photos to existing class
    if (_attSelectedFiles.length === 0) {
      showAttError('Please select at least one image to add.');
      return;
    }
    saveBtn.disabled = true;
    btnText.textContent = 'Uploading...';

    const formData = new FormData();
    _attSelectedFiles.forEach(f => formData.append('images', f));

    try {
      const res = await fetch(`/user/attendance/classes/${_attEditingClassId}/images`, {
        method: 'POST',
        credentials: 'include',
        body: formData
      });
      const data = await res.json();
      if (!res.ok || !data.success) {
        showAttError(data.message || 'Failed to upload images.');
        return;
      }
      closeAttendanceClassModal();
      openInfoModal('Photos Added', `<p>Photos added to class successfully.</p>`);
    } catch (err) {
      console.error(err);
      showAttError('Server error. Please try again.');
    } finally {
      saveBtn.disabled = false;
      btnText.textContent = 'Add Photos';
    }

  } else {
    // Creating new class
    const name = nameInput.value.trim();
    if (!name) {
      showAttError('Please enter a class name.');
      return;
    }
    if (_attSelectedFiles.length === 0) {
      showAttError('Please add at least one student photo.');
      return;
    }

    saveBtn.disabled = true;
    btnText.textContent = 'Saving...';

    const formData = new FormData();
    formData.append('name', name);
    _attSelectedFiles.forEach(f => formData.append('images', f));

    try {
      const res = await fetch('/user/attendance/classes', {
        method: 'POST',
        credentials: 'include',
        body: formData
      });
      const data = await res.json();
      if (!res.ok || !data.success) {
        showAttError(data.message || 'Failed to create class.');
        return;
      }
      closeAttendanceClassModal();
      openInfoModal('Class Saved', `<p>Class "<b>${name}</b>" created with ${_attSelectedFiles.length} photo(s).</p>`);
    } catch (err) {
      console.error(err);
      showAttError('Server error. Please try again.');
    } finally {
      saveBtn.disabled = false;
      btnText.textContent = 'Save Class';
    }
  }
}

function showAttError(msg) {
  const errEl = document.getElementById('attClassError');
  errEl.textContent = msg;
  errEl.style.display = 'block';
}

/* ─── Confirm delete class ─── */
function confirmDeleteAttendanceClass(classId, className) {
  openInfoModal('Confirm Delete', `<p>Delete class "<b>${className}</b>" and all its photos? This cannot be undone.</p>`);
  const okBtn = document.querySelector('#infoModal .btn-primary');
  okBtn.innerText = 'Delete';
  okBtn.style.backgroundColor = '#ff4d4d';
  okBtn.removeAttribute('onclick');
  okBtn.onclick = () => executeDeleteAttendanceClass(classId, className);
}

async function executeDeleteAttendanceClass(classId, className) {
  try {
    const res = await fetch(`/user/attendance/classes/${classId}`, {
      method: 'DELETE',
      credentials: 'include'
    });
    const data = await res.json();

    const okBtn = document.querySelector('#infoModal .btn-primary');
    okBtn.innerText = 'OK';
    okBtn.style.backgroundColor = '';
    okBtn.onclick = () => closeInfoModal();

    if (!res.ok || !data.success) {
      openInfoModal('Delete Failed', `<p style='color:#ff6b6b;'>${data.message || 'Could not delete class.'}</p>`);
      return;
    }
    openInfoModal('Class Deleted', `<p>Class "<b>${className}</b>" was deleted.</p>`);
  } catch (err) {
    console.error(err);
    openInfoModal('Delete Failed', `<p style='color:#ff6b6b;'>Server error. Try again.</p>`);
  }
}

/* ─── Original image upload (used in pipeline/combo mode) ─── */
function uploadAttendanceImages() {
  const input = document.createElement("input");
  input.type = "file";
  input.multiple = true;
  input.accept = "image/*";

  input.onchange = async () => {
    const files = input.files;
    const formData = new FormData();
    for (let file of files) formData.append("images", file);

    try {
      const res = await fetch("http://127.0.0.1:5000/upload_attendance_images", {
        method: "POST",
        body: formData
      });
      const data = await res.json();
      if (res.status === 200) {
        openInfoModal("Success", "<p>Images uploaded successfully.</p>");
      } else {
        openInfoModal("Upload Failed", `<p style='color: #ffbd2e;'>${data.message}</p>`);
      }
    } catch (err) {
      console.error(err);
      openInfoModal("Connection Error", "<p style='color: #ff6b6b;'>Server not reachable.</p>");
    }
  };

  input.click();
}

/* ─── Close dropdown on outside click ─── */
const modal = document.getElementById('cameraModal');
liveFeedImage.addEventListener("error", () => {
  showLiveFeedPlaceholder("Stream unavailable", "The selected camera could not be loaded. Check the backend server or camera URL.");
});

liveFeedImage.addEventListener("load", () => {
  if (currentCameraId) showLiveFeedStream(currentCameraId);
});

window.addEventListener('click', function (event) {
  if (event.target === modal) closeAddCamera();
  if (!event.target.closest('.camera-dropdown-wrapper')) closeCameraDropdown();
  if (_attDropdownEl && !event.target.closest('#attClassDropdown') && !event.target.closest('.images-btn')) {
    closeAttendanceDropdownMenu();
  }
  // Close split dropdown on outside click
  if (!event.target.closest('.split-dropdown-wrapper')) {
    document.getElementById('splitDropdownMenu')?.classList.remove('show');
  }
  if (!event.target.closest('.split-cam-dropdown-wrapper')) {
    document.querySelectorAll('.split-cam-dropdown-menu.show').forEach(m => m.classList.remove('show'));
  }
});

/* ═══════════════════════════════════════════════════════════════
   SPLIT VIEW SYSTEM
   Max 4 panels. Click a panel to focus/enlarge it. Click back to return.
════════════════════════════════════════════════════════════════ */

let currentSplitMode = 1;        // 1 = single, 2/3/4 = split
let splitCameras = {};           // { panelIndex: { cameraId, url } }
let focusedPanelIndex = null;    // which panel is currently focused
let splitPipelineActive = false; // true after uploadProject applied a pipeline in split mode

const splitGrid        = document.getElementById('splitGrid');
const splitFocusOverlay= document.getElementById('splitFocusOverlay');
const splitFocusImg    = document.getElementById('splitFocusImg');
const splitFocusPlaceholder = document.getElementById('splitFocusPlaceholder');

/* ── Toggle the split dropdown menu ── */
function toggleSplitMenu() {
  const menu = document.getElementById('splitDropdownMenu');
  menu.classList.toggle('show');
}

/* ── Set split mode (1 = single, 2/3/4 = grid) ── */
function setSplitMode(n) {
  currentSplitMode = n;
  document.getElementById('splitDropdownMenu').classList.remove('show');

  // Highlight active option
  document.querySelectorAll('.split-dropdown-menu button').forEach((btn, i) => {
    btn.classList.toggle('active-split', i + 1 === n);
  });

  if (n === 1) {
    // Restore single-camera view
    exitFocusMode();
    splitGrid.classList.remove('active', 'split-2', 'split-3', 'split-4');
    splitGrid.innerHTML = '';
    splitCameras = {};
    splitPipelineActive = false;

    // Show normal live feed elements
    document.getElementById('liveFeedPlaceholder').style.display = '';
    document.getElementById('live-feed').style.display = '';

    if (currentCameraId) {
      startCamera();
    } else {
      showLiveFeedPlaceholder("Camera idle", "Select a camera to start streaming");
    }
  } else {
    // Hide single-view elements
    document.getElementById('liveFeedPlaceholder').style.display = 'none';
    document.getElementById('live-feed').style.display = 'none';
    exitFocusMode();

    // Build grid
    splitGrid.className = 'split-grid active split-' + n;
    splitGrid.innerHTML = '';
    splitCameras = {};

    for (let i = 0; i < n; i++) {
      splitGrid.appendChild(buildSplitCell(i));
    }
  }
}

/* ── Build a single split panel ── */
function buildSplitCell(index) {
  const cell = document.createElement('div');
  cell.className = 'split-cell';
  cell.dataset.index = index;

  // Top bar
  const bar = document.createElement('div');
  bar.className = 'split-cell-bar';

  const label = document.createElement('span');
  label.className = 'split-cell-label';
  label.textContent = `Cam ${index + 1}`;

  // Custom dropdown wrapper
  const dropWrapper = document.createElement('div');
  dropWrapper.className = 'split-cam-dropdown-wrapper';

  const toggle = document.createElement('button');
  toggle.type = 'button';
  toggle.className = 'split-cam-dropdown-toggle';
  toggle.innerHTML = `<span class="split-cam-dropdown-label">Select Camera</span><span class="split-cam-dropdown-caret">▼</span>`;

  const menu = document.createElement('div');
  menu.className = 'split-cam-dropdown-menu';

  function buildSplitDropdownItems() {
    menu.innerHTML = '';
    if (cameras.length === 0) {
      const empty = document.createElement('div');
      empty.className = 'split-cam-dropdown-empty';
      empty.textContent = 'No cameras added yet';
      menu.appendChild(empty);
      return;
    }
    cameras.forEach(cam => {
      const item = document.createElement('div');
      item.className = 'split-cam-dropdown-item';

      const nameBtn = document.createElement('button');
      nameBtn.type = 'button';
      nameBtn.className = 'split-cam-dropdown-select';
      nameBtn.textContent = cam.name;
      nameBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        toggle.querySelector('.split-cam-dropdown-label').textContent = cam.name;
        menu.classList.remove('show');
        startSplitCell(index, cam.name, cam.url, cell);
      });

      item.appendChild(nameBtn);
      menu.appendChild(item);
    });
  }

  buildSplitDropdownItems();

  toggle.addEventListener('click', (e) => {
    e.stopPropagation();
    document.querySelectorAll('.split-cam-dropdown-menu.show').forEach(m => {
      if (m !== menu) m.classList.remove('show');
    });
    buildSplitDropdownItems();
    menu.classList.toggle('show');
  });

  dropWrapper.appendChild(toggle);
  dropWrapper.appendChild(menu);

  bar.appendChild(label);
  bar.appendChild(dropWrapper);
  cell.appendChild(bar);

  // Stream image
  const img = document.createElement('img');
  img.className = 'split-cell-img';
  img.alt = `Camera ${index + 1}`;
  img.onerror = () => { img.classList.remove('active'); showCellIdle(cell); };
  cell.appendChild(img);

  // Idle state
  const idle = document.createElement('div');
  idle.className = 'split-cell-idle';
  idle.innerHTML = `<span class="split-cell-idle-icon">📷</span><span>Select a camera</span>`;
  cell.appendChild(idle);

  // Expand hint
  const hint = document.createElement('span');
  hint.className = 'split-cell-expand';
  hint.textContent = '⤢ Focus';
  cell.appendChild(hint);

  // Click on cell body (not bar) → focus mode
  cell.addEventListener('click', (e) => {
    if (e.target.closest('.split-cell-bar')) return;
    enterFocusMode(index);
  });

  return cell;
}

/* ── Get the correct stream URL for a split panel ── */
function getSplitStreamUrl(cameraId, url) {
  if (splitPipelineActive) {
    return `http://127.0.0.1:5000/video_processed?camera_id=${encodeURIComponent(cameraId)}&t=${Date.now()}`;
  }
  return `http://127.0.0.1:5000/video_raw?url=${encodeURIComponent(url)}&t=${Date.now()}`;
}

/* ── Start streaming in a split cell ── */
function startSplitCell(index, cameraId, url, cellEl) {
  splitCameras[index] = { cameraId, url };

  const cell = cellEl || splitGrid.querySelector(`.split-cell[data-index="${index}"]`);
  if (!cell) return;

  const img  = cell.querySelector('.split-cell-img');
  const idle = cell.querySelector('.split-cell-idle');

  // Register this camera on the server so /video_processed can find its URL
  // Uses /register_camera which stores the URL without disrupting the main stream.
  fetch("http://127.0.0.1:5000/register_camera", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ camera_id: cameraId, url: url })
  }).catch(err => console.warn("register_camera failed for split panel:", err));

  img.src = getSplitStreamUrl(cameraId, url);
  img.classList.add('active');
  idle.style.display = 'none';

  // If this panel is currently focused, update focus view too
  if (focusedPanelIndex === index) {
    splitFocusImg.src = img.src;
    splitFocusImg.classList.add('active');
    splitFocusPlaceholder.classList.add('hidden');
  }
}

/* ── Stop streaming in a split cell ── */
function stopSplitCell(index) {
  delete splitCameras[index];

  const cell = splitGrid.querySelector(`.split-cell[data-index="${index}"]`);
  if (!cell) return;

  const img  = cell.querySelector('.split-cell-img');
  const idle = cell.querySelector('.split-cell-idle');

  img.classList.remove('active');
  img.removeAttribute('src');
  idle.style.display = '';

  if (focusedPanelIndex === index) {
    splitFocusImg.classList.remove('active');
    splitFocusImg.removeAttribute('src');
    splitFocusPlaceholder.classList.remove('hidden');
  }
}

/* ── Show idle state in a cell ── */
function showCellIdle(cell) {
  const idle = cell.querySelector('.split-cell-idle');
  if (idle) idle.style.display = '';
}

/* ── Enter focus mode for a panel ── */
function enterFocusMode(index) {
  focusedPanelIndex = index;
  const data = splitCameras[index];

  if (data) {
    splitFocusImg.src = getSplitStreamUrl(data.cameraId, data.url);
    splitFocusImg.classList.add('active');
    splitFocusPlaceholder.classList.add('hidden');
  } else {
    splitFocusImg.classList.remove('active');
    splitFocusImg.removeAttribute('src');
    splitFocusPlaceholder.classList.remove('hidden');
  }

  splitFocusOverlay.classList.add('active');
  splitGrid.style.display = 'none';
}

/* ── Exit focus mode, return to grid ── */
function exitFocusMode() {
  focusedPanelIndex = null;
  splitFocusOverlay.classList.remove('active');
  splitFocusImg.classList.remove('active');
  splitFocusImg.removeAttribute('src');
  splitFocusPlaceholder.classList.remove('hidden');

  if (currentSplitMode > 1) {
    splitGrid.style.display = '';
  }
}

/* ═══════════════════════════════════════════════════════════════
   FIRE & SMOKE ALERT SYSTEM
   Polls /fire_alert_status every second while Fire & Smoke
   Detection is active in any pipeline.  Shows non-blocking
   toasts — no overlay, no backdrop blur.
════════════════════════════════════════════════════════════════ */

let _firePollingTimer   = null;   // setInterval handle
let _fireDismissed      = { fire: false, smoke: false };  // user-dismissed this session

/* ── Start polling when fire detection is in the pipeline ── */
function startFirePolling() {
  if (_firePollingTimer !== null) return;  // already running
  _fireDismissed = { fire: false, smoke: false };
  _firePollingTimer = setInterval(_pollFireStatus, 1000);
  console.log('[FireAlert] Polling started');
}

/* ── Stop polling (pipeline changed / model removed) ── */
function stopFirePolling() {
  if (_firePollingTimer === null) return;
  clearInterval(_firePollingTimer);
  _firePollingTimer = null;
  // Hide any open toasts when the model is deactivated
  _hideFireToast('fire');
  _hideFireToast('smoke');
  console.log('[FireAlert] Polling stopped');
}

/* ── Single poll cycle ── */
async function _pollFireStatus() {
  try {
    const res  = await fetch('http://127.0.0.1:5000/fire_alert_status');
    if (!res.ok) return;
    const data = await res.json();

    _handleFireClass('fire',  data.fire,  '🔥 Fire detected continuously for 3 seconds!');
    _handleFireClass('smoke', data.smoke, '🌫️ Smoke detected continuously for 5 seconds!');

  } catch (_) {
    // Server unreachable — silently skip this tick
  }
}

/* ── Show / hide a single toast based on alert state ── */
function _handleFireClass(cls, info, defaultMessage) {
  if (!info) return;

  const toastId  = cls === 'fire' ? 'fireAlertToast' : 'smokeAlertToast';
  const subId    = cls === 'fire' ? 'fireAlertSub'   : 'smokeAlertSub';
  const toast    = document.getElementById(toastId);
  const subEl    = document.getElementById(subId);
  if (!toast) return;

  if (info.alert && !_fireDismissed[cls]) {
    // Build a dynamic sub-message with elapsed time
    const elapsed = info.elapsed_seconds.toFixed(0);
    const msg     = cls === 'fire'
      ? `Continuous detection for ${elapsed}s — evacuate immediately!`
      : `Continuous detection for ${elapsed}s — check ventilation!`;
    if (subEl) subEl.textContent = msg;

    // Show toast if not already visible
    if (toast.style.display === 'none') {
      toast.style.display = 'flex';
      // Stack second toast if the first is visible
      _repositionToasts();
    }
  } else if (!info.alert) {
    // Alert cleared — re-arm so it can show again next streak
    _fireDismissed[cls] = false;
    _hideFireToast(cls);
  }
}

/* ── Reposition stacked toasts so they don't overlap ── */
function _repositionToasts() {
  const fireToast  = document.getElementById('fireAlertToast');
  const smokeToast = document.getElementById('smokeAlertToast');
  if (!fireToast || !smokeToast) return;

  const fireVisible  = fireToast.style.display  !== 'none';
  const smokeVisible = smokeToast.style.display !== 'none';

  fireToast.style.top  = '72px';
  smokeToast.style.top = (fireVisible && smokeVisible) ? '160px' : '72px';
}

/* ── User dismissed a toast ── */
function dismissFireToast(cls) {
  _fireDismissed[cls] = true;
  _hideFireToast(cls);
}

function _hideFireToast(cls) {
  const toastId = cls === 'fire' ? 'fireAlertToast' : 'smokeAlertToast';
  const toast   = document.getElementById(toastId);
  if (toast) toast.style.display = 'none';
  _repositionToasts();
}

/* ── Hook into applyPipelineToCamera to auto start/stop polling ── */
const _origApplyPipeline = applyPipelineToCamera;
applyPipelineToCamera = async function(pipeline, cameraIds) {
  await _origApplyPipeline(pipeline, cameraIds);

  if (pipeline.includes('Fire & Smoke Detection')) {
    startFirePolling();
  } else {
    // If fire is not in this pipeline, stop only if no other
    // active camera still has it
    const anyFireActive = Object.values(cameraPipelines).some(
      p => Array.isArray(p) && p.includes('Fire & Smoke Detection')
    );
    if (!anyFireActive) stopFirePolling();
  }
};

/* ── Also stop polling when a block is deleted from the canvas ── */
const _origDeleteBlock = deleteBlock;
deleteBlock = function(id) {
  _origDeleteBlock(id);
  const pipeline = Array.from(blocks.values()).map(b => b.type);
  if (!pipeline.includes('Fire & Smoke Detection')) {
    stopFirePolling();
  }
};