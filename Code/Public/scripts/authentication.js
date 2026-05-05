/* ═══════════════════════════════════════════════════════
   ModuVision — authentication.js
   Matches index.ejs design system exactly
═══════════════════════════════════════════════════════ */

/* ══════════════════════════════════════════════════════
   CUSTOM CURSOR
══════════════════════════════════════════════════════ */
(function initCursor() {
  const cursor = document.getElementById('cursor');
  const ring   = document.getElementById('cursorRing');
  if (!cursor || !ring) return;

  let mx = 0, my = 0, rx = 0, ry = 0;

  document.addEventListener('mousemove', e => {
    mx = e.clientX;
    my = e.clientY;
  });

  function animateCursor() {
    cursor.style.transform = `translate(${mx - 6}px, ${my - 6}px)`;
    rx += (mx - rx) * 0.12;
    ry += (my - ry) * 0.12;
    ring.style.transform = `translate(${rx - 20}px, ${ry - 20}px)`;
    requestAnimationFrame(animateCursor);
  }
  animateCursor();

  // Cursor scale on interactive elements
  document.querySelectorAll('a, button, input, .tab, .eye, .submit-btn').forEach(el => {
    el.addEventListener('mouseenter', () => {
      cursor.style.transform += ' scale(1.5)';
      ring.style.width  = '56px';
      ring.style.height = '56px';
      ring.style.borderColor = 'rgba(0,198,255,0.6)';
    });
    el.addEventListener('mouseleave', () => {
      ring.style.width  = '40px';
      ring.style.height = '40px';
      ring.style.borderColor = 'rgba(0,198,255,0.4)';
    });
  });
})();

/* ══════════════════════════════════════════════════════
   FLOATING PARTICLES CANVAS
══════════════════════════════════════════════════════ */
(function initParticles() {
  const canvas = document.getElementById('auth-particles');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');

  function resize() {
    canvas.width  = window.innerWidth;
    canvas.height = window.innerHeight;
  }
  resize();
  window.addEventListener('resize', resize);

  const particles = Array.from({ length: 70 }, () => ({
    x:  Math.random() * window.innerWidth,
    y:  Math.random() * window.innerHeight,
    vx: (Math.random() - 0.5) * 0.6,
    vy: (Math.random() - 0.5) * 0.4,
    size: Math.random() * 1.8 + 0.4,
    color: Math.random() > 0.55 ? '#00C6FF' : '#FF00CC',
    opacity: Math.random() * 0.5 + 0.15,
    trail: []
  }));

  function drawFrame() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // Faint grid lines
    ctx.strokeStyle = 'rgba(0,198,255,0.025)';
    ctx.lineWidth = 0.5;
    for (let x = 0; x < canvas.width; x += 60) {
      ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, canvas.height); ctx.stroke();
    }
    for (let y = 0; y < canvas.height; y += 60) {
      ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(canvas.width, y); ctx.stroke();
    }

    particles.forEach(p => {
      // Trail
      p.trail.push({ x: p.x, y: p.y });
      if (p.trail.length > 12) p.trail.shift();

      for (let i = 1; i < p.trail.length; i++) {
        const alpha = (i / p.trail.length) * p.opacity * 0.4;
        const col = p.color === '#00C6FF'
          ? `rgba(0,198,255,${alpha})`
          : `rgba(255,0,204,${alpha})`;
        ctx.strokeStyle = col;
        ctx.lineWidth = (i / p.trail.length) * p.size;
        ctx.beginPath();
        ctx.moveTo(p.trail[i-1].x, p.trail[i-1].y);
        ctx.lineTo(p.trail[i].x,   p.trail[i].y);
        ctx.stroke();
      }

      // Dot
      const dotCol = p.color === '#00C6FF'
        ? `rgba(0,198,255,${p.opacity})`
        : `rgba(255,0,204,${p.opacity})`;
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
      ctx.fillStyle = dotCol;
      ctx.shadowColor = p.color;
      ctx.shadowBlur  = 8;
      ctx.fill();
      ctx.shadowBlur  = 0;

      // Connections between nearby particles
      particles.forEach(other => {
        const dx = p.x - other.x;
        const dy = p.y - other.y;
        const dist = Math.sqrt(dx*dx + dy*dy);
        if (dist < 90 && dist > 0) {
          ctx.strokeStyle = `rgba(0,198,255,${(1 - dist/90) * 0.08})`;
          ctx.lineWidth = 0.5;
          ctx.beginPath();
          ctx.moveTo(p.x, p.y);
          ctx.lineTo(other.x, other.y);
          ctx.stroke();
        }
      });

      // Move
      p.x += p.vx;
      p.y += p.vy;
      if (p.x < 0) p.x = canvas.width;
      if (p.x > canvas.width)  p.x = 0;
      if (p.y < 0) p.y = canvas.height;
      if (p.y > canvas.height) p.y = 0;
    });

    requestAnimationFrame(drawFrame);
  }
  drawFrame();
})();

