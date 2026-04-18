const loginForm = document.getElementById("login-form");
const signupForm = document.getElementById("signup-form");
const tabs = document.querySelectorAll(".tab");

function showLogin() {
  loginForm.classList.remove("hidden");
  signupForm.classList.add("hidden");
  tabs[0].classList.add("active");
  tabs[1].classList.remove("active");
}

function showSignup() {
  signupForm.classList.remove("hidden");
  loginForm.classList.add("hidden");
  tabs[1].classList.add("active");
  tabs[0].classList.remove("active");
}

/* PASSWORD TOGGLE */
function togglePassword(inputId, eye) {
  const input = document.getElementById(inputId);
  const icon = eye.querySelector("i");

  if (input.type === "password") {
    input.type = "text";
    icon.classList.remove("fa-eye");
    icon.classList.add("fa-eye-slash");
  } else {
    input.type = "password";
    icon.classList.remove("fa-eye-slash");
    icon.classList.add("fa-eye");
  }
}



document.addEventListener("DOMContentLoaded", () => {
  const params = new URLSearchParams(window.location.search);
  const mode = params.get("mode");
  mode === "signup" ? showSignup() : showLogin();
});
