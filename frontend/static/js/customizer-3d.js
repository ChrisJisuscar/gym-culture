// ============================================================================
// GYM CULTURE — Customizer 3D (FASE 2)
// ----------------------------------------------------------------------------
// Carga la remera 3D (models/tshirt.glb) con GLTFLoader, la encuadra por
// bounding box, habilita OrbitControls tipo configurador de producto y
// sincroniza color/lado con customizer.js vía window.GymCulture3D.
//
// Regla de oro: si CUALQUIER paso falla (Three.js, GLTFLoader, GLB, renderer,
// materiales), se registra el error en consola y el Custom Lab 2D sigue
// funcionando sin cambios. El 2D solo se oculta cuando el modelo 3D ya está
// listo y renderizando.
//
// Este archivo es un módulo ES y NO interfiere con customizer.js, que sigue
// siendo un script clásico con toda la lógica 2D actual.
// ============================================================================

import * as THREE from '/static/vendor/three/three.module.min.js';
import { GLTFLoader } from '/static/vendor/three/loaders/GLTFLoader.js';
import { OrbitControls } from '/static/vendor/three/controls/OrbitControls.js';

const Customizer3D = (() => {
  const container = document.querySelector('#customizer-3d-container');
  const MODEL_URL = '/static/models/tshirt.glb';

  // Paleta equivalente a la del 2D (customizer.js) para que el color de la
  // remera 3D coincida con el mockup recoloreado. No es un selector nuevo:
  // solo el mapa nombre -> hex que consume setColor().
  const COLOR_HEX = {
    'Negro': 0x111015,
    'Blanco': 0xebe9e4,
    'Gris': 0x7a7780,
    'Violeta': 0x7c3aed,
    'Azul oscuro': 0x182238,
    'Rojo': 0x9f233d,
    'Verde oscuro': 0x19382e,
  };

  // Instancias internas de la escena.
  let scene = null;
  let camera = null;
  let renderer = null;
  let controls = null;
  let resizeObserver = null;
  let animationFrameId = null;
  let isInitialized = false;
  let modelReady = false;

  // Prenda y estado de integración.
  let shirtGroup = null;      // grupo centrado que contiene la malla
  let fabricMaterials = [];   // materiales de tela detectados dinámicamente
  let targetYaw = 0;          // lado mostrado (front/back) — FASE 2 solo orientación

  const CONFIG = {
    fieldOfView: 40,
    nearPlane: 0.01,
    farPlane: 500,
    // Fracción de la altura del visor que debe ocupar la camiseta.
    fillRatio: 0.72,
    controls: {
      minPolarAngle: 0.35,            // no mirar excesivamente desde arriba
      maxPolarAngle: Math.PI * 0.72,  // nunca por debajo de la prenda
      // Rango de zoom amplio y continuo: desde muy cerca (sin atravesar la
      // tela) hasta muy lejos, con pasos suaves por muesca de rueda.
      minDistanceFactor: 0.38,
      maxDistanceFactor: 2.8,
      enableDamping: true,
      // Damping bajo: el dolly (zoom) queda progresivo en lugar de brusco.
      dampingFactor: 0.06,
      enablePan: false,               // configurador: rotar + zoom, no desplazar
      // Velocidad de zoom baja: cada muesca de rueda multiplica la distancia
      // por 2^(0.95·zoomSpeed) ≈ 1.18, un paso pequeño y progresivo. Con
      // zoomSpeed=1 el salto era ~1.93× por muesca (zoom "en saltos").
      zoomSpeed: 0.25,
      rotateSpeed: 0.85,
    },
  };

  // Dimensión mínima de respaldo: mientras el contenedor esté oculto mide 0 px
  // y Three.js no admite un canvas de tamaño 0.
  const MIN_DIMENSION = 1;

  const safeSize = () => ({
    width: Math.max(container?.clientWidth || 0, MIN_DIMENSION),
    height: Math.max(container?.clientHeight || 0, MIN_DIMENSION),
  });

  // Escena con fondo transparente: el gradiente oscuro violáceo vive en CSS
  // (customizer.css) para mantener la identidad visual en un solo lugar.
  const createScene = () => {
    scene = new THREE.Scene();
  };

  // Cámara en perspectiva: simula el ojo humano mirando la prenda.
  const createCamera = () => {
    const { width, height } = safeSize();
    const aspect = width / height;
    camera = new THREE.PerspectiveCamera(
      CONFIG.fieldOfView,
      aspect,
      CONFIG.nearPlane,
      CONFIG.farPlane
    );
    // Posición provisoria: fitCameraToModel() la recalcula con el bounding box.
    camera.position.set(0, 0.4, 40);
    camera.lookAt(0, 0, 0);
  };

  // Renderizador WebGL transparente: dibuja la escena dentro de un <canvas>.
  const createRenderer = () => {
    renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    const { width, height } = safeSize();
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(width, height);
    renderer.setClearColor(0x000000, 0);
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.domElement.className = 'customizer-3d-canvas';
    container.appendChild(renderer.domElement);
  };

  // Iluminación premium de producto (tela, no videojuego):
  // hemisférica suave + luz principal + relleno violáceo + rim lavanda.
  const createLights = () => {
    const hemisphere = new THREE.HemisphereLight(0xcfc4e8, 0x0d0b13, 0.85);

    const keyLight = new THREE.DirectionalLight(0xffffff, 1.6);
    keyLight.position.set(2.5, 4, 4);

    const fillLight = new THREE.DirectionalLight(0x8b5cf6, 0.4);
    fillLight.position.set(-4, 0.5, 2.5);

    const rimLight = new THREE.DirectionalLight(0xc4b5fd, 0.55);
    rimLight.position.set(-1.5, 2, -4);

    scene.add(hemisphere, keyLight, fillLight, rimLight);
  };

  // Bucle de render único: gira suavemente hacia el lado elegido y actualiza
  // los controles (damping). Sin animaciones ni post-procesado extra.
  const renderLoop = () => {
    animationFrameId = requestAnimationFrame(renderLoop);
    if (shirtGroup) {
      // Interpolación corta hacia la rotación objetivo (frente/espalda).
      shirtGroup.rotation.y += (targetYaw - shirtGroup.rotation.y) * 0.12;
    }
    controls?.update();
    renderer?.render(scene, camera);
  };

  // Ajusta cámara y canvas cuando el panel cambia de tamaño.
  const handleResize = () => {
    if (!renderer || !camera) return;
    const { width, height } = safeSize();
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
    renderer.setSize(width, height);
  };

  // ------------------------------------------------------------------
  // CARGA DEL MODELO
  // ------------------------------------------------------------------

  // Centra el modelo en el origen recalculando su Box3 (sin escala fija).
  const centerModel = (object3d) => {
    const box = new THREE.Box3().setFromObject(object3d);
    if (box.isEmpty()) return box;
    const center = box.getCenter(new THREE.Vector3());
    object3d.position.sub(center); // centra exactamente sobre el origen
    return box;
  };

  // Encuadra la cámara según el Box3 real: la camiseta ocupa ~fillRatio de la
  // altura visible. Funciona aunque la escala original del GLB cambie.
  const fitCameraToModel = (size) => {
    const { width, height } = safeSize();
    const halfFov = THREE.MathUtils.degToRad(CONFIG.fieldOfView / 2);
    // Distancia necesaria para que size.y ocupe fillRatio de la altura visible.
    const distance = (size.y / CONFIG.fillRatio) / (2 * Math.tan(halfFov));
    // Margen horizontal si el panel es muy ancho y angosto.
    const minDistanceForWidth = (size.x / 2) / (Math.tan(halfFov) * camera.aspect) + size.z;
    const finalDistance = Math.max(distance, minDistanceForWidth);
    camera.position.set(0, size.y * 0.08, finalDistance);
    camera.near = Math.max(finalDistance / 100, 0.01);
    camera.far = finalDistance * 20;
    camera.updateProjectionMatrix();
    return finalDistance;
  };

  // Detecta de forma robusta el material principal de la tela: los materiales
  // MeshStandardMaterial usados por las mallas renderizables del modelo.
  const collectFabricMaterials = (object3d) => {
    const materials = new Map();
    let renderableMeshes = 0;
    object3d.traverse((child) => {
      if (!child.isMesh || !child.geometry) return;
      renderableMeshes += 1;
      (Array.isArray(child.material) ? child.material : [child.material]).forEach((material) => {
        if (material?.isMeshStandardMaterial) materials.set(material.uuid, material);
      });
    });
    return { materials: [...materials.values()], renderableMeshes };
  };

  // Quita la baseColorTexture horneada (el diseño/color de fábrica) y libera
  // su memoria, sin tocar los mapas PBR (normal, roughness, AO, specular).
  // Resultado: superficie lisa recoloreable vía material.color.
  const neutralizeBakedDesign = (materials) => {
    materials.forEach((material) => {
      if (!material.map) return;
      material.map.dispose();
      material.map = null;
      material.needsUpdate = true;
    });
  };

  // Éxito: prepara escena, cámara, controls y MUESTRA el visor 3D.
  const onModelLoaded = (gltf) => {
    const model = gltf.scene;
    if (!model) throw new Error('El GLB no contiene una escena utilizable.');

    const { materials, renderableMeshes } = collectFabricMaterials(model);
    if (!renderableMeshes) throw new Error('El GLB no tiene mallas renderizables.');

    // Asegura que el material reciba bien la luz y siga pareciendo tela.
    materials.forEach((material) => {
      material.metalness = Math.min(material.metalness ?? 0, 0.1);
    });

    // Neutraliza el diseño horneado del GLB: el material del modelo viene con
    // una baseColorTexture (el estampado/color de fábrica del asset original).
    // Se retira SOLO el mapa de color; se conservan normalMap, roughness/
    // metallicRoughness, occlusion y specular para que siga pareciendo tela.
    neutralizeBakedDesign(materials);
    fabricMaterials = materials;

    shirtGroup = new THREE.Group();
    shirtGroup.add(model);
    centerModel(model);
    shirtGroup.rotation.y = targetYaw; // frente por defecto
    scene.add(shirtGroup);

    const box = new THREE.Box3().setFromObject(shirtGroup);
    const size = box.getSize(new THREE.Vector3());
    const finalDistance = fitCameraToModel(size);

    createControls(finalDistance);

    // Aplica el color actual del estado 2D; si el 2D aún no publicó nada,
    // el estado inicial del visor es NEGRO (color por defecto del Custom Lab).
    applyColor(window.GymCultureCustomizer?.color ?? 'Negro');

    modelReady = true;
    show3D();
    console.info(`[GYM CULTURE] Remera 3D cargada: ${renderableMeshes} malla(s), ${materials.length} material(es) de tela.`);
  };

  // OrbitControls tipo configurador de producto: rotar + zoom con límites.
  // El zoom es continuo (dolly proporcional con damping bajo) y pinch táctil
  // funciona nativamente en móvil. La cámara SOLO se posiciona aquí y en
  // fitCameraToModel() al cargar: después se respeta el zoom del usuario.
  const createControls = (distance) => {
    controls = new OrbitControls(camera, renderer.domElement);
    controls.target.set(0, 0, 0);
    controls.enableDamping = CONFIG.controls.enableDamping;
    controls.dampingFactor = CONFIG.controls.dampingFactor;
    controls.enablePan = CONFIG.controls.enablePan;
    controls.minDistance = distance * CONFIG.controls.minDistanceFactor;
    controls.maxDistance = distance * CONFIG.controls.maxDistanceFactor;
    controls.minPolarAngle = CONFIG.controls.minPolarAngle;
    controls.maxPolarAngle = CONFIG.controls.maxPolarAngle;
    controls.zoomSpeed = CONFIG.controls.zoomSpeed;
    controls.rotateSpeed = CONFIG.controls.rotateSpeed;
    controls.zoomToCursor = false;
    controls.update();
  };

  // ------------------------------------------------------------------
  // INTEGRACIÓN CON EL CUSTOMIZER 2D
  // ------------------------------------------------------------------

  // Recolorea SOLO los materiales de tela detectados, conservando roughness,
  // normalMap, occlusion y demás propiedades PBR del GLB.
  const applyColor = (colorName) => {
    if (!modelReady || !colorName) return;
    const hex = COLOR_HEX[colorName];
    if (hex === undefined) {
      console.warn(`[GYM CULTURE 3D] Color desconocido para el visor 3D: "${colorName}". Se conserva el color actual.`);
      return;
    }
    fabricMaterials.forEach((material) => {
      material.color.setHex(hex);
    });
  };

  const loadModel = () => {
    new GLTFLoader().load(
      MODEL_URL,
      onModelLoaded,
      undefined,
      (error) => {
        console.error('[GYM CULTURE 3D] No se pudo cargar tshirt.glb. El Custom Lab continúa en modo 2D.', error);
      }
    );
  };

  // Muestra el 3D y oculta el 2D SOLO cuando todo ya funcionó.
  const show3D = () => {
    container.hidden = false;
    container.classList.add('is-ready');
    const stage = container.closest('.shirt-stage');
    stage?.classList.add('is-3d-active'); // CSS: oculta #shirt, no lo elimina
    handleResize();
  };

  const init = () => {
    if (isInitialized || !container) return;
    isInitialized = true;
    try {
      createScene();
      createCamera();
      createRenderer();
      createLights();

      resizeObserver = new ResizeObserver(handleResize);
      resizeObserver.observe(container);
      window.addEventListener('resize', handleResize);

      renderLoop();
      loadModel();
    } catch (error) {
      // Cualquier fallo de inicialización deja el 2D intacto.
      console.error('[GYM CULTURE 3D] Inicialización fallida. El Custom Lab continúa en modo 2D.', error);
      dispose();
    }
  };

  // Cleanup razonable: geometrías, materiales, texturas, renderer y listeners.
  const dispose = () => {
    if (animationFrameId) cancelAnimationFrame(animationFrameId);
    resizeObserver?.disconnect();
    window.removeEventListener('resize', handleResize);
    controls?.dispose();
    scene?.traverse((object) => {
      if (object.geometry) object.geometry.dispose();
      if (object.material) {
        (Array.isArray(object.material) ? object.material : [object.material]).forEach((material) => {
          Object.values(material).forEach((value) => {
            if (value?.isTexture) value.dispose();
          });
          material.dispose();
        });
      }
    });
    renderer?.dispose();
    renderer?.domElement?.remove();
    scene = camera = renderer = controls = shirtGroup = null;
    modelReady = false;
    isInitialized = false;
  };

  return {
    init,
    dispose,
    // Puente usado por customizer.js (script clásico). Ambos son no-op
    // seguros si el 3D no está listo: el 2D nunca depende de ellos.
    setColor: applyColor,
    setSide: (side) => {
      targetYaw = side === 'back' ? Math.PI : 0;
    },
    isReady: () => modelReady,
  };
})();

// Puente global (compatible con la FASE 1: init/dispose se conservan).
window.GymCulture3D = {
  init: Customizer3D.init,
  dispose: Customizer3D.dispose,
  setColor: Customizer3D.setColor,
  setSide: Customizer3D.setSide,
  isReady: Customizer3D.isReady,
};

// Como los módulos ES ya esperan al DOM, podemos inicializar directamente.
window.GymCulture3D.init();
