import * as THREE from '/static/vendor/three/three.module.min.js';

const TEXTURE_HEIGHT = 512;
const HORIZONTAL_PADDING = 56;

export const TEXT_FONTS = ['Outfit', 'Arial', 'Impact', 'DM Mono'];

export function createTextTexture({ text, fontFamily, color }) {
  const canvas = document.createElement('canvas');
  const context = canvas.getContext('2d');
  if (!context) throw new Error('Canvas 2D no está disponible para generar texto.');
  const safeText = (text || 'GYM CULTURE').slice(0, 50);
  const font = fontFamily || TEXT_FONTS[0];
  const fontSize = 280;
  context.font = `800 ${fontSize}px "${font}"`;
  canvas.width = Math.min(2048, Math.max(512, Math.ceil(context.measureText(safeText).width + HORIZONTAL_PADDING * 2)));
  canvas.height = TEXTURE_HEIGHT;
  context.clearRect(0, 0, canvas.width, canvas.height);
  context.font = `800 ${fontSize}px "${font}"`;
  context.fillStyle = color || '#ffffff';
  context.textAlign = 'center';
  context.textBaseline = 'middle';
  context.fillText(safeText, canvas.width / 2, canvas.height / 2);
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.anisotropy = 4;
  texture.needsUpdate = true;
  return { texture, aspectRatio: canvas.width / canvas.height };
}
