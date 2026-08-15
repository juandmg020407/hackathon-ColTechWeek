// Plasma colormap and shared value scaling for the fertility surface.

const PLASMA = [
  [13, 8, 135], [65, 4, 157], [106, 0, 168], [143, 13, 164], [177, 42, 144],
  [204, 71, 120], [225, 100, 98], [242, 132, 75], [252, 166, 54], [252, 206, 37], [240, 249, 33],
];

export function plasma(t) {
  const clamped = Math.max(0, Math.min(1, t));
  const scaled = clamped * (PLASMA.length - 1);
  const index = Math.min(PLASMA.length - 2, Math.floor(scaled));
  const frac = scaled - index;
  const a = PLASMA[index];
  const b = PLASMA[index + 1];
  return [
    Math.round(a[0] + (b[0] - a[0]) * frac),
    Math.round(a[1] + (b[1] - a[1]) * frac),
    Math.round(a[2] + (b[2] - a[2]) * frac),
  ];
}

export function plasmaCss(t) {
  const [r, g, b] = plasma(t);
  return `rgb(${r},${g},${b})`;
}

export function plasmaGradient(steps = 12) {
  return Array.from({ length: steps }, (_, i) => plasmaCss(i / (steps - 1))).join(', ');
}
