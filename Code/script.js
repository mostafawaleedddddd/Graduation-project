const draggable = document.querySelector('.draggable');
const workspace = document.getElementById('workspace');

// Allow dropping
workspace.addEventListener('dragover', (e) => {
  e.preventDefault();
});

// Drop and clone
workspace.addEventListener('drop', (e) => {
  e.preventDefault();

  const rect = workspace.getBoundingClientRect();
  const x = e.clientX - rect.left;
  const y = e.clientY - rect.top;

  const clone = draggable.cloneNode(true);
  clone.classList.add('dropped');
  clone.style.left = `${x - 60}px`;
  clone.style.top = `${y - 20}px`;

  // Allow moving dropped nodes
  enableDrag(clone);
  workspace.appendChild(clone);
});

// Allow dragging of dropped nodes
function enableDrag(node) {
  let offsetX, offsetY;

  node.addEventListener('mousedown', (e) => {
    offsetX = e.offsetX;
    offsetY = e.offsetY;

    const move = (ev) => {
      ev.preventDefault();
      const rect = workspace.getBoundingClientRect();
      node.style.left = `${ev.clientX - rect.left - offsetX}px`;
      node.style.top = `${ev.clientY - rect.top - offsetY}px`;
    };

    const up = () => {
      document.removeEventListener('mousemove', move);
      document.removeEventListener('mouseup', up);
    };

    document.addEventListener('mousemove', move);
    document.addEventListener('mouseup', up);
  });
}
