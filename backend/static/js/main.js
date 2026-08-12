const toggle = document.querySelector('.menu-toggle');
const menu = document.querySelector('.mobile-menu');
const nav = document.querySelector('.nav-shell');

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

const navLinks = document.querySelectorAll('.desktop-nav a');
const sections = [...document.querySelectorAll('main section[id]')];
const updateNavigation = () => {
  nav?.classList.toggle('is-scrolled', window.scrollY > 12);
  const active = sections.reduce((current, section) => (
    window.scrollY >= section.offsetTop - 130 ? section : current
  ), null);
  navLinks.forEach((link) => link.classList.toggle('is-active', link.getAttribute('href') === `#${active?.id}`));
};
window.addEventListener('scroll', updateNavigation, { passive: true });
updateNavigation();

const revealItems = document.querySelectorAll('.section, .custom-section, .brand-section, .community, .newsletter');
if ('IntersectionObserver' in window) {
  revealItems.forEach((item) => item.classList.add('reveal'));
  const observer = new IntersectionObserver((entries) => entries.forEach(({ isIntersecting, target }) => {
    if (isIntersecting) { target.classList.add('is-visible'); observer.unobserve(target); }
  }), { threshold: .08 });
  revealItems.forEach((item) => observer.observe(item));
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
