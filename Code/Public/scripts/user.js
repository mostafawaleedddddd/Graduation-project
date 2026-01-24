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

// Validate signup form
function validateSignup() {
  const form = document.getElementById('signup-form');
  const fullName = form.querySelector('input[type="text"]').value.trim();
  const email = form.querySelector('input[type="email"]').value.trim();
  const password = form.querySelector('input[type="password"]').value.trim();
  const confirmPassword = form.querySelector('#confirm-password').value.trim();

  // Check required fields
  if (!fullName || !email || !password || !confirmPassword) {
    alert("Please fill all required fields.");
    return false;
  }

  // Name validation (no numbers, only letters, spaces, or hyphen)
  if (/\d/.test(fullName) || !/^[a-zA-Z\s-]+$/.test(fullName)) {
    alert("Invalid name. Only letters, spaces, and hyphens allowed.");
    return false;
  }

  // Email validation
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    alert("Invalid email address.");
    return false;
  }

  // Password match
  if (password !== confirmPassword) {
    alert("Passwords do not match.");
    return false;
  }

  // Password strength
  if (
    password.length < 8 ||
    !/[A-Z]/.test(password) ||
    !/[a-z]/.test(password) ||
    !/\d/.test(password) ||
    !/[!@#$%^&*()\-_=+{};:,<.>]/.test(password)
  ) {
    alert("Password must be at least 8 characters and include uppercase, lowercase, number, and special character.");
    return false;
  }

  return true;
}

// Attach submit event to signup form
document.getElementById('signup-form').addEventListener('submit', function(e) {
  e.preventDefault(); // Stop normal form submission

  if (!validateSignup()) return;

  const form = e.target;
  const fullName = form.querySelector('input[type="text"]').value.trim();
  const email = form.querySelector('input[type="email"]').value.trim();
  const password = form.querySelector('input[type="password"]').value.trim();
  console.log({ fullName, email, password });

  // Send AJAX POST
  fetch('/addUser', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ fullName, email, password })
  })
  .then(res => res.json())
  .then(data => {
    if (data.error) {
      alert(data.error);
    } else {
      alert(data.message);
      form.reset(); // Clear form
      showLogin();   // Switch to login tab
    }
  })
  .catch(err => {
    console.error(err);
    alert('Something went wrong. Try again.');
  });
});
