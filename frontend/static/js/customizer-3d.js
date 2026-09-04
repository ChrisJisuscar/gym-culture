import * as THREE from '/static/vendor/three/three.module.min.js';
import { GLTFLoader } from '/static/vendor/three/loaders/GLTFLoader.js';
import { OrbitControls } from '/static/vendor/three/controls/OrbitControls.js';
import { DesignManager } from './customizer-3d/design-manager.js';
import { RaycastManager } from './customizer-3d/raycast-manager.js';

const container = document.querySelector('#customizer-3d-container');
const statusElement = document.querySelector('#viewer-status');

const Customizer3D = (() => {
  const MODEL_URL = '/static/models/tshirt.glb';
  const config = {
    fieldOfView: 40,
    fillRatio: 0.78,
    pixelRatioLimit: 2,
    controls: {
      minPolarAngle: Math.PI * 0.22,
      maxPolarAngle: Math.PI * 0.72,
      minDistanceFactor: 0.72,
      maxDistanceFactor: 2.3,
      dampingFactor: 0.065,
      rotateSpeed: 0.72,
      zoomSpeed: 0.55,
    },
  };

  let scene;
  let camera;
  let renderer;
  let controls;
  let garment;
  let garmentMaterials = [];
  let garmentMeshes = [];
  let garmentSize;
  let designManager;
  let raycastManager;
  let draggingDesign = false;
  let repositioningDesign = false;
  let captureDistance;
  let resizeObserver;
  let animationFrameId;
  let initialized = false;
  let currentColor = '#111015';

  const getViewport = () => ({
    width: Math.max(container?.clientWidth || 0, 1),
    height: Math.max(container?.clientHeight || 0, 1),
  });

  const setStatus = (message, isError = false) => {
    if (!statusElement) return;
    statusElement.textContent = message;
    statusElement.classList.toggle('is-error', isError);
    statusElement.hidden = !message;
  };

  const createScene = () => {
    scene = new THREE.Scene();
    const hemisphere = new THREE.HemisphereLight(0xe8e1f4, 0x15111d, 1.25);
    const key = new THREE.DirectionalLight(0xffffff, 1.8);
    key.position.set(3, 4, 5);
    const fill = new THREE.DirectionalLight(0x9f7aea, 0.55);
    fill.position.set(-4, 1, 3);
    const rim = new THREE.DirectionalLight(0xd8c7ff, 0.75);
    rim.position.set(-2, 3, -5);
    scene.add(hemisphere, key, fill, rim);
  };

  const createRenderer = () => {
    const { width, height } = getViewport();
    renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: 'high-performance' });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, config.pixelRatioLimit));
    renderer.setSize(width, height, false);
    renderer.setClearColor(0x000000, 0);
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.domElement.className = 'customizer-3d-canvas';
    container.appendChild(renderer.domElement);
  };

  const createCamera = () => {
    const { width, height } = getViewport();
    camera = new THREE.PerspectiveCamera(config.fieldOfView, width / height, 0.01, 1000);
  };

  const replaceLogoMaterials = (model) => {
    const materialsBySource = new Map();
    const sourceMaterials = new Map();
    let meshCount = 0;
    model.traverse((object) => {
      if (!object.isMesh || !object.geometry) return;
      meshCount += 1;
      garmentMeshes.push(object);
      const sources = Array.isArray(object.material) ? object.material : [object.material];
      const replacements = sources.map((source) => {
        if (!source?.isMaterial) throw new Error(`La malla ${object.name || '(sin nombre)'} no tiene un material válido.`);
        sourceMaterials.set(source.uuid, source);
        if (!materialsBySource.has(source.uuid)) {
          // RUN está horneado en color, normal y roughness; un material limpio
          // evita conservar relieve residual y mantiene el volumen geométrico.
          materialsBySource.set(source.uuid, new THREE.MeshStandardMaterial({
            name: `${source.name || 'garment'}_plain`,
            color: currentColor,
            metalness: 0,
            roughness: 0.88,
            side: source.side,
          }));
        }
        return materialsBySource.get(source.uuid);
      });
      object.material = Array.isArray(object.material) ? replacements : replacements[0];
    });
    if (!meshCount) throw new Error('El modelo no contiene mallas renderizables.');
    garmentMaterials = [...materialsBySource.values()];
    const sourceTextures = new Set();
    sourceMaterials.forEach((material) => {
      Object.values(material).forEach((value) => {
        if (value?.isTexture) sourceTextures.add(value);
      });
      material.dispose();
    });
    sourceTextures.forEach((texture) => texture.dispose());
  };

  const centerAndFrameGarment = () => {
    const box = new THREE.Box3().setFromObject(garment);
    if (box.isEmpty()) throw new Error('No se pudo calcular el volumen de la remera.');
    const center = box.getCenter(new THREE.Vector3());
    garment.position.sub(center);
    const centeredBox = new THREE.Box3().setFromObject(garment);
    const size = centeredBox.getSize(new THREE.Vector3());
    garmentSize = size.clone();
    const halfFov = THREE.MathUtils.degToRad(camera.fov / 2);
    const verticalDistance = size.y / (2 * config.fillRatio * Math.tan(halfFov));
    const horizontalDistance = size.x / (2 * config.fillRatio * Math.tan(halfFov) * camera.aspect);
    const distance = Math.max(verticalDistance, horizontalDistance) + size.z * 0.6;
    captureDistance = distance;

    camera.position.set(0, size.y * 0.04, distance);
    camera.near = Math.max(distance * 0.02, 0.01);
    camera.far = distance * 20;
    camera.updateProjectionMatrix();

    controls = new OrbitControls(camera, renderer.domElement);
    controls.target.set(0, 0, 0);
    controls.enableDamping = true;
    controls.dampingFactor = config.controls.dampingFactor;
    controls.enablePan = false;
    controls.minDistance = Math.max(distance * config.controls.minDistanceFactor, size.z * 1.2);
    controls.maxDistance = distance * config.controls.maxDistanceFactor;
    controls.minPolarAngle = config.controls.minPolarAngle;
    controls.maxPolarAngle = config.controls.maxPolarAngle;
    controls.rotateSpeed = config.controls.rotateSpeed;
    controls.zoomSpeed = config.controls.zoomSpeed;
    controls.zoomToCursor = false;
    controls.update();
  };

  const notifySelection = (design) => {
    document.dispatchEvent(new CustomEvent('gymculture:design-selection', { detail: design }));
  };

  const handlePointerDown = (event) => {
    if (!designManager || !controls) return;
    if (repositioningDesign) {
      const hit = raycastManager.garmentHit(event, garmentMeshes);
      if (!hit) return;
      try {
        designManager.moveSelected(hit);
        repositioningDesign = false;
        container.classList.remove('is-placing');
        setStatus('Elemento reubicado. Arrastralo para realizar ajustes.');
      } catch (error) {
        setStatus(error.message, true);
      }
      event.preventDefault();
      event.stopPropagation();
      return;
    }
    if (designManager.pending) {
      const hit = raycastManager.garmentHit(event, garmentMeshes);
      if (!hit) return;
      try {
        designManager.place(hit);
        container.classList.remove('is-placing');
        setStatus('Diseño colocado. Arrastralo para moverlo sobre la tela.');
      } catch (error) {
        setStatus(error.message, true);
      }
      event.preventDefault();
      event.stopPropagation();
      return;
    }
    const designHit = raycastManager.cast(event, designManager.meshes())[0];
    if (!designHit) {
      designManager.select(null);
      return;
    }
    designManager.select(designHit.object.userData.designId);
    draggingDesign = true;
    controls.enabled = false;
    renderer.domElement.setPointerCapture(event.pointerId);
    container.classList.add('is-dragging-design');
    event.preventDefault();
    event.stopPropagation();
  };

  const handlePointerMove = (event) => {
    if (!draggingDesign) return;
    event.stopPropagation();
    const hit = raycastManager.garmentHit(event, garmentMeshes);
    if (!hit) return;
    try {
      designManager.moveSelected(hit);
    } catch (error) {
      setStatus(error.message, true);
    }
  };

  const handlePointerUp = (event) => {
    if (!draggingDesign) return;
    draggingDesign = false;
    controls.enabled = true;
    container.classList.remove('is-dragging-design');
    if (renderer.domElement.hasPointerCapture(event.pointerId)) renderer.domElement.releasePointerCapture(event.pointerId);
  };

  const bindDesignInteraction = () => {
    raycastManager = new RaycastManager(camera, renderer.domElement);
    designManager = new DesignManager({
      scene,
      designs: window.GymCultureCustomizer.state.designs,
      garmentSize,
      onChange: notifySelection,
    });
    renderer.domElement.addEventListener('pointerdown', handlePointerDown, true);
    renderer.domElement.addEventListener('pointermove', handlePointerMove, true);
    renderer.domElement.addEventListener('pointerup', handlePointerUp, true);
    renderer.domElement.addEventListener('pointercancel', handlePointerUp, true);
  };

  const handleResize = () => {
    if (!renderer || !camera) return;
    const { width, height } = getViewport();
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, config.pixelRatioLimit));
    renderer.setSize(width, height, false);
  };

  const render = () => {
    animationFrameId = requestAnimationFrame(render);
    controls?.update();
    renderer?.render(scene, camera);
  };

  const onModelLoaded = (gltf) => {
    try {
      if (!gltf.scene) throw new Error('El GLB no contiene una escena utilizable.');
      garment = gltf.scene;
      replaceLogoMaterials(garment);
      scene.add(garment);
      centerAndFrameGarment();
      bindDesignInteraction();
      setStatus('');
      document.dispatchEvent(new CustomEvent('gymculture:3d-ready'));
    } catch (error) {
      setStatus('No se pudo preparar la remera 3D.', true);
      console.error('[GYM CULTURE 3D] Modelo inválido.', error);
    }
  };

  const setColor = (hexColor) => {
    if (!/^#[0-9a-f]{6}$/i.test(hexColor || '')) {
      console.error('[GYM CULTURE 3D] Color inválido.', hexColor);
      return;
    }
    currentColor = hexColor;
    garmentMaterials.forEach((material) => material.color.set(hexColor));
  };

  const prepareImage = async (file) => {
    if (!designManager) throw new Error('Esperá a que termine de cargar la remera.');
    await designManager.prepareImage(file);
    repositioningDesign = false;
    container.classList.add('is-placing');
    setStatus('Hacé clic o tocá la prenda para colocar tu diseño.');
  };

  const prepareText = (settings) => {
    if (!designManager) throw new Error('Esperá a que termine de cargar la remera.');
    designManager.prepareText(settings);
    repositioningDesign = false;
    container.classList.add('is-placing');
    setStatus('Hacé clic o tocá la prenda para colocar el texto.');
  };

  const updateSelectedDesign = (changes) => designManager?.updateSelected(changes);
  const removeSelectedDesign = () => {
    repositioningDesign = false;
    container.classList.remove('is-placing');
    designManager?.removeSelected();
    setStatus('');
  };
  const rearmSelectedDesign = () => {
    const selected = designManager?.selected();
    if (!selected) return;
    repositioningDesign = true;
    container.classList.add('is-placing');
    setStatus('Hacé clic o tocá otra zona de la prenda para reubicarlo.');
  };

  const getCustomizationState = () => JSON.parse(JSON.stringify({
    version: 1,
    garment: {
      type: window.GymCultureCustomizer?.state.garmentType,
      color: window.GymCultureCustomizer?.state.garmentColor,
      colorHex: window.GymCultureCustomizer?.state.garmentColorHex,
      size: window.GymCultureCustomizer?.state.size,
      variantId: window.GymCultureCustomizer?.state.selectedVariant?.id ?? null,
    },
    designs: window.GymCultureCustomizer?.state.designs || [],
  }));

  const canvasToBlob = (canvas) => new Promise((resolve, reject) => {
    canvas.toBlob((blob) => blob ? resolve(blob) : reject(new Error('No se pudo generar el preview.')), 'image/webp', 0.9);
  });

  const capturePreviews = async () => {
    if (!garment || !designManager) throw new Error('La remera todavía no está lista.');
    const previewRenderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
    previewRenderer.setPixelRatio(1);
    previewRenderer.setSize(1024, 1024, false);
    previewRenderer.outputColorSpace = THREE.SRGBColorSpace;
    previewRenderer.setClearColor(0x100d18, 1);
    const previewCamera = camera.clone();
    previewCamera.aspect = 1;
    previewCamera.updateProjectionMatrix();
    designManager.setSelectionHighlight(false);
    try {
      const capture = async (direction) => {
        previewCamera.position.set(0, garmentSize.y * 0.04, captureDistance * direction);
        previewCamera.lookAt(0, 0, 0);
        previewRenderer.render(scene, previewCamera);
        return canvasToBlob(previewRenderer.domElement);
      };
      return { front: await capture(1), back: await capture(-1) };
    } finally {
      designManager.setSelectionHighlight(true);
      previewRenderer.dispose();
    }
  };

  const loadCustomization = async (configuration) => {
    if (configuration?.version !== 1 || !configuration.garment || !Array.isArray(configuration.designs)) {
      throw new Error('La versión de la personalización no es compatible.');
    }
    const state = window.GymCultureCustomizer.state;
    Object.assign(state, {
      garmentType: configuration.garment.type,
      garmentColor: configuration.garment.color,
      garmentColorHex: configuration.garment.colorHex,
      size: configuration.garment.size,
    });
    state.designs.splice(0, state.designs.length, ...configuration.designs);
    setColor(state.garmentColorHex);
    await designManager.restoreAll(garmentMeshes[0]);
    document.dispatchEvent(new CustomEvent('gymculture:customization-loaded', { detail: configuration }));
  };

  const dispose = () => {
    if (animationFrameId) cancelAnimationFrame(animationFrameId);
    resizeObserver?.disconnect();
    window.removeEventListener('resize', handleResize);
    controls?.dispose();
    renderer?.domElement.removeEventListener('pointerdown', handlePointerDown, true);
    renderer?.domElement.removeEventListener('pointermove', handlePointerMove, true);
    renderer?.domElement.removeEventListener('pointerup', handlePointerUp, true);
    renderer?.domElement.removeEventListener('pointercancel', handlePointerUp, true);
    designManager?.dispose();
    garment?.traverse((object) => object.geometry?.dispose());
    garmentMaterials.forEach((material) => material.dispose());
    renderer?.dispose();
    renderer?.domElement.remove();
    initialized = false;
  };

  const init = () => {
    if (initialized || !container) return;
    initialized = true;
    try {
      currentColor = window.GymCultureCustomizer?.state?.garmentColorHex || currentColor;
      createScene();
      createCamera();
      createRenderer();
      resizeObserver = new ResizeObserver(handleResize);
      resizeObserver.observe(container);
      window.addEventListener('resize', handleResize, { passive: true });
      render();
      new GLTFLoader().load(MODEL_URL, onModelLoaded, undefined, (error) => {
        setStatus('No se pudo cargar la remera 3D. Intentá recargar la página.', true);
        console.error('[GYM CULTURE 3D] Falló la carga de tshirt.glb.', error);
      });
    } catch (error) {
      setStatus('Tu navegador no pudo iniciar el visor 3D.', true);
      console.error('[GYM CULTURE 3D] Falló la inicialización WebGL.', error);
      dispose();
    }
  };

  return {
    init, dispose, setColor, prepareImage, prepareText,
    updateSelectedDesign, removeSelectedDesign, rearmSelectedDesign,
    getCustomizationState, capturePreviews, loadCustomization,
    isReady: () => Boolean(designManager),
  };
})();

window.GymCulture3D = Customizer3D;
Customizer3D.init();
