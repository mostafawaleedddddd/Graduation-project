let cameras = [];
const cameraPipelines = {};
let currentCameraId = null;

function openAddCamera() {
  document.getElementById("cameraModal").style.display = "block";
}
function closeAddCamera() {
  document.getElementById("cameraModal").style.display = "none";
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
    await fetch('/user/addCamera', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ name, url })
    });

    const select = document.getElementById("cameraSelect");
    const option = document.createElement("option");
    option.value = url;
    option.dataset.cameraId = name;
    option.textContent = name;
    select.appendChild(option);

    closeAddCamera();
    openInfoModal("Success", `<p>Camera "<b>${name}</b>" added successfully.</p>`);

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
  const select = document.getElementById('cameraSelect');
  if (select && select.value) return true;
  openInfoModal("Camera Required", "<p style='color: #ffbd2e;'>Please select a camera before adding models or uploading the pipeline.</p>");
  return false;
}

document.getElementById("cameraSelect").addEventListener("change", async function () {
  const url = this.value;
  if (!url) return;
  const cameraId = this.selectedOptions[0].dataset.cameraId || url;

  if (currentCameraId) {
    cameraPipelines[currentCameraId] = getCurrentPipelineFromBlocks();
  }

  await applyCameraSelection(cameraId, url);
});

function startCamera() {
  const img = document.getElementById("live-feed");
  const suffix = currentCameraId ? `camera_id=${encodeURIComponent(currentCameraId)}&` : "";
  img.src = `http://127.0.0.1:5000/video?${suffix}t=${new Date().getTime()}`;
}
window.onload = startCamera;

async function activateParkingMode() {
  await fetch("http://127.0.0.1:5000/init_parking", {
    method: "POST"
  });

  alert("Draw parking areas in the opened window, then press ESC");

  await fetch("http://127.0.0.1:5000/set_pipeline", {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      pipeline: ["Parking Management"]
    })
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
      <button class="images-btn">Images</button>
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
    block.querySelector('.images-btn').onclick = () => uploadAttendanceImages();
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
  b.element.style.top  = `${y}px`;
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

    if (!ensureCameraSelected()) {
      return;
    }

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
        pipeline[0] === "Parking Management" ||
        pipeline[0] === "Heatmap" ||
        pipeline[0] === "Object Detection" ||
        pipeline[0] === "Color Detection"
      );

    const isValid = isAllowedSingle || isAllowedCombo;

    if (!isValid) {
      const errorMsg = `
        <p style='color: #ff6b6b; margin-bottom: 10px;'>Invalid pipeline configuration!</p>
        <p><b>Allowed setups:</b></p>
        <ul style='color: #c9d1d9; line-height: 1.6;'>
            <li>Single model only</li>
            <li>Object Counting + Gap Detection</li>
            <li>Tracking + Attendance</li>
        </ul>
      `;
      openInfoModal("Pipeline Error", errorMsg);
      return;
    }

    // ================= SEND TO SERVER =================
    const response = await fetch("http://127.0.0.1:5000/set_pipeline", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pipeline, camera_id: currentCameraId || "default" })
    });

    if (!response.ok) throw new Error("Server error");

    const data = await response.json();

    openInfoModal("Models Applied", `<p>Successfully applied:<br><b>${pipeline.join(" &rarr; ")}</b></p>`);
    updateLiveFeed("Pipeline applied: " + pipeline.join(" → "));
    console.log("Backend pipeline:", data);

  } catch (err) {
    console.error(err);
    openInfoModal("Connection Error", "<p style='color: #ff6b6b;'>Backend is not running or unreachable.</p>");
    updateLiveFeed("Backend not running");
  }
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
// --- Modal Helper Functions ---
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

window.addEventListener('click', function(event) {
    if (event.target === infoModal) {
        closeInfoModal();
    }
});
//-------------------Attendence Buttons-------------------

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


function uploadAttendanceImages() {
    const input = document.createElement("input");
    input.type = "file";
    input.multiple = true;
    input.accept = "image/*";

    input.onchange = async () => {
        const files = input.files;
        const formData = new FormData();

        for (let file of files) {
            formData.append("images", file);
        }

        try {
            const res = await fetch("http://127.0.0.1:5000/upload_attendance_images", {
                method: "POST",
                body: formData
            });

            const data = await res.json();
            console.log("Upload response:", data);

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


document.addEventListener('DOMContentLoaded', () => {
  loadProjects();
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
      const select = document.getElementById("cameraSelect");
      for (let name in data.cameras) {
        const option = document.createElement("option");
        option.value = data.cameras[name];
        option.textContent = name;
        select.appendChild(option);
      }
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
});


const modal = document.getElementById('cameraModal');
function openAddCamera() {
    modal.classList.add('show');
}
function closeAddCamera() {
    modal.classList.remove('show');
    
    document.getElementById('cameraName').value = '';
    document.getElementById('cameraUrl').value = '';
}
window.onclick = function(event) {
    if (event.target === modal) {
        closeAddCamera();
    }
}

