document.addEventListener('DOMContentLoaded', () => {
  const form = document.querySelector('[data-auth-form]');
  if (!form) return;
  const message = form.querySelector('.auth-message');
  const submit = form.querySelector('[type="submit"]');
  form.querySelectorAll('.password-toggle').forEach((button) => button.addEventListener('click', () => {
    const input = button.previousElementSibling;
    const hidden = input.type === 'password';
    input.type = hidden ? 'text' : 'password';
    button.textContent = hidden ? 'OCULTAR' : 'VER';
    button.setAttribute('aria-label', hidden ? 'Ocultar contraseña' : 'Mostrar contraseña');
  }));
  const showMessage = (text, error = true) => {
    message.textContent = text;
    message.classList.toggle('is-error', error);
    message.classList.toggle('is-success', !error);
  };
  const apiError = async (response) => {
    const data = await response.json().catch(() => ({}));
    const detail = data.detail || Object.values(data).flat().join(' ');
    return detail || 'No pudimos completar la solicitud. Intentá de nuevo.';
  };
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (!form.checkValidity()) { form.reportValidity(); return; }
    const payload = Object.fromEntries(new FormData(form));
    const isRegister = form.dataset.authForm === 'register';
    submit.disabled = true;
    showMessage(isRegister ? 'Creando tu cuenta...' : 'Validando acceso...', false);
    try {
      const endpoint = isRegister ? '/api/auth/register/' : '/api/auth/login/';
      const response = await fetch(endpoint, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
      if (!response.ok) throw new Error(await apiError(response));
      if (isRegister) {
        showMessage('Cuenta creada. Iniciá sesión para entrar a la cultura.', false);
        form.reset();
        setTimeout(() => window.location.assign('/login/'), 650);
        return;
      }
      window.GymCultureAuth.save(await response.json());
      window.GymCultureAuth.updateNavbar();
      const next = new URLSearchParams(window.location.search).get('next');
      const destination = next && next.startsWith('/') && !next.startsWith('//') ? next : '/';
      window.location.assign(destination);
    } catch (error) { showMessage(error.message); }
    finally { submit.disabled = false; }
  });
});
