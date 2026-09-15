// DOM-only orbit. It shares the Custom Lab's animation clock, never starts a RAF.
const ORBIT_MOTION = Object.freeze({ periodSeconds: 30, dragSensitivity: .009, maximumInertia: 1.2, friction: 4, resumeDelayMs: 1800, resumeDurationMs: 1200 });
export class RecommendationOrbit {
  constructor(stage, track, onSelect) {
    this.stage = stage; this.track = track; this.onSelect = onSelect;
    this.angle = Math.PI / 2; this.velocity = 0; this.lastInteraction = -10000;
    this.visible = false; this.buttons = []; this.activeId = null;
    this.observer = new IntersectionObserver(([entry]) => { this.visible = entry.isIntersecting; });
    this.observer.observe(stage);
    this.pointerDown = event => {
      if (this.drag || event.target.closest('.recommendation-center') || event.button > 0) return;
      this.drag = { id: event.pointerId, x: event.clientX, start: event.clientX, time: performance.now(), moved: false };
      this.velocity = 0; this.lastInteraction = performance.now();
    };
    this.pointerMove = event => {
      if (!this.drag || event.pointerId !== this.drag.id) return;
      if (event.pointerType === 'mouse' && !event.buttons) { this.pointerUp(event); return; }
      const now = performance.now(); const dx = event.clientX - this.drag.x;
      if (Math.abs(event.clientX - this.drag.start) > 6) this.drag.moved = true;
      if (this.drag.moved) {
        stage.setPointerCapture(event.pointerId);
        this.angle += dx * ORBIT_MOTION.dragSensitivity;
        this.velocity = Math.max(-ORBIT_MOTION.maximumInertia, Math.min(ORBIT_MOTION.maximumInertia, dx * ORBIT_MOTION.dragSensitivity / Math.max((now - this.drag.time) / 1000, .016)));
        this.layout(); event.preventDefault();
      }
      this.drag.x = event.clientX; this.drag.time = now; this.lastInteraction = now;
    };
    this.pointerUp = event => {
      if (!this.drag || event.pointerId !== this.drag.id) return;
      this.suppressClick = this.drag.moved ? performance.now() + 150 : 0;
      this.lastInteraction = this.drag.moved ? performance.now() : -10000;
      this.drag = null;
      if (stage.hasPointerCapture(event.pointerId)) stage.releasePointerCapture(event.pointerId);
    };
    this.click = event => {
      const button = event.target.closest('[data-orbit-id]');
      if (button && performance.now() > (this.suppressClick || 0)) onSelect(Number(button.dataset.orbitId));
    };
    stage.addEventListener('pointerdown', this.pointerDown);
    stage.addEventListener('pointermove', this.pointerMove);
    stage.addEventListener('pointerup', this.pointerUp);
    stage.addEventListener('pointercancel', this.pointerUp);
    // Pointer release outside the stage must never leave auto-rotation paused.
    window.addEventListener('pointerup', this.pointerUp);
    stage.addEventListener('lostpointercapture', this.pointerUp);
    this.blur = () => { if (!this.drag) return; this.drag = null; this.velocity = 0; this.lastInteraction = performance.now(); };
    window.addEventListener('blur', this.blur);
    track.addEventListener('click', this.click);
    this.resize = new ResizeObserver(() => this.layout()); this.resize.observe(stage);
    this.unsubscribe = GymCulture3D.subscribeFrame((time, delta) => {
      if (!this.visible) return;
      if (!this.drag) {
        const auto = Math.min(1, Math.max(0, (time - this.lastInteraction - ORBIT_MOTION.resumeDelayMs) / ORBIT_MOTION.resumeDurationMs));
        const decay = Math.exp(-delta * ORBIT_MOTION.friction);
        this.angle += Math.PI * 2 / ORBIT_MOTION.periodSeconds * auto * delta + this.velocity * (1 - decay) / ORBIT_MOTION.friction;
        this.velocity *= decay;
      }
      this.layout();
    });
  }
  setItems(items, activeId) {
    this.activeId = activeId;
    this.buttons = items.filter(item => item.id !== activeId).map(item => {
      const button = document.createElement('button'); button.type = 'button'; button.className = 'orbit-preview'; button.dataset.orbitId = item.id;
      button.setAttribute('aria-label', `Ver ${item.name} en 3D`);
      const image = document.createElement('img'); image.src = item.preview_url || item.preview_image_url; image.alt = ''; image.loading = 'lazy'; image.draggable = false;
      const name = document.createElement('span'); name.textContent = item.name;
      const thumbnail = document.createElement('div'); thumbnail.className = 'orbit-thumbnail'; thumbnail.append(image);
      button.append(thumbnail, name); return button;
    });
    this.track.replaceChildren(...this.buttons); this.layout();
  }
  layout() {
    const width = this.stage.clientWidth, height = this.stage.clientHeight;
    if (!width || !height) return;
    const mobile = matchMedia('(max-width: 680px)').matches;
    const count = this.buttons.length;
    const cardWidth = this.buttons[0]?.offsetWidth || 0, cardHeight = this.buttons[0]?.offsetHeight || 0;
    this.buttons.forEach((button, index) => {
      const theta = this.angle + index * Math.PI * 2 / count;
      const depth = (Math.cos(theta) + 1) / 2;
      const scale = .86 + depth * .14;
      const spread = value => value / (.4 + .6 * Math.abs(value));
      const radiusX = width / 2 - cardWidth / 2 - 12;
      const radiusY = mobile ? 104 : height / 2 - cardHeight / 2 - 18;
      const x = width / 2 + spread(Math.sin(theta)) * radiusX;
      const y = (mobile ? height - 210 : height / 2) + spread(Math.cos(theta)) * radiusY;
      button.style.transform = `translate(-50%, -50%) translate(${x}px, ${y}px) scale(${scale})`;
      button.style.opacity = String(.7 + depth * .3);
      button.style.zIndex = String(2 + Math.round(depth * 5));
      button.hidden = false;
      button._orbit = { x, y, width: cardWidth * scale, height: cardHeight * scale, depth };
    });
    // Crowded catalogs keep the frontmost previews legible; all remain reachable
    // through navigation as they travel into an available part of the orbit.
    const visible = [];
    [...this.buttons].sort((a, b) => b._orbit.depth - a._orbit.depth).forEach(button => {
      const box = button._orbit;
      const overlaps = visible.some(other => Math.abs(box.x - other.x) < (box.width + other.width) / 2 + 12 && Math.abs(box.y - other.y) < (box.height + other.height) / 2 + 12);
      button.style.visibility = overlaps ? 'hidden' : 'visible';
      button.inert = overlaps;
      if (!overlaps) visible.push(box);
    });
  }
  nudge(direction) { this.angle += direction * Math.PI / Math.max(this.buttons.length, 2); this.layout(); }
  dispose() {
    this.unsubscribe(); this.observer.disconnect(); this.resize.disconnect();
    this.stage.removeEventListener('pointerdown', this.pointerDown);
    this.stage.removeEventListener('pointermove', this.pointerMove);
    this.stage.removeEventListener('pointerup', this.pointerUp);
    this.stage.removeEventListener('pointercancel', this.pointerUp);
    window.removeEventListener('pointerup', this.pointerUp);
    this.stage.removeEventListener('lostpointercapture', this.pointerUp);
    window.removeEventListener('blur', this.blur);
    this.track.removeEventListener('click', this.click);
  }
}
