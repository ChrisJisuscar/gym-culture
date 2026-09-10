/**
 * culture-carousel.js
 * Round Carousel 3D para la sección CULTURAS (GYM CULTURE).
 *
 * Cards organizadas en un cilindro 3D (rotateY + translateZ) con:
 *  - auto-rotación lenta y suave siempre activa (una vuelta ~26 s)
 *  - drag con mouse y touch
 *  - momentum / inercia al soltar
 *  - reanudación gradual tras un delay al soltar (sin saltos)
 *  - énfasis en la card frontal (brightness / opacity / scale)
 *  - distinción click vs drag para no navegar accidentalmente
 *
 * Un único requestAnimationFrame.
 */
;(function () {
  'use strict'

  var SECTION_ID = 'culture'

  var section = document.getElementById(SECTION_ID)
  if (!section) return

  var stage = section.querySelector('.culture-carousel__stage')
  var ring = section.querySelector('.culture-carousel__ring')
  var cards = Array.prototype.slice.call(section.querySelectorAll('.culture-card'))
  if (!stage || !ring || !cards.length) return

  /* ── Parámetros ───────────────────────────────────── */

  var CONFIG = {
    // Animación
    AUTO_ROTATION_SPEED: 360 / 26, // deg/s → una vuelta ~26 s
    FRICTION: 0.95,                // decaimiento del momentum por frame
    MOMENTUM_STOP: 0.02,           // deg/frame bajo el cual se detiene el momentum
    RESUME_DELAY: 2000,            // ms de espera antes de reanudar auto-rotación
    RESUME_RAMP_SEC: 2,            // s que tarda en recuperar velocidad plena

    // Geometría 3D
    TILT: -5,                      // inclinación del anillo (°)
    SPACING_FACTOR: 0.42,          // hueco entre cards ≈ 42% del ancho (↑ separa las laterales)

    // Interacción
    DRAG_SENSITIVITY: 0.5,         // grados por px de drag
    DRAG_THRESHOLD: 8              // px para distinguir click vs drag
  }

  // Tamaños de card según viewport (proporción vertical ~ 1.47:1).
  var CARD_SIZES = {
    mobile: { width: 280, height: 430 },
    smallTablet: { width: 310, height: 470 },
    tablet: { width: 340, height: 515 },
    notebook: { width: 340, height: 515 },
    desktop: { width: 380, height: 560 }
  }

  /* ── Estado ───────────────────────────────────────── */

  var angle = 0
  var velocity = 0
  var dragging = false
  var rafId = null
  var lastTime = 0

  // geometría cacheada
  var cardAngles = []     // ángulo base de cada card
  var radius = 0          // radio del cilindro (px)
  var cardW = 0
  var cardH = 0

  // drag state
  var pointerId = null
  var lastX = 0
  var lastY = 0
  var dragDist = 0        // acumulado para detectar click vs drag

  /* ── Mirilla de interacción (click vs drag) ───────── */

  var suppressClickUntil = 0
  section.addEventListener('click', function (e) {
    if (Date.now() < suppressClickUntil) {
      e.preventDefault()
      e.stopPropagation()
    }
  }, true)

  /* ── Utilidades ───────────────────────────────────── */

  function clamp(v, lo, hi) {
    return v < lo ? lo : (v > hi ? hi : v)
  }

  /* Normaliza un ángulo a (-180, 180]. */
  function normalizeDeg(deg) {
    var d = ((deg % 360) + 360) % 360
    return d > 180 ? d - 360 : d
  }

  /* ── Medición / layout (solo al iniciar / resize) ─── */

  function measure() {
    var w = stage.clientWidth
    var h = window.innerHeight

    // tamaño de card según viewport (ancho y alto)
    var size
    if (w <= 520 || h <= 520) {
      size = CARD_SIZES.mobile
    } else if (w <= 760) {
      size = CARD_SIZES.smallTablet
    } else if (w <= 1024) {
      size = CARD_SIZES.tablet
    } else if (h <= 800) {
      // notebook: algo menor
      size = CARD_SIZES.notebook
    } else {
      size = CARD_SIZES.desktop
    }
    cardW = size.width
    cardH = size.height

    // radio: separa las cards para que las laterales no queden pegadas.
    // Cuerda entre centros = cardW + hueco; radio = cuerda / (2·sin(π/n)).
    var chord = cardW * (1 + CONFIG.SPACING_FACTOR)
    radius = Math.round(chord / (2 * Math.sin(Math.PI / cards.length)))

    // no dejar que las cards laterales salgan del ancho del carrusel
    var maxRadius = Math.floor(stage.clientWidth / 2 - cardW / 2)
    if (maxRadius > cardW / 2) {
      radius = Math.min(radius, maxRadius)
    }

    // aplicar tamaño a las cards
    cards.forEach(function (card) {
      card.style.width = cardW + 'px'
      card.style.height = cardH + 'px'
      card.style.marginLeft = (-cardW / 2) + 'px'
      card.style.marginTop = (-cardH / 2) + 'px'
    })
  }

  /* ── Render del anillo + caras ────────────────────── */

  var prevAngles = new Array(cards.length).fill(-999)

  function render() {
    // anillo
    ring.style.transform =
      'rotateX(' + CONFIG.TILT + 'deg) rotateY(' + angle.toFixed(3) + 'deg)'

    // por card: orientación respecto a la cámara
    var n = cards.length
    for (var i = 0; i < n; i++) {
      var facing = normalizeDeg(cardAngles[i] + angle)
      var abs = Math.abs(facing)
      // proporción 0 (frontal) → 1 (de espaldas)
      var t = clamp(abs / 180, 0, 1)

      var brightness = 1 - t * 0.45          // frontal 1, trasera ~0.55
      var opacity = 1 - t * 0.35             // frontal 1, trasera ~0.65
      var scale = 1 - t * 0.05               // frontal 1, trasera ~0.95

      // solo escribir si cambia de forma relevante
      if (Math.abs(prevAngles[i] - facing) > 0.25 || prevAngles[i] === -999) {
        prevAngles[i] = facing
        var card = cards[i]
        card.style.opacity = opacity.toFixed(3)
        card.style.filter = 'brightness(' + brightness.toFixed(3) + ')'
        card.style.transform =
          'scale(' + scale.toFixed(4) + ') rotateY(' + cardAngles[i].toFixed(3) + 'deg) translateZ(' + radius + 'px)'
      }
    }
  }

  /* ── Loop principal (único) ───────────────────────── */

  // Estado de reanudación de la auto-rotación
  var resumeAt = 0          // timestamp en el que se reanuda tras el drag
  var autoSpeedFactor = 1   // 0..1, rampa progresiva al reanudar

  function loop(now) {
    if (lastTime === 0) lastTime = now
    var dt = Math.min((now - lastTime) / 1000, 0.05)
    lastTime = now

    if (dragging) {
      // durante drag no se anima: la posición la aporta onMove
    } else if (velocity !== 0) {
      // momentum
      angle += velocity
      velocity *= CONFIG.FRICTION
      if (Math.abs(velocity) < CONFIG.MOMENTUM_STOP) {
        velocity = 0
        autoSpeedFactor = 0 // preparar rampa de reanudación
      }
    } else {
      // auto-rotación lenta siempre activa (pausando solo durante drag/momentum)
      if (now >= resumeAt) {
        // rampa progresiva para un retorno sin saltos
        autoSpeedFactor = Math.min(autoSpeedFactor + dt / CONFIG.RESUME_RAMP_SEC, 1)
        // hacia la derecha (ángulo decreciente en rotateY)
        angle -= CONFIG.AUTO_ROTATION_SPEED * dt * autoSpeedFactor
      }
    }

    render()
    rafId = requestAnimationFrame(loop)
  }

  function startLoop() {
    if (rafId) return
    lastTime = 0
    rafId = requestAnimationFrame(loop)
  }

  /* ── Drag ─────────────────────────────────────────── */

  function pointFromEvent(e) {
    if (e.touches && e.touches[0]) return { x: e.touches[0].clientX, y: e.touches[0].clientY }
    if (e.clientX !== undefined) return { x: e.clientX, y: e.clientY }
    return { x: lastX, y: lastY }
  }

  function onPointerDown(e) {
    // solo botón primario / touch
    if (e.touches && e.touches.length !== 1) return
    if (e.button !== undefined && e.button !== 0) return

    var p = pointFromEvent(e)
    dragging = true
    velocity = 0          // detener momentum
    autoSpeedFactor = 0   // no reanimar a mitad del drag
    pointerId = e.pointerId || 1
    lastX = p.x
    lastY = p.y
    dragDist = 0
    stage.classList.add('is-dragging')

    stage.addEventListener('pointermove', onPointerMove)
    window.addEventListener('pointerup', onPointerUp)
    window.addEventListener('pointercancel', onPointerUp)
  }

  function onPointerMove(e) {
    if (!dragging) return
    var pid = e.pointerId || 1
    if (pid !== pointerId) return
    var p = pointFromEvent(e)
    var dx = p.x - lastX
    var dy = p.y - lastY
    lastX = p.x
    lastY = p.y

    angle += dx * CONFIG.DRAG_SENSITIVITY
    dragDist += Math.abs(dx) + Math.abs(dy)
    // velocidad en deg/frame aprox (para momentum)
    velocity = dx * CONFIG.DRAG_SENSITIVITY * 2
  }

  function onPointerUp() {
    if (!dragging) return
    dragging = false
    stage.classList.remove('is-dragging')
    stage.removeEventListener('pointermove', onPointerMove)
    window.removeEventListener('pointerup', onPointerUp)
    window.removeEventListener('pointercancel', onPointerUp)

    // si hubo arrastre, suprimir el click de esta card momentáneamente
    if (dragDist > CONFIG.DRAG_THRESHOLD) {
      suppressClickUntil = Date.now() + 250
    }

    // armar la reanudación: esperar el delay y acelerar progresivamente
    resumeAt = performance.now() + CONFIG.RESUME_DELAY
    autoSpeedFactor = 0
  }

  stage.addEventListener('pointerdown', onPointerDown)
  stage.addEventListener('mousedown', function (e) { if (e.preventDefault) e.preventDefault() })

  /* ── Inicialización ───────────────────────────────── */

  function build() {
    var step = 360 / cards.length
    cardAngles = cards.map(function (_, i) { return i * step })
    measure()
    render()
    startLoop()
  }

  var resizeTimer = null
  window.addEventListener('resize', function () {
    clearTimeout(resizeTimer)
    resizeTimer = setTimeout(function () {
      measure()
      render()
    }, 120)
  }, { passive: true })

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', build)
  } else {
    build()
  }
})()
