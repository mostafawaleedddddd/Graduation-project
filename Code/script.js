// Global state for connection management
let isConnecting = false;
let startNode = null;
let currentLine = null;
let nodeIdCounter = 0; // To give each dropped node a unique ID
const connections = [];
const draggableItems = document.querySelectorAll('.draggable');
const workspace = document.getElementById('workspace');

// --- 1. Attach dragstart event to EVERY draggable item (Kept from previous) ---
draggableItems.forEach(item => {
  item.addEventListener('dragstart', (e) => {
    e.dataTransfer.setData('text/html', e.target.outerHTML);
    e.target.classList.add('dragging');
  });

  item.addEventListener('dragend', (e) => {
    e.target.classList.remove('dragging');
  });
});


// --- 2. Allow dropping (Kept from previous) ---
workspace.addEventListener('dragover', (e) => {
  e.preventDefault();
});


// --- 3. Drop and clone (Crucial updates here) ---
workspace.addEventListener('drop', (e) => {
  e.preventDefault();

  const htmlData = e.dataTransfer.getData('text/html');

  // Safety check: only proceed if valid data
  if (!htmlData) return;

  const tempDiv = document.createElement('div');
  tempDiv.innerHTML = htmlData;
  const clone = tempDiv.firstChild;

  if (!clone || !clone.classList.contains('draggable')) return;

  const rect = workspace.getBoundingClientRect();
  const x = e.clientX - rect.left;
  const y = e.clientY - rect.top;

  // --- NEW: Set up the clone's structure and controls ---
  const title = clone.querySelector('strong').textContent;
  const description = clone.querySelector('p').textContent;

  // Create the new interior HTML structure
  clone.innerHTML = `
        <div style="display: flex; align-items: center; justify-content: space-between;">
            <div style="display: flex; align-items: center;">
                <span class="connector-point"></span>
                <strong>${title}</strong>
            </div>
            <div class="dropped-controls">
                <button class="node-action-btn link-btn">Link</button>
                <button class="node-action-btn to-btn">To</button>
            </div>
        </div>
        <p>${description}</p>
    `;

  // Clean up clone attributes
  clone.removeAttribute('draggable');
  clone.classList.remove('draggable');
  clone.classList.add('dropped');
  clone.id = `node-${nodeIdCounter++}`; // Give it a unique ID

  // Position the clone
  clone.style.left = `${x - 60}px`;
  clone.style.top = `${y - 20}px`;

  // Enable moving and connection
  enableDrag(clone);
  setupConnectionLogic(clone); // NEW FUNCTION CALL
  workspace.appendChild(clone);
});


// --- 4. Enable dragging of dropped nodes (Kept from previous) ---
function enableDrag(node) {
  let offsetX, offsetY;

  node.addEventListener('mousedown', (e) => {
    if (e.button !== 0 || isConnecting || e.target.closest('.node-action-btn')) return;
    e.stopPropagation();

    offsetX = e.offsetX;
    offsetY = e.offsetY;

    const move = (ev) => {
      ev.preventDefault();
      const rect = workspace.getBoundingClientRect();

      // Move node
      node.style.left = `${ev.clientX - rect.left - offsetX}px`;
      node.style.top = `${ev.clientY - rect.top - offsetY}px`;

      // Update all connected lines in real time
      requestAnimationFrame(() => {
        connections.forEach(conn => {
          if (conn.startNodeId === node.id || conn.endNodeId === node.id) {
            redrawLine(conn);
          }
        });
      });
    };

    const up = () => {
      document.removeEventListener('mousemove', move);
      document.removeEventListener('mouseup', up);
    };

    document.addEventListener('mousemove', move);
    document.addEventListener('mouseup', up);
  });
}




// ... (Keep all code above setupConnectionLogic as is) ...

// --- 5. Connection Logic (UPDATED) ---

function setupConnectionLogic(node) {
  const linkBtn = node.querySelector('.link-btn');
  const toBtn = node.querySelector('.to-btn');

  // Logic for the 'Link' button (start connection)
  linkBtn.addEventListener('click', (e) => {
    e.stopPropagation();

    if (!isConnecting) {
      // START connection mode
      isConnecting = true;
      startNode = node;
      node.classList.add('connecting-mode');

      // Create the temporary line element
      currentLine = document.createElement('div');
      currentLine.classList.add('connection-line', 'temp'); // Added 'temp' class
      workspace.appendChild(currentLine);

      document.addEventListener('mousemove', drawLine);
      document.addEventListener('mouseup', cancelConnection);

    } else if (startNode === node) {
      // Clicking the same node again cancels
      cancelConnection(false); // Pass false: connection was NOT completed
    }
  });

  // Logic for the 'To' button (complete connection)
  toBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    if (isConnecting && startNode && startNode !== node) {
      // COMPLETE connection
      connectNodes(startNode, node);
      cancelConnection(true); // Pass true: connection WAS completed
    }
  });
}

