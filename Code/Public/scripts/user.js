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
  const passwordRegex =/^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d!@#$%^&*()-_=+{};:,<.>]{8,}$/;

  if (!passwordRegex.test(password)) {
    alert(
      "Password not accepted.\n\n" +
      "Your password must:\n" +
      "• Be at least 8 characters long\n" +
      "• Contain at least one uppercase letter\n" +
      "• Contain at least one lowercase letter\n" +
      "• Contain at least one number\n" +
      "• Contain at least one special character (@$!%*?& etc.)"
    );
    return false;
  }


  return true;
}


document.addEventListener("DOMContentLoaded", () => {

  // Attach submit event to signup form
  const signupForm = document.getElementById('signup-form');

  if (!signupForm) return; // safety guard

  signupForm.addEventListener('submit', function(e) {
    e.preventDefault();

    if (!validateSignup()) return;

    const form = e.target;
    const fullName = form.querySelector('input[type="text"]').value.trim();
    const email = form.querySelector('input[type="email"]').value.trim();
    const password = form.querySelector('input[type="password"]').value.trim();

    console.log({ fullName, email, password });

    fetch('/addUser', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ fullName, email, password })
    })
    .then(res => res.json())
    .then(data => {
      alert(data.message || "Account created");
      form.reset();
      showLogin();
    })
    .catch(err => {
      console.error(err);
      alert('Something went wrong.');
    });
  });

});
