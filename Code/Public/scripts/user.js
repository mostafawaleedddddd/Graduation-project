// Toggle password visibility
function togglePassword(inputId, icon) {
  const input = document.getElementById(inputId);
  if (input.type === "password") {
    input.type = "text";
    icon.innerHTML = '<i class="fa-solid fa-eye-slash"></i>';
  } else {
    input.type = "password";
    icon.innerHTML = '<i class="fa-solid fa-eye"></i>';
  }
}

// Show Signup form
function showSignup() {
  document.getElementById('login-form').classList.add('hidden');
  document.getElementById('signup-form').classList.remove('hidden');
}

document.addEventListener("DOMContentLoaded", () => {

  const passwordInput = document.getElementById("password");
  const popup = document.getElementById("password-popup");

  const rules = {
    length: document.getElementById("rule-length"),
    upper: document.getElementById("rule-upper"),
    lower: document.getElementById("rule-lower"),
    number: document.getElementById("rule-number"),
    special: document.getElementById("rule-special"),
    space: document.getElementById("rule-space"),
  };

  function updateRules(value) {
    let passed = 0;

    if (value.length >= 8 && value.length <= 20) {
      rules.length.innerHTML = "✅ 8–20 characters";
      passed++;
    } else rules.length.innerHTML = "❌ 8–20 characters";

    if (/[A-Z]/.test(value)) {
      rules.upper.innerHTML = "✅ At least one capital letter";
      passed++;
    } else rules.upper.innerHTML = "❌ At least one capital letter";

    if (/[a-z]/.test(value)) {
      rules.lower.innerHTML = "✅ At least one lowercase letter";
      passed++;
    } else rules.lower.innerHTML = "❌ At least one lowercase letter";

    if (/\d/.test(value)) {
      rules.number.innerHTML = "✅ At least one number";
      passed++;
    } else rules.number.innerHTML = "❌ At least one number";

    if (/[@$!%*?&]/.test(value)) {
      rules.special.innerHTML = "✅ At least one special character";
      passed++;
    } else rules.special.innerHTML = "❌ At least one special character";

    if (!/\s/.test(value)) {
      rules.space.innerHTML = "✅ No spaces";
      passed++;
    } else rules.space.innerHTML = "❌ No spaces";

    // Hide popup ONLY when all pass (like image)
    if (passed === 6) {
      popup.classList.add("hidden");
    } else {
      popup.classList.remove("hidden");
    }
  }

  // Show popup when user interacts
  passwordInput.addEventListener("focus", () => {
    popup.classList.remove("hidden");
  });

  passwordInput.addEventListener("input", () => {
    updateRules(passwordInput.value);
  });

  passwordInput.addEventListener("blur", () => {
    if (!passwordInput.value) popup.classList.add("hidden");
  });

});

/* ============================
   FORM VALIDATION (CLEANED)
============================ */
function validateSignup() {
  const form = document.getElementById('signup-form');

  const fullName = form.querySelector('input[type="text"]').value.trim();
  const email = form.querySelector('input[type="email"]').value.trim();
  const password = document.getElementById('password').value.trim();
  const confirmPassword = document.getElementById('confirm-password').value.trim();

  if (!fullName || !email || !password || !confirmPassword) {
    alert("Please fill all required fields.");
    return false;
  }

  if (password !== confirmPassword) {
    alert("Passwords do not match.");
    return false;
  }

  // Final hard check (popup already guided user)
  const passwordRegex =
    /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[^\s]{8,20}$/;

  if (!passwordRegex.test(password)) {
    alert("Password does not meet all requirements.");
    return false;
  }

  return true;
}
function createUser(fullName, email, password) {
  fetch('/addUser', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ fullName, email, password })
  })
    .then(res => res.json())
    .then(() => {
      window.location.href = "/successful-login";
    })
    .catch(err => {
      console.error(err);
      alert('Something went wrong.');
    });
}

document.addEventListener("DOMContentLoaded", () => {
  const signupForm = document.getElementById('signup-form');
  if (!signupForm) return;

  signupForm.addEventListener('submit', function (e) {
    e.preventDefault();
    if (!validateSignup()) return;

    const form = e.target;
    const fullName = form.querySelector('input[type="text"]').value.trim();
    const email = form.querySelector('input[type="email"]').value.trim();
    const password = document.getElementById('password').value.trim();
    fetch('/checkUser', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password })
    })
      .then(res => res.json())
      .then(data => {
          if (data.success) {
            showError(data.message || 'This Account already exists.');
          } else {
            createUser(fullName, email, password);
          }
        })
      .catch(err => {
        console.error(err);
        showError('Something went wrong. Please try again.');
      });

  });
});


function showError(message) {
  const modal = document.getElementById('error-modal');
  const msgElement = document.getElementById('modal-message');
  msgElement.textContent = message;
  modal.classList.remove('hidden');
}
function closeModal() {
  const modal = document.getElementById('error-modal');
  modal.classList.add('hidden');
}

document.addEventListener("DOMContentLoaded", () => {
  const loginForm = document.getElementById('login-form');
  if (!loginForm) return;

  loginForm.addEventListener('submit', function (e) {
    e.preventDefault();

    const email = loginForm.querySelector('input[type="email"]').value.trim();
    const password = document.getElementById('login-password').value.trim();

    if (!email || !password) {
      alert("Please enter email and password");
      return;
    }
    console.log(email, password);
    fetch('/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password })
    })
      .then(res => res.json())
      .then(data => {
        if (data.success) {
          // ✅ login success
          window.location.href = "/user"; // dashboard
        } else {
          // ❌ wrong credentials
          alert(data.message || "Wrong credentials");
        }
      })
      .catch(err => {
        console.error(err);
        alert("Something went wrong");
      });
  });
});
