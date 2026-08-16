// Codificador QR propio. El contrato prohíbe hosts externos, así que no se
// puede traer una librería por CDN y el proyecto no tiene empaquetador: el
// código de corrección va aquí, en modo byte, versiones 1 a 10.
//
// Diez versiones alcanzan de sobra: lo que se codifica es la URL del acta en
// el mismo origen, unos sesenta caracteres, y la versión 10 admite 213 bytes
// con corrección M.

const MODE_BYTE = 4;
const TOTAL_CODEWORDS = [26, 44, 70, 100, 134, 172, 196, 242, 292, 346];

// Por versión: [correctores por bloque, bloques grupo 1, datos grupo 1,
// bloques grupo 2, datos grupo 2].
const BLOCKS = {
  L: [
    [7, 1, 19, 0, 0], [10, 1, 34, 0, 0], [15, 1, 55, 0, 0], [20, 1, 80, 0, 0],
    [26, 1, 108, 0, 0], [18, 2, 68, 0, 0], [20, 2, 78, 0, 0], [24, 2, 97, 0, 0],
    [30, 2, 116, 0, 0], [18, 2, 68, 2, 69],
  ],
  M: [
    [10, 1, 16, 0, 0], [16, 1, 28, 0, 0], [26, 1, 44, 0, 0], [18, 2, 32, 0, 0],
    [24, 2, 43, 0, 0], [16, 4, 27, 0, 0], [18, 4, 31, 0, 0], [22, 2, 38, 2, 39],
    [22, 3, 36, 2, 37], [26, 4, 43, 1, 44],
  ],
  Q: [
    [13, 1, 13, 0, 0], [22, 1, 22, 0, 0], [18, 2, 17, 0, 0], [26, 2, 24, 0, 0],
    [18, 2, 15, 2, 16], [24, 4, 19, 0, 0], [18, 2, 14, 4, 15], [22, 4, 18, 2, 19],
    [20, 4, 16, 4, 17], [24, 6, 19, 2, 20],
  ],
  H: [
    [17, 1, 9, 0, 0], [28, 1, 16, 0, 0], [22, 2, 13, 0, 0], [16, 4, 9, 0, 0],
    [22, 2, 11, 2, 12], [28, 4, 15, 0, 0], [26, 4, 13, 1, 14], [26, 4, 14, 2, 15],
    [24, 4, 12, 4, 13], [28, 6, 15, 2, 16],
  ],
};

const ALIGNMENT = [
  [], [6, 18], [6, 22], [6, 26], [6, 30],
  [6, 34], [6, 22, 38], [6, 24, 42], [6, 26, 46], [6, 28, 50],
];

// Los dos bits que la especificación asigna a cada nivel, que no siguen el
// orden de robustez: M es 00 y L es 01.
const ECC_BITS = { L: 1, M: 0, Q: 3, H: 2 };

// Aritmética en GF(256) con el primitivo 0x11d de la especificación.
const EXP = new Uint8Array(512);
const LOG = new Uint8Array(256);
for (let i = 0, x = 1; i < 255; i += 1) {
  EXP[i] = x;
  LOG[x] = i;
  x <<= 1;
  if (x & 0x100) x ^= 0x11d;
}
for (let i = 255; i < 512; i += 1) EXP[i] = EXP[i - 255];

const mul = (a, b) => (a === 0 || b === 0 ? 0 : EXP[LOG[a] + LOG[b]]);

function generatorPoly(degree) {
  let poly = [1];
  for (let i = 0; i < degree; i += 1) {
    // poly · (x + α^i): el primer término sube un grado, el segundo escala.
    const next = new Array(poly.length + 1).fill(0);
    for (let j = 0; j < poly.length; j += 1) {
      next[j] ^= poly[j];
      next[j + 1] ^= mul(poly[j], EXP[i]);
    }
    poly = next;
  }
  return poly;
}

function eccFor(data, count) {
  const gen = generatorPoly(count);
  const remainder = new Array(count).fill(0);
  for (const byte of data) {
    const factor = byte ^ remainder[0];
    remainder.shift();
    remainder.push(0);
    if (factor !== 0) {
      for (let i = 0; i < count; i += 1) remainder[i] ^= mul(gen[i + 1], factor);
    }
  }
  return remainder;
}

