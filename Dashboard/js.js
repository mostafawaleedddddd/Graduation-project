// Navbar button functions
        function saveProject() {
            const projectData = {
                blocks: Array.from(blocks.values()).map(block => ({
                    id: block.id,
                    type: block.type,
                    x: block.x,
                    y: block.y
                })),
                connections: connections
            };
            console.log('Project saved:', projectData);
            updateLiveFeed('Project saved successfully!');
            
        }

        function uploadProject() {
            const input = document.createElement('input');
            input.type = 'file';
            input.accept = '.json';
            input.onchange = (e) => {
                const file = e.target.files[0];
                const reader = new FileReader();
                reader.onload = (event) => {
                    try {
                        const data = JSON.parse(event.target.result);
                        console.log('Project loaded:', data);
                        updateLiveFeed('Project uploaded successfully!');
                        // You can add logic here to reconstruct blocks from data
                    } catch (error) {
                        console.error('Invalid file format', error);
                        updateLiveFeed('Error: Invalid file format');
                    }
                };
                reader.readAsText(file);
            };
            input.click();
        }

        const canvas = document.getElementById('canvas');
        const svg = document.getElementById('connectionSvg');
        const functionalities = document.querySelectorAll('.functionality');
        const liveFeedContent = document.querySelector('.live-feed-content');

        let blockCount = 0;
        const blocks = new Map();
        const connections = [];
        let draggedBlock = null;
        let linking = false;
        let linkingFromBlock = null;
        let updatePending = false;

        // Make canvas droppable
        canvas.addEventListener('dragover', (e) => e.preventDefault());
        canvas.addEventListener('drop', (e) => {
            e.preventDefault();
            const type = e.dataTransfer.getData('text/plain');
            if (type) {
                const rect = canvas.getBoundingClientRect();
                const x = e.clientX - rect.left;
                const y = e.clientY - rect.top;
                createBlock(type, x, y);
            }
        });

        // Dragging from sidebar
        functionalities.forEach(func => {
            func.addEventListener('dragstart', (e) => {
                e.dataTransfer.effectAllowed = 'move';
                e.dataTransfer.setData('text/plain', func.dataset.type);
            });
        });

        function createBlock(type, x, y) {
            const blockId = `block-${blockCount++}`;
            const block = document.createElement('div');
            block.className = 'block';
            block.id = blockId;
            block.innerHTML = `
                <div class="block-title">${type.split(' ')[0]}</div>
                <div class="block-controls">
                    <button class="link-btn">Link</button>
                    <button class="delete-btn">✕</button>
                </div>
                <div class="port top" data-port="top"></div>
                <div class="port bottom" data-port="bottom"></div>
                <div class="port left" data-port="left"></div>
                <div class="port right" data-port="right"></div>
            `;
            block.style.left = (x - 70) + 'px';
            block.style.top = (y - 40) + 'px';

            canvas.appendChild(block);

            const blockData = {
                id: blockId,
                type: type,
                element: block,
                x: x - 70,
                y: y - 40,
                connections: []
            };

            blocks.set(blockId, blockData);

            const linkBtn = block.querySelector('.link-btn');
            const deleteBtn = block.querySelector('.delete-btn');

            linkBtn.addEventListener('click', () => toggleLinking(blockId, linkBtn));
            deleteBtn.addEventListener('click', () => deleteBlock(blockId));

            // Make block draggable
            makeBlockDraggable(blockId);
            updateLiveFeed(`Added ${type} block`);
        }

        function makeBlockDraggable(blockId) {
            const blockElement = document.getElementById(blockId);
            let offsetX, offsetY;

            blockElement.addEventListener('mousedown', (e) => {
                if (e.target.classList.contains('link-btn') || e.target.classList.contains('delete-btn')) return;
                
                draggedBlock = blockId;
                const rect = blockElement.getBoundingClientRect();
                offsetX = e.clientX - rect.left;
                offsetY = e.clientY - rect.top;

                blockElement.classList.add('selected');
            });

            document.addEventListener('mousemove', (e) => {
                if (draggedBlock !== blockId) return;

                const canvasRect = canvas.getBoundingClientRect();
                
                let x = e.clientX - canvasRect.left - offsetX;
                let y = e.clientY - canvasRect.top - offsetY;

                // Constrain within canvas
                x = Math.max(0, Math.min(x, canvasRect.width - blockElement.offsetWidth));
                y = Math.max(0, Math.min(y, canvasRect.height - blockElement.offsetHeight));

                blockElement.style.left = x + 'px';
                blockElement.style.top = y + 'px';

                blocks.get(draggedBlock).x = x;
                blocks.get(draggedBlock).y = y;

                if (!updatePending) {
                    updatePending = true;
                    requestAnimationFrame(updateConnections);
                }
            });

            document.addEventListener('mouseup', () => {
                if (draggedBlock === blockId) {
                    blockElement.classList.remove('selected');
                    draggedBlock = null;
                }
            });
        }

        function toggleLinking(blockId, linkBtn) {
            if (linking && linkingFromBlock === blockId) {
                // Toggle off
                linking = false;
                linkingFromBlock = null;
                linkBtn.classList.remove('active');
                updateLiveFeed('Linking cancelled');
            } else if (linking && linkingFromBlock !== blockId) {
                // Create connection
                createConnection(linkingFromBlock, blockId);
                document.getElementById(linkingFromBlock).querySelector('.link-btn').classList.remove('active');
                linking = false;
                linkingFromBlock = null;
                updateLiveFeed(`Connected blocks`);
            } else {
                // Toggle on
                linking = true;
                linkingFromBlock = blockId;
                linkBtn.classList.add('active');
                updateLiveFeed(`Select another block to link...`);
            }
        }

        function getClosestPorts(fromBlockId, toBlockId) {
            const fromBlock = blocks.get(fromBlockId).element;
            const toBlock = blocks.get(toBlockId).element;

            const fromRect = fromBlock.getBoundingClientRect();
            const toRect = toBlock.getBoundingClientRect();

            const ports = ['top', 'bottom', 'left', 'right'];
            let minDistance = Infinity;
            let closestFromPort = 'right';
            let closestToPort = 'left';

            ports.forEach(fromPort => {
                ports.forEach(toPort => {
                    const fromPortEl = fromBlock.querySelector(`.port[data-port="${fromPort}"]`);
                    const toPortEl = toBlock.querySelector(`.port[data-port="${toPort}"]`);

                    const fromPortRect = fromPortEl.getBoundingClientRect();
                    const toPortRect = toPortEl.getBoundingClientRect();

                    const distance = Math.hypot(
                        fromPortRect.left - toPortRect.left,
                        fromPortRect.top - toPortRect.top
                    );

                    if (distance < minDistance) {
                        minDistance = distance;
                        closestFromPort = fromPort;
                        closestToPort = toPort;
                    }
                });
            });

            return { fromPort: closestFromPort, toPort: closestToPort };
        }

        function getPortPosition(blockId, port) {
            const blockElement = blocks.get(blockId).element;
            const portEl = blockElement.querySelector(`.port[data-port="${port}"]`);
            const portRect = portEl.getBoundingClientRect();
            const canvasRect = canvas.getBoundingClientRect();

            return {
                x: portRect.left - canvasRect.left + portRect.width / 2,
                y: portRect.top - canvasRect.top + portRect.height / 2
            };
        }

        function createConnection(fromId, toId) {
            const connectionId = `${fromId}-${toId}`;
            if (!connections.find(c => c.from === fromId && c.to === toId)) {
                const ports = getClosestPorts(fromId, toId);
                connections.push({ 
                    from: fromId, 
                    to: toId, 
                    id: connectionId,
                    fromPort: ports.fromPort,
                    toPort: ports.toPort
                });
                updateConnections();
            }
        }

        function updateConnections() {
            updatePending = false;
            
            svg.querySelectorAll('path').forEach(path => path.remove());

            connections.forEach(conn => {
                const fromBlock = blocks.get(conn.from);
                const toBlock = blocks.get(conn.to);

                if (fromBlock && toBlock) {
                    const fromPos = getPortPosition(conn.from, conn.fromPort);
                    const toPos = getPortPosition(conn.to, conn.toPort);

                    const line = document.createElementNS('http://www.w3.org/2000/svg', 'path');
                    const midX = (fromPos.x + toPos.x) / 2;
                    line.setAttribute('d', `M ${fromPos.x} ${fromPos.y} C ${midX} ${fromPos.y}, ${midX} ${toPos.y}, ${toPos.x} ${toPos.y}`);
                    line.setAttribute('class', 'line');
                    svg.appendChild(line);
                }
            });
        }

        function deleteBlock(blockId) {
            const blockElement = document.getElementById(blockId);
            blockElement.style.opacity = '0';
            blockElement.style.transform = 'scale(0.8)';
            
            connections.splice(0, connections.length, ...connections.filter(c => c.from !== blockId && c.to !== blockId));
            updateConnections();
            
            setTimeout(() => {
                blockElement.remove();
                blocks.delete(blockId);
                updateLiveFeed('Block removed');
            }, 200);
        }

        function updateLiveFeed(message) {
            const timestamp = new Date().toLocaleTimeString();
            liveFeedContent.innerHTML = `<span>[${timestamp}] ${message}</span>`;
        }

        // Initial message
        updateLiveFeed('System ready. Drag blocks to canvas.');