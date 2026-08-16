// Renders the lot grid as local SVG: no tiles, single-hue sequential scale.

export const NUTRIENTS = ['N', 'P', 'K'];

// Elemental mass percent, covering the observed span of readings and grid means.
export const UNIT_LABEL = '%';

export const RANGES = {
  N: [0, 28],
  P: [0, 10],
  K: [0, 14],
};

export function color(value, [min, max]) {
  const t = Math.max(0, Math.min(1, (value - min) / (max - min)));
  const lightness = 94 - t * 56;
  const saturation = 22 + t * 42;
  return `hsl(96 ${saturation}% ${lightness}%)`;
}

export function renderMap({ grid, nutrient, nextSample, contour, points, origin }) {
  const values = grid[nutrient];
  const range = RANGES[nutrient];
  const flipRow = (index) => grid.rows - 1 - Math.floor(index / grid.cols);

  const cells = values.map((value, index) => {
    if (!grid.mask[index]) return '';
    const col = index % grid.cols;
    const row = flipRow(index);
    const uncertain = grid.sigma[index] > grid.sigma_umbral;
    const fill = uncertain ? 'url(#nose)' : color(value, range);
    return `<rect x="${col}" y="${row}" width="1" height="1" fill="${fill}"/>`;
  }).join('');

  const metersPerDegLon = 111320 * Math.cos((grid.origen[0] * Math.PI) / 180);
  const toCell = (lat, lon) => ({
    x: ((lon - grid.origen[1]) * metersPerDegLon) / grid.celda_m,
    y: grid.rows - ((lat - grid.origen[0]) * 110540) / grid.celda_m,
  });

  const outline = contour?.length
    ? `<polygon points="${contour.map(([lat, lon]) => { const p = toCell(lat, lon); return `${p.x.toFixed(2)},${p.y.toFixed(2)}`; }).join(' ')}"
        fill="none" stroke="#1b1d1a" stroke-width="0.18" stroke-linejoin="round" opacity="0.55"/>`
    : '';

  const dots = points?.length
    ? points.map((p) => {
      const c = toCell(p.lat, p.lon);
      return `<circle cx="${c.x.toFixed(2)}" cy="${c.y.toFixed(2)}" r="0.3" fill="#1b1d1a" opacity="${p.sospechoso ? 0.45 : 0.8}">`
        + `<title>N ${p.N} % · P ${p.P} % · K ${p.K} %${p.sospechoso ? ' · lectura rara' : ''}</title></circle>`;
    }).join('')
    : '';

  const cross = nextSample?.celda
    ? `<g class="pulso">
        <circle cx="${nextSample.celda.c + 0.5}" cy="${grid.rows - 0.5 - nextSample.celda.r}" r="1.6"
          fill="none" stroke="#1b1d1a" stroke-width="0.35"/>
        <path d="M${nextSample.celda.c - 0.3} ${grid.rows - 0.5 - nextSample.celda.r}h1.6
                 M${nextSample.celda.c + 0.5} ${grid.rows - 1.3 - nextSample.celda.r}v1.6"
          stroke="#1b1d1a" stroke-width="0.35"/>
      </g>`
    : '';

  return `<svg class="plot" viewBox="0 0 ${grid.cols} ${grid.rows}" shape-rendering="crispEdges"
      role="img" aria-label="Mapa de ${nutrient} del lote ${origin ?? ''}" preserveAspectRatio="xMidYMid meet">
    <defs>
      <pattern id="nose" width="2" height="2" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
        <rect width="2" height="2" fill="hsl(96 8% 88%)"/>
        <line x1="0" y1="0" x2="0" y2="2" stroke="hsl(96 10% 62%)" stroke-width="0.7"/>
      </pattern>
    </defs>
    ${cells}${outline}${dots}${cross}
  </svg>`;
}

export function legend(nutrient) {
  const range = RANGES[nutrient];
  const steps = Array.from({ length: 5 }, (_, i) => color(range[0] + ((range[1] - range[0]) * i) / 4, range));
  return `<div class="scale">
    <span>poco</span>
    ${steps.map((c) => `<i style="background:${c}"></i>`).join('')}
    <span>mucho</span>
    <i class="nose-key" title="El modelo no tiene certeza aquí"></i><span>no sé</span>
  </div>`;
}
