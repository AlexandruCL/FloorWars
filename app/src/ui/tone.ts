// Team colours come from the server and can be anything, #000000 included. Every team colour
// passes through teamTone before it is drawn, so a lit window always reads on the night ground
// (DESIGN.md section 5).

export type Tone = { tone: string; ink: string };

const NIGHT = '#0A0E16';
const CHALK = '#EEF0F4';

type Rgb = [number, number, number];

const toLinear = (c: number) =>
  c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
const toGamma = (c: number) =>
  c <= 0.0031308 ? 12.92 * c : 1.055 * c ** (1 / 2.4) - 0.055;

function parse(hex: string): Rgb {
  return [1, 3, 5].map(i =>
    toLinear(parseInt(hex.slice(i, i + 2), 16) / 255),
  ) as Rgb;
}

function format(rgb: Rgb): string {
  return (
    '#' +
    rgb
      .map(c =>
        Math.round(Math.min(1, Math.max(0, toGamma(c))) * 255)
          .toString(16)
          .padStart(2, '0'),
      )
      .join('')
      .toUpperCase()
  );
}

// OKLab, Ottosson's matrices on linear sRGB.
function toOklch([r, g, b]: Rgb): [number, number, number] {
  const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
  const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
  const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
  const L = 0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s;
  const a = 1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s;
  const bb = 0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s;
  return [L, Math.hypot(a, bb), Math.atan2(bb, a)];
}

function fromOklch(L: number, C: number, h: number): Rgb {
  const a = C * Math.cos(h);
  const b = C * Math.sin(h);
  const l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3;
  const m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3;
  const s = (L - 0.0894841775 * a - 1.291485548 * b) ** 3;
  return [
    4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
    -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
    -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s,
  ];
}

const inGamut = (rgb: Rgb) => rgb.every(c => c >= -1e-6 && c <= 1 + 1e-6);
const clamp = (v: number, lo: number, hi: number) =>
  Math.min(hi, Math.max(lo, v));

function luminance(hex: string): number {
  const [r, g, b] = parse(hex);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

export function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

export function teamTone(hex: string): Tone {
  const valid = /^#[0-9A-Fa-f]{6}$/.test(hex);
  const [l0, c0, h] = toOklch(parse(valid ? hex : '#808080'));
  const grey = c0 < 0.03;
  const L = grey ? clamp(l0, 0.62, 0.9) : clamp(l0, 0.66, 0.84);
  let C = grey ? c0 : Math.min(c0, 0.17);
  // Lower chroma until the colour fits sRGB, so the hue never shifts.
  if (!inGamut(fromOklch(L, C, h))) {
    let lo = 0;
    let hi = C;
    for (let i = 0; i < 24; i++) {
      C = (lo + hi) / 2;
      if (inGamut(fromOklch(L, C, h))) {
        lo = C;
      } else {
        hi = C;
      }
    }
    C = lo;
  }
  const tone = format(fromOklch(L, C, h));
  const ink = contrast(tone, NIGHT) >= contrast(tone, CHALK) ? NIGHT : CHALK;
  return { tone, ink };
}
