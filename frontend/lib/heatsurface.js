// Paints the contract grid as a smooth plasma surface over a slippy basemap.

import { plasma } from './colormap.js';
import { RANGES } from './plotmap.js';

const METERS_PER_DEG_LAT = 110540;
const PADDING_M = 12;

export function gridGeoBounds(grid) {
  const [lat0, lon0] = grid.origen;
  const metersPerDegLon = 111320 * Math.cos((lat0 * Math.PI) / 180);
  const heightM = grid.rows * grid.celda_m;
  const widthM = grid.cols * grid.celda_m;
  return {
    south: lat0 - PADDING_M / METERS_PER_DEG_LAT,
    north: lat0 + (heightM + PADDING_M) / METERS_PER_DEG_LAT,
    west: lon0 - PADDING_M / metersPerDegLon,
    east: lon0 + (widthM + PADDING_M) / metersPerDegLon,
  };
}

export function cellCorners(grid) {
  const [lat0, lon0] = grid.origen;
  const metersPerDegLon = 111320 * Math.cos((lat0 * Math.PI) / 180);
  return {
    north: lat0 + (grid.rows * grid.celda_m) / METERS_PER_DEG_LAT,
    south: lat0,
    west: lon0,
    east: lon0 + (grid.cols * grid.celda_m) / metersPerDegLon,
  };
}

export function paintSurface(canvas, grid, nutrient, projector) {
  const values = grid[nutrient];
  const [min, max] = RANGES[nutrient];
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
    if (!grid.mask[index]) {
      image.data[offset + 3] = 0;
      continue;
    }
    const [r, g, b] = plasma((values[index] - min) / span);
    image.data[offset] = r;
    image.data[offset + 1] = g;
    image.data[offset + 2] = b;
    image.data[offset + 3] = 255;
  }
  sourceCtx.putImageData(image, 0, 0);

  const rect = canvas.getBoundingClientRect();
  const ratio = window.devicePixelRatio || 1;
  canvas.width = Math.round(rect.width * ratio);
  canvas.height = Math.round(rect.height * ratio);

  const corners = cellCorners(grid);
  const topLeft = projector.toPixel(corners.north, corners.west);
  const bottomRight = projector.toPixel(corners.south, corners.east);

  const ctx = canvas.getContext('2d');
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  ctx.clearRect(0, 0, rect.width, rect.height);
  ctx.imageSmoothingEnabled = true;
  ctx.imageSmoothingQuality = 'high';
  ctx.drawImage(source, topLeft.x, topLeft.y, bottomRight.x - topLeft.x, bottomRight.y - topLeft.y);
}

export function paintOverlay(svg, view, projector) {
  const { grid, contorno, puntos, nextSample } = view;
  const point = (lat, lon) => projector.toPixel(lat, lon);

  const outline = contorno?.length
    ? `<polygon points="${contorno.map(([lat, lon]) => { const p = point(lat, lon); return `${p.x.toFixed(1)},${p.y.toFixed(1)}`; }).join(' ')}"
        fill="none" stroke="#12212e" stroke-width="1.4" stroke-dasharray="6 4"/>`
    : '';

  const uncertain = [];
  const corners = cellCorners(grid);
  const cellW = (projector.toPixel(corners.north, corners.east).x - projector.toPixel(corners.north, corners.west).x) / grid.cols;
  const cellH = (projector.toPixel(corners.south, corners.west).y - projector.toPixel(corners.north, corners.west).y) / grid.rows;
  const gridTopLeft = projector.toPixel(corners.north, corners.west);

  for (let index = 0; index < grid.mask.length; index += 1) {
    if (!grid.mask[index] || grid.sigma[index] <= grid.sigma_umbral) continue;
    const col = index % grid.cols;
    const row = grid.rows - 1 - Math.floor(index / grid.cols);
    uncertain.push(`<rect x="${(gridTopLeft.x + col * cellW).toFixed(1)}" y="${(gridTopLeft.y + row * cellH).toFixed(1)}"
      width="${Math.ceil(cellW)}" height="${Math.ceil(cellH)}" fill="url(#nose)"/>`);
  }

  const dots = puntos.map((p) => {
    const c = point(p.lat, p.lon);
    return `<g><circle cx="${c.x.toFixed(1)}" cy="${c.y.toFixed(1)}" r="3" fill="#111" stroke="#fff" stroke-width="1.1"/>`
      + `<title>N ${p.N} · P ${p.P} · K ${p.K}${p.sospechoso ? ' · lectura rara' : ''}</title></g>`;
  }).join('');

  const cross = nextSample
    ? (() => {
      const c = point(nextSample.punto[0], nextSample.punto[1]);
      return `<g class="pulso">
          <circle cx="${c.x.toFixed(1)}" cy="${c.y.toFixed(1)}" r="13" fill="none" stroke="#12212e" stroke-width="2"/>
          <path d="M${(c.x - 18).toFixed(1)} ${c.y.toFixed(1)}h36 M${c.x.toFixed(1)} ${(c.y - 18).toFixed(1)}v36"
            stroke="#12212e" stroke-width="2"/>
        </g>`;
    })()
    : '';

  svg.innerHTML = `<defs>
      <pattern id="nose" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
        <line x1="0" y1="0" x2="0" y2="6" stroke="rgba(255,255,255,.85)" stroke-width="1.6"/>
      </pattern>
    </defs>${uncertain.join('')}${outline}${dots}${cross}`;
}
