function startCamera() {
    const img = document.getElementById("cameraFeed");
    img.src = "http://127.0.0.1:5000/video";
}
window.onload = startCamera;
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
let updatePending = false;


/* ================= DRAG & DROP FROM SIDEBAR ================= */
canvas.addEventListener('dragover', e => e.preventDefault());

canvas.addEventListener('drop', e => {
    e.preventDefault();
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
    block.innerHTML = `
        <div class="block-title">${type}</div>
        <div class="block-controls">
            <button class="link-btn">Link</button>
            <button class="delete-btn">✕</button>
        </div>
        <div class="port top" data-port="top"></div>
        <div class="port bottom" data-port="bottom"></div>
        <div class="port left" data-port="left"></div>
        <div class="port right" data-port="right"></div>
    `;

    block.style.left = `${x - 70}px`;
    block.style.top = `${y - 40}px`;

    canvas.appendChild(block);

    blocks.set(id, {
        id,
        type,
        element: block,
        x: x - 70,
        y: y - 40
    });

    block.querySelector('.link-btn').onclick = () => toggleLinking(id);
    block.querySelector('.delete-btn').onclick = () => deleteBlock(id);

    makeBlockDraggable(id);
    updateLiveFeed(`Added ${type} block`);
    return  id;
}


/* ================= BLOCK DRAGGING ================= */
function makeBlockDraggable(id) {
    const el = document.getElementById(id);
    let offsetX, offsetY;

    el.addEventListener('mousedown', e => {
        if (e.target.tagName === 'BUTTON') return;

        draggedBlock = id;
        const rect = el.getBoundingClientRect();
        offsetX = e.clientX - rect.left;
        offsetY = e.clientY - rect.top;

        el.classList.add('selected');
    });

    document.addEventListener('mousemove', e => {
        if (draggedBlock !== id) return;

        const canvasRect = canvas.getBoundingClientRect();
        const x = e.clientX - canvasRect.left - offsetX;
        const y = e.clientY - canvasRect.top - offsetY;

        el.style.left = `${x}px`;
        el.style.top = `${y}px`;

        blocks.get(id).x = x;
        blocks.get(id).y = y;

        if (!updatePending) {
            updatePending = true;
            requestAnimationFrame(updateConnections);
        }
    });

    document.addEventListener('mouseup', () => {
        if (draggedBlock === id) {
            draggedBlock = null;
            el.classList.remove('selected');
        }
    });
}


/* ================= LINKING ================= */
function toggleLinking(id) {
    if (!linking) {
        linking = true;
        linkingFromBlock = id;
        document.getElementById(id)
            .querySelector('.link-btn')
            .classList.add('active');

        updateLiveFeed('Select another block to link');

    } else if (linkingFromBlock !== id) {

        createConnection(linkingFromBlock, id);

        document.getElementById(linkingFromBlock)
            .querySelector('.link-btn')
            .classList.remove('active');

        linking = false;
        linkingFromBlock = null;

        updateLiveFeed('Blocks connected');
    }
}


/* ================= CONNECTION LOGIC ================= */
function getClosestPorts(fromId, toId) {
    const ports = ['top', 'bottom', 'left', 'right'];
    let min = Infinity;
    let fromPort = 'right';
    let toPort = 'left';

    ports.forEach(fp => {
        ports.forEach(tp => {
            const a = blocks.get(fromId).element
                .querySelector(`[data-port="${fp}"]`).getBoundingClientRect();
            const b = blocks.get(toId).element
                .querySelector(`[data-port="${tp}"]`).getBoundingClientRect();

            const d = Math.hypot(a.left - b.left, a.top - b.top);
            if (d < min) {
                min = d;
                fromPort = fp;
                toPort = tp;
            }
        });
    });

    return { fromPort, toPort };
}

function getPortPosition(id, port) {
    const el = blocks.get(id).element.querySelector(`[data-port="${port}"]`);
    const pr = el.getBoundingClientRect();
    const cr = canvas.getBoundingClientRect();

    return {
        x: pr.left - cr.left + pr.width / 2,
        y: pr.top - cr.top + pr.height / 2
    };
}

function createConnection(from, to) {
    if (connections.find(c => c.from === from && c.to === to)) return;

    const ports = getClosestPorts(from, to);
    connections.push({ from, to, ...ports });
    updateConnections();
}

function updateConnections() {
    updatePending = false;
    svg.querySelectorAll('path').forEach(p => p.remove());

    connections.forEach(c => {
        const a = getPortPosition(c.from, c.fromPort);
        const b = getPortPosition(c.to, c.toPort);
        console.log(b, a);
        const midX = (a.x + b.x) / 2;

        const path = document.createElementNS(
            'http://www.w3.org/2000/svg',
            'path'
        );

        path.setAttribute(
            'd',
            `M ${a.x} ${a.y}
             C ${midX} ${a.y},
               ${midX} ${b.y},
               ${b.x} ${b.y}`
        );
        path.setAttribute('class', 'line');
        svg.appendChild(path);
    });
}


/* ================= DELETE BLOCK ================= */
function deleteBlock(id) {
    document.getElementById(id).remove();
    blocks.delete(id);

    for (let i = connections.length - 1; i >= 0; i--) {
        if (connections[i].from === id || connections[i].to === id) {
            connections.splice(i, 1);
        }
    }

    updateConnections();
    updateLiveFeed('Block removed');
}


/* ================= LIVE FEED LOG ================= */
function updateLiveFeed(msg) {
    const time = new Date().toLocaleTimeString();
    console.log(`[${time}] ${msg}`);
}

updateLiveFeed('System ready');

/* ================= PROJECT FUNCTIONS ================= */
function saveProject() {
    const pipeline = Array.from(blocks.values()).map(b => b.type);

    if (pipeline.length === 0) {
        alert("Cannot save empty project");
        return;
    }

    // 2️⃣ Ask for project name (simple for now)
    const name = prompt("Enter project name:");
    if (!name) return;

    // 3️⃣ Send to backend
        fetch('/user/projectsCreate', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            name,
            pipeline
        })
    })
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                updateLiveFeed(`Project "${name}" saved`);
                window.location.reload();
            } else {
                alert(data.message || "Failed to save project");
            }
        })
        .catch(err => {
            console.error(err);
            alert("Server error while saving project");
        });
}