// Los cinco bits de formato (nivel + máscara) llevan BCH(15,5) y se cierran
// con el patrón fijo 0x5412 para que un símbolo en blanco no valide.
function formatBits(level, mask) {
  const data = (ECC_BITS[level] << 3) | mask;
  let rest = data << 10;
  for (let i = 4; i >= 0; i -= 1) {
    if (rest & (1 << (i + 10))) rest ^= 0x537 << i;
  }
  return ((data << 10) | rest) ^ 0x5412;
}

// A partir de la versión 7 el símbolo repite su número en dos bloques de 18
// bits con BCH(18,6).
function versionBits(version) {
  let rest = version << 12;
  for (let i = 5; i >= 0; i -= 1) {
    if (rest & (1 << (i + 12))) rest ^= 0x1f25 << i;
  }
  return (version << 12) | rest;
}

const MASKS = [
  (r, c) => (r + c) % 2 === 0,
  (r) => r % 2 === 0,
  (r, c) => c % 3 === 0,
  (r, c) => (r + c) % 3 === 0,
  (r, c) => (Math.floor(r / 2) + Math.floor(c / 3)) % 2 === 0,
  (r, c) => ((r * c) % 2) + ((r * c) % 3) === 0,
  (r, c) => (((r * c) % 2) + ((r * c) % 3)) % 2 === 0,
  (r, c) => (((r + c) % 2) + ((r * c) % 3)) % 2 === 0,
];

function utf8Bytes(text) {
  return Array.from(new TextEncoder().encode(text));
}

function pickVersion(byteLength, level) {
  for (let version = 1; version <= 10; version += 1) {
    const [ecc, b1, d1, b2, d2] = BLOCKS[level][version - 1];
    const capacity = b1 * d1 + b2 * d2;
    // Cabecera: 4 bits de modo más 8 o 16 de longitud según la versión.
    const header = 4 + (version < 10 ? 8 : 16);
    if (Math.ceil((header + byteLength * 8) / 8) <= capacity) {
      return { version, ecc, b1, d1, b2, d2, capacity };
    }
  }
  throw new Error('El texto no cabe en un QR de versión 10.');
}

function encodeData(bytes, spec) {
  const bits = [];
  const push = (value, length) => {
    for (let i = length - 1; i >= 0; i -= 1) bits.push((value >> i) & 1);
  };

  push(MODE_BYTE, 4);
  push(bytes.length, spec.version < 10 ? 8 : 16);
  for (const byte of bytes) push(byte, 8);

  // Terminador de hasta cuatro ceros, relleno hasta byte y luego el par
  // alterno 0xEC/0x11 que exige la especificación.
  const capacityBits = spec.capacity * 8;
  for (let i = 0; i < 4 && bits.length < capacityBits; i += 1) bits.push(0);
  while (bits.length % 8 !== 0) bits.push(0);

  const codewords = [];
  for (let i = 0; i < bits.length; i += 8) {
    codewords.push(bits.slice(i, i + 8).reduce((acc, bit) => (acc << 1) | bit, 0));
  }
  // El relleno siempre arranca en 0xEC y alterna desde ahí, sin importar en
  // qué posición hayan terminado los datos.
  const PAD = [0xec, 0x11];
  for (let i = 0; codewords.length < spec.capacity; i += 1) codewords.push(PAD[i % 2]);
  return codewords;
}

// Los bloques no van uno tras otro: se intercalan codeword a codeword, primero
// los de datos y después los de corrección.
function interleave(codewords, spec) {
  const blocks = [];
  let offset = 0;
  for (let i = 0; i < spec.b1; i += 1) {
    blocks.push(codewords.slice(offset, offset + spec.d1));
    offset += spec.d1;
  }
  for (let i = 0; i < spec.b2; i += 1) {
    blocks.push(codewords.slice(offset, offset + spec.d2));
    offset += spec.d2;
  }
  const eccBlocks = blocks.map((block) => eccFor(block, spec.ecc));

  const out = [];
  const longest = Math.max(...blocks.map((b) => b.length));
  for (let i = 0; i < longest; i += 1) {
    for (const block of blocks) if (i < block.length) out.push(block[i]);
  }
  for (let i = 0; i < spec.ecc; i += 1) {
    for (const block of eccBlocks) out.push(block[i]);
  }
  return out;
}

function emptyMatrix(size) {
  return {
    modules: Array.from({ length: size }, () => new Array(size).fill(0)),
    reserved: Array.from({ length: size }, () => new Array(size).fill(false)),
    size,
  };
}

