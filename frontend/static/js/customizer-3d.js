import * as THREE from '/static/vendor/three/three.module.min.js';
import { GLTFLoader } from '/static/vendor/three/loaders/GLTFLoader.js';
import { OrbitControls } from '/static/vendor/three/controls/OrbitControls.js';
import { DesignManager } from './customizer-3d/design-manager.js';
import { RaycastManager } from './customizer-3d/raycast-manager.js';
import { GARMENTS, getGarment } from './customizer-3d/garments.js';
import { disposeModel, prepareGarment, getFrameDistance } from './customizer-3d/garment-model.js';
import { recommendationHit } from './customizer-3d/recommendation-placement.js';
import { changeLayer, syncLayers } from './customizer-3d/layer-manager.js';
import { transformSelection } from './customizer-3d/transform-tools.js';

const container = document.querySelector('#customizer-3d-container');
const statusElement = document.querySelector('#viewer-status');

const Customizer3D = (() => {
  const loader = new GLTFLoader();
  const config = {
    fieldOfView: 40,
    fillRatio: 0.78,
    pixelRatioLimit: 2,
    controls: {
      minPolarAngle: Math.PI * 0.22,
      maxPolarAngle: Math.PI * 0.72,
      minDistanceFactor: 0.22,
      surfaceClearanceFactor: 0.035,
      maxDistanceFactor: 2.3,
      dampingFactor: 0.065,
      rotateSpeed: 0.72,
      zoomSpeed: 0.55,
    },
  };

  let scene;
  let editorGroup;
  let preview = null;
  let previewHost = null;
  let previewMode = false;
  let previewVersion = 0;
  let editorCameraState = null;
  const frameSubscribers = new Set();
  let lastFrame = null;
  let camera;
  let renderer;
  let controls;
  let garment;
  let garmentMaterials = [];
  let garmentMeshes = [];
  let garmentSize;
  let garmentRadius;
  let designManager;
  let raycastManager;
  let draggingDesign = false;
  let repositioningDesign = false;
  let busy = false;
  let editLocked = false;
  let initialLoad;
  let lifecycle = 0;
  let resizeObserver;
  let animationFrameId;
  let initialized = false;
  let currentColor = '#111015';

  const getViewport = () => ({
    width: Math.max((previewMode ? previewHost : container)?.clientWidth || 0, 1),
    height: Math.max((previewMode ? previewHost : container)?.clientHeight || 0, 1),
  });

  const setStatus = (message, isError = false) => {
    if (!statusElement) return;
    statusElement.textContent = message;
    statusElement.classList.toggle('is-error', isError);
    statusElement.classList.toggle('is-hint', !!garment && !busy && !isError);
    statusElement.hidden = !message;
  };

  const createScene = () => {
    scene = new THREE.Scene();
    editorGroup = new THREE.Group();
    scene.add(editorGroup);
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
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, previewMode ? 1.5 : config.pixelRatioLimit));
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

  const setBusy = (value) => {
    busy = value;
    container.setAttribute('aria-busy', String(value));
    if (controls) controls.enabled = !value && !editLocked;
    document.dispatchEvent(new CustomEvent('gymculture:3d-busy', { detail: value }));
  };

  const frameGarment = () => {
    const size = previewMode ? preview?.size : garmentSize;
    if (!size) return;
    const distance = getFrameDistance(size, camera.fov, camera.aspect, config.fillRatio);
    // Flush OrbitControls damping before assigning the new framing.
    controls.enableDamping = false;
    controls.update();
    controls.target.set(0, 0, 0);
    camera.position.set(0, size.y * 0.04, distance);
    camera.near = Math.max(distance * 0.002, 0.0001);
    camera.far = distance * 20;
    camera.updateProjectionMatrix();
    const radius = previewMode ? preview?.radius : garmentRadius;
    // The camera stays outside every vertex, at every allowed viewing angle.
    controls.minDistance = Math.max(distance * config.controls.minDistanceFactor, radius + size.y * config.controls.surfaceClearanceFactor);
    controls.maxDistance = distance * config.controls.maxDistanceFactor;
    controls.update();
    controls.enableDamping = true;
  };

  const createControls = () => {
    controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = config.controls.dampingFactor;
    controls.enablePan = false;
    controls.minPolarAngle = config.controls.minPolarAngle;
    controls.maxPolarAngle = config.controls.maxPolarAngle;
    controls.rotateSpeed = config.controls.rotateSpeed;
    controls.zoomSpeed = config.controls.zoomSpeed;
    controls.zoomToCursor = false;
  };

  const resetDesigns = () => {
    designManager?.clearResources();
    draggingDesign = false;
    repositioningDesign = false;
    container.classList.remove('is-placing', 'is-dragging-design');
  };

  // Load first so a failed request leaves the current garment and designs intact.
  // This is the only place that replaces a model; the scene/renderer/controls survive.
  const replaceGarment = async (type) => {
    const definition = getGarment(type);
    if (!definition?.enabled) throw new Error('Esta prenda todavía no está disponible.');
    if (garment && window.GymCultureCustomizer.state.garmentType === type) return;
    const generation = lifecycle;
    setStatus(`Cargando ${definition.label.toLowerCase()} 3D…`);
    const gltf = await loader.loadAsync(definition.modelUrl);
    if (generation !== lifecycle || !initialized) {
      disposeModel(gltf.scene);
      throw new Error('El visor se cerró durante la carga.');
    }
    let prepared;
    try {
      if (!gltf.scene) throw new Error('El GLB no contiene una escena utilizable.');
      prepared = prepareGarment(gltf.scene, currentColor, definition);
    } catch (error) {
      disposeModel(gltf.scene);
      throw error;
    }
    resetDesigns();
    disposeModel(garment);
    garment = prepared.model;
    garmentMeshes = prepared.meshes;
    garmentMaterials = prepared.materials;
    garmentSize = prepared.size;
    garmentRadius = prepared.radius;
    editorGroup.add(garment);
    frameGarment();
    if (designManager) designManager.garmentSize = garmentSize;
    else bindDesignInteraction();
    window.GymCultureCustomizer.state.garmentType = type;
    applyHoodState(window.GymCultureCustomizer.state.hoodState || "down");
    container.setAttribute('aria-label', `${definition.label} 3D interactiva`);
    document.dispatchEvent(new CustomEvent('gymculture:garment-changed', { detail: type }));
    setStatus('');
  };

  const applyHoodState = (value) => {
    const state = window.GymCultureCustomizer.state;
    const definition = getGarment(state.garmentType);
    if (!definition.hoodMeshes || !['down', 'up'].includes(value)) return;
    state.hoodState = value;
    garmentMeshes.forEach((mesh) => {
      if (Object.values(definition.hoodMeshes).includes(mesh.name)) mesh.visible = mesh.name === definition.hoodMeshes[value];
    });
    if (designManager) syncLayers(designManager);
  };
  const setHoodState = (value) => { if (!busy) applyHoodState(value); };

  const setGarmentType = async (type) => {
    activateEditor();
    if (busy || !getGarment(type)?.enabled) return false;
    if (garment && type === window.GymCultureCustomizer.state.garmentType) return true;
    if ((designManager?.designs.length || designManager?.pending) &&
        !window.confirm('Cambiar de prenda eliminará los diseños actuales.')) return false;
    const generation = lifecycle;
    setBusy(true);
    try {
      await replaceGarment(type);
      return true;
    } catch (error) {
      if (generation === lifecycle) {
        setStatus('No se pudo cargar la prenda. Podés volver a intentarlo.', true);
        console.error('[GYM CULTURE 3D] Falló el cambio de prenda.', error);
      }
      return false;
    } finally {
      if (generation === lifecycle) {
        setBusy(false);
        handleResize();
      }
    }
  };

  const notifySelection = (design) => {
    document.dispatchEvent(new CustomEvent('gymculture:design-selection', { detail: design }));
  };

  const handlePointerDown = (event) => {
    if (previewMode || busy || editLocked || !designManager || !controls) return;
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
    if (busy || editLocked || !draggingDesign) return;
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
    if (busy || !draggingDesign) return;
    draggingDesign = false;
    controls.enabled = !editLocked;
    container.classList.remove('is-dragging-design');
    if (renderer.domElement.hasPointerCapture(event.pointerId)) renderer.domElement.releasePointerCapture(event.pointerId);
  };

  const bindDesignInteraction = () => {
    raycastManager = new RaycastManager(camera, renderer.domElement);
    designManager = new DesignManager({
      scene: editorGroup,
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
    if (busy || !renderer || !camera) return;
    const { width, height } = getViewport();
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, config.pixelRatioLimit));
    renderer.setSize(width, height, false);
    frameGarment();
  };

  const render = (time = 0) => {
    animationFrameId = requestAnimationFrame(render);
    // DOM autoplay needs real elapsed time. Clamping to 50 ms slows the orbit
    // on low-FPS devices; reset the clock on visibility changes instead.
    const delta = lastFrame === null ? 0 : Math.max(0, (time - lastFrame) / 1000);
    lastFrame = time;
    if (document.hidden) return;
    frameSubscribers.forEach(callback => callback(time, delta));
    const rect = renderer?.domElement.getBoundingClientRect();
    if (!busy && rect && rect.bottom > 0 && rect.top < innerHeight) {
      controls?.update();
      renderer?.render(scene, camera);
    }
  };

  const setColor = (hexColor) => {
    activateEditor();
    if (!/^#[0-9a-f]{6}$/i.test(hexColor || '')) {
      console.error('[GYM CULTURE 3D] Color inválido.', hexColor);
      return;
    }
    currentColor = hexColor;
    garmentMaterials.forEach((material) => material.color.set(hexColor));
  };

  const prepareImage = async (file) => {
    activateEditor();
    if (busy || !designManager) throw new Error('Esperá a que termine de cargar la prenda.');
    await designManager.prepareImage(file);
    repositioningDesign = false;
    container.classList.add('is-placing');
    setStatus('Hacé clic o tocá la prenda para colocar tu diseño.');
  };

  const prepareText = (settings) => {
    activateEditor();
    if (busy || !designManager) throw new Error('Esperá a que termine de cargar la prenda.');
    designManager.prepareText(settings);
    repositioningDesign = false;
    container.classList.add('is-placing');
    setStatus('Hacé clic o tocá la prenda para colocar el texto.');
  };

  const updateSelectedDesign = (changes) => { if (!busy) designManager?.updateSelected(changes); };
  const removeSelectedDesign = () => {
    if (busy) return;
    repositioningDesign = false;
    container.classList.remove('is-placing');
    designManager?.removeSelected();
    setStatus('');
  };
  const rearmSelectedDesign = () => {
    if (busy) return;
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
      ...(getGarment(window.GymCultureCustomizer?.state.garmentType)?.hoodMeshes ? { hoodState: window.GymCultureCustomizer.state.hoodState } : {}),
      color: window.GymCultureCustomizer?.state.garmentColor,
      colorHex: window.GymCultureCustomizer?.state.garmentColorHex,
      size: window.GymCultureCustomizer?.state.size,
      productId: window.GymCultureCustomizer?.state.productId,
      variantId: window.GymCultureCustomizer?.state.selectedVariant?.id ?? null,
    },
    designs: window.GymCultureCustomizer?.state.designs || [],
  }));

  const canvasToBlob = (canvas, quality = .9) => new Promise((resolve, reject) => {
    canvas.toBlob((blob) => blob ? resolve(blob) : reject(new Error('No se pudo generar el preview.')), 'image/webp', quality);
  });

  const capturePreviews = async ({ size = 1024, quality = .9 } = {}) => {
    activateEditor();
    if (designManager?.processing) throw new Error('Esperá a que termine de quitarse el fondo antes de guardar.');
    if (busy || !garment || !designManager) throw new Error('La prenda todavía no está lista.');
    setBusy(true);
    const generation = lifecycle;
    const pixelRatio = renderer.getPixelRatio();
    const clearColor = renderer.getClearColor(new THREE.Color());
    const clearAlpha = renderer.getClearAlpha();
    const previewCamera = camera.clone();
    previewCamera.aspect = 1;
    // Square previews must be framed independently of the on-screen aspect ratio.
    const distance = getFrameDistance(garmentSize, previewCamera.fov, 1, config.fillRatio);
    previewCamera.near = Math.max(distance * 0.002, 0.0001);
    previewCamera.far = distance * 20;
    previewCamera.updateProjectionMatrix();
    designManager.setSelectionHighlight(false);
    try {
      renderer.setPixelRatio(1);
      const resolution = Math.max(256, Math.min(1024, size));
      renderer.setSize(resolution, resolution, false);
      renderer.setClearColor(0x100d18, 1);
      const capture = async (direction) => {
        if (generation !== lifecycle) throw new Error('El visor se cerró durante el preview.');
        previewCamera.position.set(0, garmentSize.y * 0.04, distance * direction);
        previewCamera.lookAt(0, 0, 0);
        renderer.render(scene, previewCamera);
        // toBlob snapshots immediately, before the next animation frame.
        return canvasToBlob(renderer.domElement, quality);
      };
      return { front: await capture(1), back: await capture(-1) };
    } finally {
      if (generation === lifecycle) {
        designManager.setSelectionHighlight(true);
        renderer.setPixelRatio(pixelRatio);
        renderer.setClearColor(clearColor, clearAlpha);
        setBusy(false);
        const { width, height } = getViewport();
        renderer.setSize(width, height, false);
        camera.aspect = width / height;
        camera.updateProjectionMatrix();
        renderer.render(scene, camera);
      }
    }
  };

  const vectorData = (vector) => ({ x: vector.x, y: vector.y, z: vector.z });

  // The showroom and editor resolve the preset against the same garment geometry.
  const applyRecommendation = async ({ assetUrl, garmentType, position, rotation = 0, scale = 1, name, baseColor, baseColorHex }) => {
    if (!designManager) throw new Error('Esperá a que termine de cargar la prenda.');
    if (busy) throw new Error('Esperá a que termine la operación actual.');
    if (garmentType && garmentType !== window.GymCultureCustomizer.state.garmentType) {
      if (!getGarment(garmentType)?.enabled) throw new Error('Esta prenda todavía no está disponible.');
      if (busy) throw new Error('Esperá a que termine la operación actual.');
      const changed = await setGarmentType(garmentType);
      if (!changed) throw new Error('No se pudo cambiar la prenda para aplicar la recomendación.');
    }
    const generation = lifecycle;
    setBusy(true);
    try {
      const hit = recommendationHit(garmentMeshes, garmentSize, position);
      if (!hit) throw new Error('No pudimos encontrar una superficie en la prenda para colocar el diseño.');
      const design = await designManager.applyRemoteDesign({
        assetUrl,
        position: vectorData(hit.point),
        normal: vectorData(hit.normal),
        mesh: hit.mesh,
        rotation,
        scale,
        sourceName: name,
      });
      if (baseColor && baseColorHex) {
        Object.assign(window.GymCultureCustomizer.state, { garmentColor: baseColor, garmentColorHex: baseColorHex });
        setColor(baseColorHex);
      }
      frameGarment();
      if (position?.z < 0) { camera.position.z *= -1; controls.update(); }
      designManager.notify();
      container.classList.remove('is-placing', 'is-dragging-design');
      setStatus('Diseño recomendado aplicado. Arrastralo o ajustalo libremente.');
      document.dispatchEvent(new CustomEvent('gymculture:recommendation-applied', { detail: { assetUrl, garmentType } }));
      return design;
    } finally {
      if (generation === lifecycle) {
        setBusy(false);
        handleResize();
      }
    }
  };

  const loadCustomization = async (configuration, { strict = false } = {}) => {
    activateEditor();
    if (configuration?.version !== 1 || !getGarment(configuration.garment?.type)?.enabled || !Array.isArray(configuration.designs)) {
      throw new Error('La versión o prenda de la personalización no es compatible.');
    }
    if (busy || !garment) throw new Error('Esperá a que termine de cargar la prenda.');
    const generation = lifecycle;
    setBusy(true);
    try {
      await replaceGarment(configuration.garment.type);
      resetDesigns();
      const state = window.GymCultureCustomizer.state;
      Object.assign(state, {
        productId: configuration.garment.productId ?? state.productId,
        hoodState: configuration.garment.hoodState || "down",
        garmentColor: configuration.garment.color,
        garmentColorHex: configuration.garment.colorHex,
        size: configuration.garment.size,
      });
      state.designs.splice(0, state.designs.length, ...JSON.parse(JSON.stringify(configuration.designs)));
      setColor(state.garmentColorHex);
      const failedAssets = await designManager.restoreAll(garmentMeshes);
      if (strict && failedAssets.length) throw new Error('No se pudieron restaurar todas las capas. Volvé a intentar antes de guardar.');
      applyHoodState(state.hoodState);
      document.dispatchEvent(new CustomEvent('gymculture:customization-loaded', { detail: configuration }));
      setStatus(failedAssets.length ? `Se restauraron ${state.designs.length - failedAssets.length} de ${state.designs.length} diseños. Revisá los que no pudieron cargarse.` : '');
    } catch (error) {
      if (generation === lifecycle) setStatus('No se pudo restaurar la personalización.', true);
      throw error;
    } finally {
      if (generation === lifecycle) {
        setBusy(false);
        handleResize();
      }
    }
  };

  // The public preview borrows this canvas, scene, camera, controls and RAF.
  // The editor's group stays in memory (hidden), preserving pending uploads,
  // selection and every unsaved change. Only one group is rendered at a time.
  const activateEditor = () => {
    if (!previewMode || !renderer) return;
    previewMode = false;
    editorGroup.visible = true;
    if (preview) preview.group.visible = false;
    container.append(renderer.domElement);
    container.querySelector('.lab-snapshot')?.remove();
    previewHost?.classList.remove('has-live-viewer');
    handleResize();
    if (editorCameraState) {
      camera.position.copy(editorCameraState.position);
      controls.target.copy(editorCameraState.target);
      controls.enableDamping = false; controls.update(); controls.enableDamping = true;
    }
  };

  const activatePreview = (host = previewHost) => {
    if (!preview || busy || !renderer || !host) return false;
    previewHost = host;
    if (previewMode) return true;
    editorCameraState = { position: camera.position.clone(), target: controls.target.clone() };
    renderer.render(scene, camera);
    const snapshot = document.createElement('img');
    snapshot.className = 'lab-snapshot'; snapshot.alt = 'Tu personalización actual';
    snapshot.src = renderer.domElement.toDataURL('image/webp', .8);
    container.querySelector('.lab-snapshot')?.remove(); container.append(snapshot);
    previewMode = true;
    editorGroup.visible = false; preview.group.visible = true;
    host.append(renderer.domElement); host.classList.add('has-live-viewer');
    handleResize();
    return true;
  };

  const clearPreview = ({ invalidate = true } = {}) => {
    if (invalidate) previewVersion++;
    activateEditor();
    if (!preview) return;
    preview.manager.clearResources();
    disposeModel(preview.model);
    preview.group.removeFromParent();
    preview = null;
  };

  const configurePreview = async (item, host) => {
    const version = ++previewVersion;
    const configuration = item.customization_state;
    const type = configuration?.garment?.type || item.garment_type;
    const definition = getGarment(type);
    if (!definition) throw new Error('La recomendación tiene una prenda inválida.');
    if (!preview || preview.type !== type) {
      const gltf = await loader.loadAsync(definition.modelUrl);
      if (version !== previewVersion || !initialized) { disposeModel(gltf.scene); return false; }
      const prepared = prepareGarment(gltf.scene, configuration?.garment?.colorHex || item.base_color_hex, definition);
      clearPreview({ invalidate: false });
      const group = new THREE.Group(); group.visible = false; group.add(prepared.model); scene.add(group);
      preview = { ...prepared, group, type, manager: new DesignManager({ scene: group, designs: [], garmentSize: prepared.size }) };
    }
    previewHost = host;
    const current = preview;
    const hood = configuration?.garment?.hoodState || 'down';
    current.meshes.forEach(mesh => { if (definition.hoodMeshes && Object.values(definition.hoodMeshes).includes(mesh.name)) mesh.visible = mesh.name === definition.hoodMeshes[hood]; });
    current.materials.forEach(material => material.color.set(configuration?.garment?.colorHex || item.base_color_hex));
    current.manager.clearResources();
    if (configuration?.version === 1) {
      current.manager.designs.push(...JSON.parse(JSON.stringify(configuration.designs)));
      const failed = await current.manager.restoreAll(current.meshes);
      if (failed.length) throw new Error('No se pudieron cargar todos los elementos de la recomendación.');
    } else {
      const hit = recommendationHit(current.meshes, current.size, item.default_position);
      await current.manager.applyRemoteDesign({ assetUrl: item.design_asset_url, position: hit.point, normal: hit.normal, mesh: hit.mesh, scale: item.default_scale, rotation: item.default_rotation });
    }
    if (version !== previewVersion) return false;
    current.manager.setSelectionHighlight(false);
    if (previewMode) { current.group.visible = true; handleResize(); }
    return true;
  };

  const activateFromEditor = () => activateEditor();
  const resetFrameClock = () => { lastFrame = null; };
  document.addEventListener('visibilitychange', resetFrameClock);
  window.addEventListener('pageshow', resetFrameClock);
  document.querySelector('.customizer-layout')?.addEventListener('pointerdown', activateFromEditor, true);
  document.querySelector('.customizer-layout')?.addEventListener('focusin', activateFromEditor, true);

  const dispose = () => {
    document.removeEventListener('visibilitychange', resetFrameClock);
    window.removeEventListener('pageshow', resetFrameClock);
    previewVersion++;
    clearPreview();
    frameSubscribers.clear();
    document.querySelector('.customizer-layout')?.removeEventListener('pointerdown', activateFromEditor, true);
    document.querySelector('.customizer-layout')?.removeEventListener('focusin', activateFromEditor, true);
    lifecycle += 1;
    if (animationFrameId) cancelAnimationFrame(animationFrameId);
    resizeObserver?.disconnect();
    window.removeEventListener('resize', handleResize);
    controls?.dispose();
    renderer?.domElement.removeEventListener('pointerdown', handlePointerDown, true);
    renderer?.domElement.removeEventListener('pointermove', handlePointerMove, true);
    renderer?.domElement.removeEventListener('pointerup', handlePointerUp, true);
    renderer?.domElement.removeEventListener('pointercancel', handlePointerUp, true);
    designManager?.dispose();
    disposeModel(garment);
    garment = null;
    garmentMeshes = [];
    garmentMaterials = [];
    garmentSize = null;
    designManager = null;
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
      createControls();
      resizeObserver = new ResizeObserver(handleResize);
      resizeObserver.observe(container);
      window.addEventListener('resize', handleResize, { passive: true });
      render();
      setBusy(true);
      const generation = lifecycle;
      initialLoad = replaceGarment(window.GymCultureCustomizer.state.garmentType)
        .catch((error) => {
          if (generation === lifecycle) {
            setStatus('No se pudo cargar la prenda 3D. Elegí una prenda para reintentar.', true);
            console.error('[GYM CULTURE 3D] Falló la carga inicial.', error);
          }
        })
        .finally(() => {
          if (generation === lifecycle) {
            setBusy(false);
            handleResize();
            if (garment) document.dispatchEvent(new CustomEvent('gymculture:3d-ready'));
          }
        });
    } catch (error) {
      setStatus('Tu navegador no pudo iniciar el visor 3D.', true);
      console.error('[GYM CULTURE 3D] Falló la inicialización WebGL.', error);
      dispose();
    }
  };

  return {
    init, dispose, setColor, prepareImage, prepareText,
    getSelectedDesign: () => designManager?.selected(),
    getLayers: () => designManager?.designs.map(design => ({ id: design.id, type: design.type, label: design.text || design.source?.name || 'Imagen', visibility: design.visibility !== false, layerOrder: design.layerOrder })) || [],
    selectDesign: id => { activateEditor(); if (!busy && !editLocked) designManager?.select(id); },
    transformSelected: action => { activateEditor(); if (!busy && !editLocked && !designManager?.processing) return transformSelection(designManager, garmentMeshes, action); },
    changeLayer: (id, action) => { activateEditor(); if (!busy && !editLocked && !designManager?.processing) changeLayer(designManager, id, action); },
    canEdit: () => Boolean(garment && designManager && !busy && !editLocked && !designManager.processing),
    setEditLock: value => { editLocked = value; if (controls) controls.enabled = !value && !busy; },
    updateSelectedDesign, removeSelectedDesign, rearmSelectedDesign,
    removeBackground: () => designManager?.removeBackground(),
    applyBackgroundRemoval: () => designManager?.applyBackgroundRemoval(),
    cancelBackgroundRemoval: () => designManager?.cancelBackgroundRemoval(),
    restoreOriginal: () => designManager?.restoreOriginal(),
    getCustomizationState, capturePreviews, loadCustomization, setGarmentType, setHoodState,
    applyDesignAsset: applyRecommendation,
    configurePreview, activatePreview, activateEditor, clearPreview,
    subscribeFrame: (callback) => { frameSubscribers.add(callback); return () => frameSubscribers.delete(callback); },
    isPreviewActive: () => previewMode,
    garments: GARMENTS,
    whenReady: () => initialLoad,
    isReady: () => Boolean(garment && designManager && !busy),
  };
})();

window.GymCulture3D = Customizer3D;
document.addEventListener('gymculture:editor-saving', event => Customizer3D.setEditLock(event.detail));
Customizer3D.init();