function drawLine(e) {
  if (!isConnecting || !startNode || !currentLine) return;

  // Use the function to get the correct connection point coordinates
  const startCoords = getNodeConnectionPoint(startNode, 'output');

  const workspaceRect = workspace.getBoundingClientRect();

  const startX = startCoords.x;
  const startY = startCoords.y;

  const endX = e.clientX - workspaceRect.left;
  const endY = e.clientY - workspaceRect.top;

  // Use vector math to position and rotate the line
  const dx = endX - startX;
  const dy = endY - startY;
  const length = Math.sqrt(dx * dx + dy * dy);
  const angle = Math.atan2(dy, dx) * 180 / Math.PI;

  currentLine.style.width = `${length}px`;
  currentLine.style.transform = `translate(${startX}px, ${startY}px) rotate(${angle}deg)`;
  currentLine.style.transformOrigin = '0 0';
}

function connectNodes(nodeA, nodeB) {
  // safety checks
  if (!nodeA || !nodeB) return;

  // get coordinates
  const startCoords = getNodeConnectionPoint(nodeA, 'output');
  const endCoords = getNodeConnectionPoint(nodeB, 'input');

  // geometry
  const dx = endCoords.x - startCoords.x;
  const dy = endCoords.y - startCoords.y;
  const length = Math.sqrt(dx * dx + dy * dy);
  const angle = Math.atan2(dy, dx) * 180 / Math.PI;

  // ensure currentLine is an element and inside workspace
  if (!currentLine) {
    console.error('connectNodes called but currentLine is null');
    return;
  }
  // set required styles
  currentLine.style.position = 'absolute';
  currentLine.style.top = '0';
  currentLine.style.left = '0';
  currentLine.style.transformOrigin = '0 0';
  currentLine.classList.remove('temp');
  currentLine.classList.add('permanent-connection');

  // finalize transform
  currentLine.style.width = `${length}px`;
  currentLine.style.transform = `translate(${startCoords.x}px, ${startCoords.y}px) rotate(${angle}deg)`;

  // ensure the line is a child of workspace
  if (currentLine.parentNode !== workspace) {
    workspace.appendChild(currentLine);
  }

  // store connection (store direct DOM reference)
  connections.push({
    lineElement: currentLine,
    startNodeId: nodeA.id,
    endNodeId: nodeB.id
  });

  // reset
  currentLine = null;

  console.log(`Connection created: ${nodeA.id} -> ${nodeB.id}`);
}

/**
 * Helper function to calculate the precise coordinates of the connection points
 * @param {HTMLElement} node The node element.
 * @param {string} type 'input' for the .connector-point (green dot) or 'output' for the .link-btn
 * @returns {{x: number, y: number}} Workspace relative coordinates
 */
function getNodeConnectionPoint(node, type) {
  // Defensive checks
  if (!node || !workspace) return { x: 0, y: 0 };

  // Force layout recalculation so we read up-to-date metrics
  const workspaceRect = workspace.getBoundingClientRect();

  // Default fallback: center-left or center-right of node
  const nodeRect = node.getBoundingClientRect();
  let x = nodeRect.left - workspaceRect.left + (type === 'output' ? nodeRect.width : 0);
  let y = nodeRect.top - workspaceRect.top + (nodeRect.height / 2);

  // choose target element
  let targetElement = null;
  if (type === 'output') {
    targetElement = node.querySelector('.link-btn');
  } else { // input
    targetElement = node.querySelector('.connector-point');
  }

  if (targetElement) {
    const tRect = targetElement.getBoundingClientRect();
    // center of target
    x = tRect.left - workspaceRect.left + (tRect.width / 2);
    y = tRect.top - workspaceRect.top + (tRect.height / 2);

    // for output use right edge
    if (type === 'output') x = tRect.right - workspaceRect.left;
  }

  return { x, y };
}


/**
 * Cleans up the state and temporary line.
 * @param {boolean} wasCompleted True if the line was successfully connected.
 */
function cancelConnection(wasCompleted) {
  isConnecting = false;

  if (startNode) {
    startNode.classList.remove('connecting-mode');
  }
  startNode = null;

  // IMPORTANT: Only remove the line if the connection was NOT completed.
  // If it was completed, 'currentLine' now holds the permanent line.
  if (currentLine && !wasCompleted) {
    currentLine.remove();
  }
  currentLine = null;

  document.removeEventListener('mousemove', drawLine);
  document.removeEventListener('mouseup', cancelConnection);
}

/**
 * Redraws a single connection line based on the current positions of its nodes.
 @param {object} connectionObj - An object from the connections array.
 */
function redrawLine(conn) {
  const line = document.getElementById(conn.id);
  const startNode = document.getElementById(conn.startNodeId);
  const endNode = document.getElementById(conn.endNodeId);

  if (!line || !startNode || !endNode) return;

  const workspaceRect = workspace.getBoundingClientRect();
  const startPort = startNode.querySelector('.output-port');
  const endPort = endNode.querySelector('.input-port');

  const startRect = startPort.getBoundingClientRect();
  const endRect = endPort.getBoundingClientRect();

  // Compute positions relative to workspace
  const startX = startRect.left - workspaceRect.left + startRect.width / 2;
  const startY = startRect.top - workspaceRect.top + startRect.height / 2;
  const endX = endRect.left - workspaceRect.left + endRect.width / 2;
  const endY = endRect.top - workspaceRect.top + endRect.height / 2;

  // Draw a smooth cubic Bézier curve between nodes
  const dx = Math.abs(endX - startX) * 0.5;
  line.setAttribute('d', `M ${startX} ${startY} C ${startX + dx} ${startY}, ${endX - dx} ${endY}, ${endX} ${endY}`);
}