function placeFinder(m, row, col) {
  for (let r = -1; r <= 7; r += 1) {
    for (let c = -1; c <= 7; c += 1) {
      const rr = row + r;
      const cc = col + c;
      if (rr < 0 || cc < 0 || rr >= m.size || cc >= m.size) continue;
      const ring = r >= 0 && r <= 6 && c >= 0 && c <= 6
        && (r === 0 || r === 6 || c === 0 || c === 6
          || (r >= 2 && r <= 4 && c >= 2 && c <= 4));
      m.modules[rr][cc] = ring ? 1 : 0;
      m.reserved[rr][cc] = true;
    }
  }
}

function placeFunctionPatterns(m, version) {
  placeFinder(m, 0, 0);
  placeFinder(m, 0, m.size - 7);
  placeFinder(m, m.size - 7, 0);

  for (let i = 8; i < m.size - 8; i += 1) {
    const bit = i % 2 === 0 ? 1 : 0;
    m.modules[6][i] = bit;
    m.reserved[6][i] = true;
    m.modules[i][6] = bit;
    m.reserved[i][6] = true;
  }

  const centers = ALIGNMENT[version - 1];
  const last = centers.length - 1;
  for (let i = 0; i <= last; i += 1) {
    for (let j = 0; j <= last; j += 1) {
      // Se omiten sólo las tres esquinas que ya ocupa un localizador. Los
      // demás sí van, incluidos los que caen sobre la línea de temporización.
      if ((i === 0 && j === 0) || (i === 0 && j === last) || (i === last && j === 0)) continue;
      const row = centers[i];
      const col = centers[j];
      for (let r = -2; r <= 2; r += 1) {
        for (let c = -2; c <= 2; c += 1) {
          const solid = Math.max(Math.abs(r), Math.abs(c)) !== 1;
          m.modules[row + r][col + c] = solid ? 1 : 0;
          m.reserved[row + r][col + c] = true;
        }
      }
    }
  }

  // Módulo oscuro fijo y las casillas que después ocupará el formato.
  m.modules[m.size - 8][8] = 1;
  m.reserved[m.size - 8][8] = true;
  for (let i = 0; i < 9; i += 1) {
    if (!m.reserved[8][i]) { m.modules[8][i] = 0; m.reserved[8][i] = true; }
    if (!m.reserved[i][8]) { m.modules[i][8] = 0; m.reserved[i][8] = true; }
  }
  for (let i = 0; i < 8; i += 1) {
    m.reserved[8][m.size - 1 - i] = true;
    m.reserved[m.size - 1 - i][8] = true;
  }

  if (version >= 7) {
    for (let i = 0; i < 18; i += 1) {
      const r = Math.floor(i / 3);
      const c = i % 3;
      m.reserved[m.size - 11 + c][r] = true;
      m.reserved[r][m.size - 11 + c] = true;
    }
  }
}

// Recorrido en zigzag de dos columnas, de abajo hacia arriba, saltando la
// columna de temporización.
function placeData(m, codewords) {
  let bitIndex = 0;
  const nextBit = () => {
    if (bitIndex >= codewords.length * 8) return 0;
    const bit = (codewords[bitIndex >> 3] >> (7 - (bitIndex & 7))) & 1;
    bitIndex += 1;
    return bit;
  };

  let upward = true;
  for (let right = m.size - 1; right > 0; right -= 2) {
    if (right === 6) right -= 1;
    for (let step = 0; step < m.size; step += 1) {
      const row = upward ? m.size - 1 - step : step;
      for (let c = 0; c < 2; c += 1) {
        const col = right - c;
        if (m.reserved[row][col]) continue;
        m.modules[row][col] = nextBit();
      }
    }
    upward = !upward;
  }
}

function applyFormat(m, level, mask, version) {
  const bits = formatBits(level, mask);
  for (let i = 0; i < 15; i += 1) {
    const bit = (bits >> i) & 1;
    // Primera copia, en escuadra alrededor del localizador superior izquierdo:
    // los bits bajos bajan por la columna 8 y los altos vuelven por la fila 8.
    if (i < 6) m.modules[i][8] = bit;
    else if (i === 6) m.modules[7][8] = bit;
    else if (i === 7) m.modules[8][8] = bit;
    else if (i === 8) m.modules[8][7] = bit;
    else m.modules[8][14 - i] = bit;
    // Segunda copia: los ocho bits bajos por la fila 8 desde el borde derecho,
    // el resto por la columna 8 desde abajo. El módulo oscuro de la fila
    // size-8 se repone al final porque esta copia no lo toca.
    if (i < 8) m.modules[8][m.size - 1 - i] = bit;
    else m.modules[m.size - 15 + i][8] = bit;
  }
  m.modules[m.size - 8][8] = 1;

  if (version < 7) return;
  const vbits = versionBits(version);
  for (let i = 0; i < 18; i += 1) {
    const bit = (vbits >> i) & 1;
    const r = Math.floor(i / 3);
    const c = i % 3;
    m.modules[m.size - 11 + c][r] = bit;
    m.modules[r][m.size - 11 + c] = bit;
  }
}

