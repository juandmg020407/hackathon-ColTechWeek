// Paints the lot grid full-bleed behind the entry screens.

import { plasma } from './colormap.js';
import { RANGES } from './plotmap.js';
import { getPackage } from './api.js';

const FALLBACK = 'linear-gradient(140deg,#0d0887,#8f0da4,#e16462,#fca636)';
const NUTRIENT = 'K';

export async function paintField(canvas) {
  let grid;
  try {
    ({ data: { grid } } = await getPackage());
  } catch {
    canvas.style.background = FALLBACK;
    return;
  }

  const values = grid[NUTRIENT];
  const [min, max] = RANGES[NUTRIENT];
  const span = max - min || 1;

  const source = document.createElement('canvas');
  source.width = grid.cols;
  source.height = grid.rows;
  const sourceCtx = source.getContext('2d');
  const image = sourceCtx.createImageData(grid.cols, grid.rows);

  for (let index = 0; index < values.length; index += 1) {
    const col = index % grid.cols;
    const row = grid.rows - 1 - Math.floor(index / grid.cols);
    const offset = (row * grid.cols + col) * 4;
    const [r, g, b] = plasma((values[index] - min) / span);
    image.data[offset] = r;
    image.data[offset + 1] = g;
    image.data[offset + 2] = b;
    image.data[offset + 3] = grid.mask[index] ? 255 : 90;
  }
  sourceCtx.putImageData(image, 0, 0);

  const paint = () => {
    if (canvas.clientWidth < 2) return;
    const ratio = window.devicePixelRatio || 1;
    canvas.width = Math.round(canvas.clientWidth * ratio);
    canvas.height = Math.round(canvas.clientHeight * ratio);
    const ctx = canvas.getContext('2d');
    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = 'high';
    const scale = Math.max(canvas.width / grid.cols, canvas.height / grid.rows);
    const width = grid.cols * scale;
    const height = grid.rows * scale;
    ctx.drawImage(source, (canvas.width - width) / 2, (canvas.height - height) / 2, width, height);
  };

  paint();
  window.addEventListener('resize', paint);
}
