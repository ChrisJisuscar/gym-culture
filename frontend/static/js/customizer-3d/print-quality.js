export function estimatePrintQuality(design, garmentType, profile) {
  const garment = profile?.garments[garmentType];
  if (design?.type !== 'image' || !garment || !design.imageWidth || !design.imageHeight) return null;
  const factor = garment.heightCm / garment.modelHeight;
  const widthCm = design.width * design.scale * factor, heightCm = design.height * design.scale * factor;
  const dpi = Math.min(design.imageWidth / (widthCm / 2.54), design.imageHeight / (heightCm / 2.54));
  return { level: dpi >= profile.highDpi ? 'high' : dpi >= profile.mediumDpi ? 'medium' : 'low', dpi: Math.round(dpi), widthCm: Math.round(widthCm * 10) / 10, heightCm: Math.round(heightCm * 10) / 10, estimated: true };
}