function penalty(modules, size) {
  let score = 0;

  const runScore = (line) => {
    let total = 0;
    let run = 1;
    for (let i = 1; i < size; i += 1) {
      if (line[i] === line[i - 1]) {
        run += 1;
      } else {
        if (run >= 5) total += 3 + (run - 5);
        run = 1;
      }
    }
    if (run >= 5) total += 3 + (run - 5);
    return total;
  };

  for (let i = 0; i < size; i += 1) {
    score += runScore(modules[i]);
    score += runScore(modules.map((row) => row[i]));
  }

  for (let r = 0; r < size - 1; r += 1) {
    for (let c = 0; c < size - 1; c += 1) {
      const v = modules[r][c];
      if (v === modules[r][c + 1] && v === modules[r + 1][c] && v === modules[r + 1][c + 1]) {
        score += 3;
      }
    }
  }

  // El patrón 1:1:3:1:1 con cuatro claros a un lado se confunde con un
  // localizador, y cada aparición cuesta 40.
  const FINDER = [1, 0, 1, 1, 1, 0, 1];
  const matches = (line, at) => {
    for (let i = 0; i < 7; i += 1) if (line[at + i] !== FINDER[i]) return false;
    const before = line.slice(Math.max(0, at - 4), at);
    const after = line.slice(at + 7, at + 11);
    const clear = (part) => part.length === 4 && part.every((v) => v === 0);
    return clear(before) || clear(after);
  };
  for (let i = 0; i < size; i += 1) {
    const row = modules[i];
    const col = modules.map((r) => r[i]);
    for (let at = 0; at + 7 <= size; at += 1) {
      if (matches(row, at)) score += 40;
      if (matches(col, at)) score += 40;
    }
  }

  let dark = 0;
  for (const row of modules) for (const v of row) dark += v;
  const ratio = (dark * 100) / (size * size);
  score += Math.floor(Math.abs(ratio - 50) / 5) * 10;
  return score;
}

/**
 * Devuelve la matriz de módulos del QR: `true` es un módulo oscuro.
 * El nivel por defecto es Q porque el código se lee de una pantalla, donde
 * el reflejo y el brillo se comen parte del contraste.
 */
export function qrMatrix(text, level = 'Q') {
  const bytes = utf8Bytes(text);
  const spec = pickVersion(bytes.length, level);
  const codewords = interleave(encodeData(bytes, spec), spec);
  const size = spec.version * 4 + 17;

  let best = null;
  for (let mask = 0; mask < 8; mask += 1) {
    const m = emptyMatrix(size);
    placeFunctionPatterns(m, spec.version);
    placeData(m, codewords);
    for (let r = 0; r < size; r += 1) {
      for (let c = 0; c < size; c += 1) {
        if (!m.reserved[r][c] && MASKS[mask](r, c)) m.modules[r][c] ^= 1;
      }
    }
    applyFormat(m, level, mask, spec.version);
    const score = penalty(m.modules, size);
    if (!best || score < best.score) best = { score, mask, modules: m.modules };
  }

  return {
    size,
    version: spec.version,
    mask: best.mask,
    modules: best.modules.map((row) => row.map(Boolean)),
  };
}

/**
 * El QR como SVG en una sola pieza: un `path` con un rectángulo por módulo.
 * Un `img` con miles de nodos no escalaría, pero a esta versión son cientos.
 */
export function qrSvg(text, { level = 'Q', quiet = 4, title = 'Código QR' } = {}) {
  const { size, modules } = qrMatrix(text, level);
  const side = size + quiet * 2;
  let path = '';
  for (let r = 0; r < size; r += 1) {
    for (let c = 0; c < size; c += 1) {
      if (modules[r][c]) path += `M${c + quiet} ${r + quiet}h1v1h-1z`;
    }
  }
  return `<svg class="qr-svg" viewBox="0 0 ${side} ${side}" role="img" aria-label="${title}"
    shape-rendering="crispEdges" xmlns="http://www.w3.org/2000/svg">
    <rect width="${side}" height="${side}" fill="#ffffff"/>
    <path d="${path}" fill="#0b1f17"/>
  </svg>`;
}
