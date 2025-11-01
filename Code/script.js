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
                <div class="port input"></div>
                <div class="port output"></div>
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

                updateConnections();
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

        function createConnection(fromId, toId) {
            const connectionId = `${fromId}-${toId}`;
            if (!connections.find(c => c.from === fromId && c.to === toId)) {
                connections.push({ from: fromId, to: toId, id: connectionId });
                updateConnections();
            }
        }

        function updateConnections() {
            svg.querySelectorAll('path').forEach(path => path.remove());

            connections.forEach(conn => {
                const fromBlock = blocks.get(conn.from);
                const toBlock = blocks.get(conn.to);

                if (fromBlock && toBlock) {
                    const fromRect = fromBlock.element.getBoundingClientRect();
                    const toRect = toBlock.element.getBoundingClientRect();
                    const canvasRect = canvas.getBoundingClientRect();

                    const x1 = fromRect.right - canvasRect.left;
                    const y1 = fromRect.top - canvasRect.top + fromRect.height / 2;
                    const x2 = toRect.left - canvasRect.left;
                    const y2 = toRect.top - canvasRect.top + toRect.height / 2;

                    const line = document.createElementNS('http://www.w3.org/2000/svg', 'path');
                    const midX = (x1 + x2) / 2;
                    line.setAttribute('d', `M ${x1} ${y1} C ${midX} ${y1}, ${midX} ${y2}, ${x2} ${y2}`);
                    line.setAttribute('class', 'line');
                    svg.appendChild(line);
                }
            });
        }

        function deleteBlock(blockId) {
            const blockElement = document.getElementById(blockId);
            blockElement.style.opacity = '0';
            blockElement.style.transform = 'scale(0.8)';
            
            setTimeout(() => {
                blockElement.remove();
                blocks.delete(blockId);
                connections = connections.filter(c => c.from !== blockId && c.to !== blockId);
                updateConnections();
                updateLiveFeed('Block removed');
            }, 200);
        }

        function updateLiveFeed(message) {
            const timestamp = new Date().toLocaleTimeString();
            liveFeedContent.innerHTML = `<span>[${timestamp}] ${message}</span>`;
        }

        // Initial message
        updateLiveFeed('System ready. Drag blocks to canvas.');