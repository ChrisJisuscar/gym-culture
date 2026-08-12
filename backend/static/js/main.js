const toggle = document.querySelector('.menu-toggle');
const menu = document.querySelector('.mobile-menu');

if (toggle && menu) {
  toggle.addEventListener('click', () => {
    const open = toggle.getAttribute('aria-expanded') === 'true';
    toggle.setAttribute('aria-expanded', String(!open));
    menu.classList.toggle('is-open', !open);
  });
  menu.querySelectorAll('a').forEach((link) => link.addEventListener('click', () => {
    toggle.setAttribute('aria-expanded', 'false');
    menu.classList.remove('is-open');
  }));
}

const form = document.querySelector('#newsletter-form');
const note = document.querySelector('#form-note');
if (form && note) form.addEventListener('submit', (event) => {
  event.preventDefault();
  const email = form.elements.email;
  if (!email.validity.valid) {
    note.textContent = 'Ingresá un email válido.';
    email.focus();
    return;
  }
  note.textContent = 'Gracias. Te avisaremos cuando sea el momento.';
  form.reset();
});