/* 🔥 SEND PIPELINE TO BACKEND */
function uploadProject() {

    // 🔹 Collect pipeline from blocks (current simple order)
    const pipeline = Array.from(blocks.values()).map(b => b.type);

    fetch("http://127.0.0.1:5000/set_pipeline", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pipeline })
    })
        .then(res => res.json())
        .then(data => {
            updateLiveFeed("Pipeline applied: " + pipeline.join(" → "));
            console.log("Backend pipeline:", data.pipeline);
        })
        .catch(err => {
            console.error(err);
            updateLiveFeed("Backend not running");
        });
}


function loadProjects() {
  fetch('/user/Getprojects')
    .then(res => res.json())
    .then(data => {
      console.log("Projects response:", data);

      if (!data.success) {
        alert("Failed to load projects");
        return;
      }

      const select = document.getElementById('projectSelect');

      data.projects.forEach(project => {
        const opt = document.createElement('option');
        opt.value = project._id;
        opt.textContent = project.name;
        select.appendChild(opt);
      });
    })
    .catch(err => {
      console.error("Fetch projects error:", err);
    });
}
function loadProject(projectId) {
  fetch(`/user/projects/${projectId}`)
    .then(res => res.json())
    .then(data => {
      console.log("Loaded project:", data);

      if (!data.success) {
        alert("Failed to load project");
        return;
      }

      renderProjectBlocks(data.project.pipeline);
    })
    .catch(err => console.error(err));
}
function clearCanvasOnly() {
  blocks.forEach(b => b.element.remove());
  blocks.clear();
  connections.length = 0;
  blockCount = 0;
}
function renderProjectBlocks(pipeline) {
  console.log("Rendering pipeline:", pipeline);

  clearCanvasOnly();

  let x = 100;
  let y = 200;

  const orderedBlockIds = [];

  pipeline.forEach(type => {
    const blockId = createBlock(type, x, y);
    orderedBlockIds.push(blockId);
    x += 300;
  });

  // 🔥 IMPORTANT: wait for DOM paint before linking
  requestAnimationFrame(() => {
    autoConnectBlocksInOrder(orderedBlockIds);
    updateConnections(); // 👈 FORCE redraw
  });
}


function autoConnectBlocksInOrder(orderedBlockIds) {
    // remove old connections
    connections.length = 0;

    for (let i = 0; i < orderedBlockIds.length - 1; i++) {
        const fromId = orderedBlockIds[i];
        const toId = orderedBlockIds[i + 1];

        if (blocks.has(fromId) && blocks.has(toId)) {
            createConnection(fromId, toId);
        }
    }

    updateConnections();
}

document.addEventListener('DOMContentLoaded', () => {
      loadProjects();
    const dropdown = document.getElementById('projectSelect');
    if (!dropdown) return;

    fetch('/user/Getprojects')
        .then(res => {
            if (!res.ok) throw new Error('Failed to fetch projects');
            return res.json();
        })
        .then(data => {
            dropdown.innerHTML = '';

            if (!data.success || data.projects.length === 0) {
                dropdown.innerHTML = `<option value="">No projects found</option>`;
                return;
            }

            // Default option
            dropdown.innerHTML = `<option value="">Select a project</option>`;

            data.projects.forEach(project => {
                const option = document.createElement('option');
                option.value = project._id;
                option.textContent = project.name;
                dropdown.appendChild(option);
            });
        })
        .catch(err => {
            console.error(err);
            dropdown.innerHTML = `<option value="">Error loading projects</option>`;
        });

    // Handle project selection
    dropdown.addEventListener('change', () => {
        const projectId = dropdown.value;
        if (!projectId) return;
        loadProject(projectId);
        console.log('Selected project:', projectId);

        // Save selection (used later for Flask pipeline)
        localStorage.setItem('activeProjectId', projectId);
    });
});