/* ══════════════════════════════════════════════════════
   TAB SWITCHING
══════════════════════════════════════════════════════ */
const loginForm  = document.getElementById('login-form');
const signupForm = document.getElementById('signup-form');
const tabs       = document.querySelectorAll('.tab');

function showLogin() {
  loginForm.classList.remove('hidden');
  signupForm.classList.add('hidden');
  tabs[0].classList.add('active');
  tabs[1].classList.remove('active');
  // re-trigger entrance animation
  loginForm.style.animation = 'none';
  requestAnimationFrame(() => {
    loginForm.style.animation = '';
  });
}

function showSignup() {
  signupForm.classList.remove('hidden');
  loginForm.classList.add('hidden');
  tabs[1].classList.add('active');
  tabs[0].classList.remove('active');
  signupForm.style.animation = 'none';
  requestAnimationFrame(() => {
    signupForm.style.animation = '';
  });
}

/* ══════════════════════════════════════════════════════
   URL PARAM — auto open login or signup
══════════════════════════════════════════════════════ */
document.addEventListener('DOMContentLoaded', () => {
  const params = new URLSearchParams(window.location.search);
  const mode   = params.get('mode');
  mode === 'signup' ? showSignup() : showLogin();
});

/* ══════════════════════════════════════════════════════
   PASSWORD VISIBILITY TOGGLE
══════════════════════════════════════════════════════ */
function togglePassword(inputId, eyeEl) {
  const input = document.getElementById(inputId);
  const icon  = eyeEl.querySelector('i');
  if (!input || !icon) return;

  if (input.type === 'password') {
    input.type = 'text';
    icon.classList.replace('fa-eye', 'fa-eye-slash');
  } else {
    input.type = 'password';
    icon.classList.replace('fa-eye-slash', 'fa-eye');
  }
}

/* ══════════════════════════════════════════════════════
   PASSWORD STRENGTH RULES
══════════════════════════════════════════════════════ */
(function initPasswordRules() {
  const passwordInput = document.getElementById('password');
  const popup         = document.getElementById('password-popup');
  if (!passwordInput || !popup) return;

  const rules = {
    'rule-length':  v => v.length >= 8 && v.length <= 20,
    'rule-upper':   v => /[A-Z]/.test(v),
    'rule-lower':   v => /[a-z]/.test(v),
    'rule-number':  v => /\d/.test(v),
    'rule-special': v => /[!@#$%^&*()_+\-=\[\]{};':"\\|,.<>\/?]/.test(v),
    'rule-space':   v => !/\s/.test(v),
  };

  passwordInput.addEventListener('focus', () => popup.classList.remove('hidden'));
  passwordInput.addEventListener('blur',  () => {
    setTimeout(() => popup.classList.add('hidden'), 200);
  });

  passwordInput.addEventListener('input', () => {
    const val = passwordInput.value;
    popup.classList.remove('hidden');

    Object.entries(rules).forEach(([id, test]) => {
      const li      = document.getElementById(id);
      const icon    = li ? li.querySelector('.rule-icon') : null;
      const passing = test(val);

      if (li) li.classList.toggle('valid', passing);
      if (icon) icon.textContent = passing ? '✓' : '✕';
    });
  });
})();

/* ══════════════════════════════════════════════════════
   INPUT FOCUS GLOW — icon color sync
══════════════════════════════════════════════════════ */
document.querySelectorAll('.input-wrap input').forEach(input => {
  const wrap = input.closest('.input-wrap');
  const icon = wrap ? wrap.querySelector('.input-icon') : null;

  input.addEventListener('focus', () => {
    if (icon) icon.style.color = '#00C6FF';
  });
  input.addEventListener('blur', () => {
    if (icon) icon.style.color = '';
  });
});

/* ══════════════════════════════════════════════════════
   MODAL HELPERS
══════════════════════════════════════════════════════ */
function showModal(message) {
  const modal = document.getElementById('error-modal');
  const msg   = document.getElementById('modal-message');
  if (!modal) return;
  if (msg && message) msg.textContent = message;
  modal.classList.remove('hidden');
}

function closeModal() {
  const modal = document.getElementById('error-modal');
  if (modal) modal.classList.add('hidden');
}

const closeBtn = document.getElementById('close-modal');
if (closeBtn) closeBtn.addEventListener('click', closeModal);
