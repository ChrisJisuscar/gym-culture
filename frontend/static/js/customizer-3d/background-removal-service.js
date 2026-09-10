export class BackgroundRemovalService {
  async remove(source) {
    const input = await fetch(source);
    if (!input.ok) throw new Error('No se pudo leer la imagen seleccionada.');
    const form = new FormData();
    form.append('image', await input.blob(), 'design');
    const response = await fetch('/api/customizations/remove-background/', { method: 'POST', body: form });
    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.detail || 'No se pudo procesar la imagen. Intentá con otro archivo.');
    }
    const blob = await response.blob();
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve({ dataUrl: reader.result, mimeType: 'image/png', size: blob.size, name: 'design-transparent.png' });
      reader.onerror = () => reject(new Error('No se pudo leer la imagen procesada.'));
      reader.readAsDataURL(blob);
    });
  }
}
