"use client";

import { useEffect, useRef } from "react";

const CONFIG = {
  bgColor: "#f3f0e6",
  colorA: "#e6e6dc",
  colorB: "#b9ccd6",
  colorC: "#5f86a4",
  colorD: "#1d3a55",
  scale: 1.15,
  speed: 0.33,
  drift: 0.13,
  warp: 1.35,
  warpScale: 0.62,
  roughness: 0.54,
  lacunarity: 2.05,
  coat: 0.34,
  coatScale: 0.7,
  streak: 4.2,
  border: 0.86,
  borderSoft: 0.3,
  fibre: 0.055,
  fibreScale: 220,
  fibreAniso: 3.4,
  toe: 1.05,
  wash: 0.3,
  bandAmount: 0.18,
  bandCount: 7,
  bandSoft: 0.6,
  contrast: 1.24,
  midpoint: 0.5,
  sink: 0.14,
  glow: 0,
  grain: 0,
  grainAnim: 0,
  dither: 1.4,
  vignette: 0.06,
  cursor: 1,
  pointerRadius: 0.8,
  pointerStrength: 0.1,
  pointerBleach: 0.22,
  parallax: 0.0033,
  maxDpr: 1,
} as const;

const VERT = `#version 300 es
void main() {
  vec2 p = vec2((gl_VertexID << 1) & 2, gl_VertexID & 2);
  gl_Position = vec4(p * 2.0 - 1.0, 0.0, 1.0);
}`;

const FRAG = `#version 300 es
precision highp float;
out vec4 fragColor;

uniform vec2  iResolution;
uniform float iTime;
uniform vec2  iMouse;

uniform vec3  uBg, uColorA, uColorB, uColorC, uColorD;
uniform float uScale, uSpeed, uDrift, uWarp, uWarpScale, uRoughness, uLacunarity;
uniform float uCoat, uCoatScale, uStreak, uBorder, uBorderSoft;
uniform float uFibre, uFibreScale, uFibreAniso;
uniform float uToe, uWash, uBandAmount, uBandCount, uBandSoft;
uniform float uContrast, uMidpoint, uSink, uGlow;
uniform float uGrain, uDither, uVignette;
uniform float uPointerRadius, uPointerStrength, uPointerBleach, uParallax;
uniform float uGrainAnim;

#define OCTAVES 4

vec2 hash2(vec2 p) {
  p = vec2(dot(p, vec2(127.1, 311.7)), dot(p, vec2(269.5, 183.3)));
  return -1.0 + 2.0 * fract(sin(p) * 43758.5453123);
}

float snoise(vec2 p) {
  const float K1 = 0.366025404, K2 = 0.211324865;
  vec2 i = floor(p + (p.x + p.y) * K1);
  vec2 a = p - i + (i.x + i.y) * K2;
  float m = step(a.y, a.x);
  vec2 o = vec2(m, 1.0 - m);
  vec2 b = a - o + K2;
  vec2 c = a - 1.0 + 2.0 * K2;
  vec3 h = max(0.5 - vec3(dot(a, a), dot(b, b), dot(c, c)), 0.0);
  vec3 n = h * h * h * h * vec3(dot(a, hash2(i)), dot(b, hash2(i + o)), dot(c, hash2(i + 1.0)));
  return dot(n, vec3(70.0));
}

float fbm(vec2 p) {
  float v = 0.0, amp = 0.5;
  for (int i = 0; i < OCTAVES; i++) {
    v += amp * snoise(p);
    p *= uLacunarity;
    amp *= uRoughness;
  }
  return v;
}

vec3 ramp4(float t) {
  vec3 c = mix(uColorA, uColorB, smoothstep(0.00, 0.36, t));
  c = mix(c, uColorC, smoothstep(0.32, 0.70, t));
  c = mix(c, uColorD, smoothstep(0.66, 1.00, t));
  return c;
}

float triDither(vec2 fc) {
  float a = fract(sin(dot(fc, vec2(12.9898, 78.233))) * 43758.5453);
  float b = fract(sin(dot(fc + 17.0, vec2(12.9898, 78.233))) * 43758.5453);
  return (a + b - 1.0) / 255.0;
}

float houseGrain(vec2 fc) {
  uvec2 q = uvec2(fc) * uvec2(1597334677u, 3812015801u)
          + uint(floor(iTime * 24.0 * uGrainAnim)) * 2654435769u;
  uint n = q.x ^ q.y; n = n * 1664525u + 1013904223u; n ^= n >> 16u; n *= 2246822519u; n ^= n >> 13u;
  float a = float(n & 0xffffu) / 65535.0;
  n *= 3266489917u; n ^= n >> 16u;
  float b = float(n & 0xffffu) / 65535.0;
  return a + b - 1.0;
}

void main() {
  vec2 uv = (gl_FragCoord.xy - 0.5 * iResolution) / iResolution.y;
  float t = iTime * uSpeed;

  vec2 d = uv - iMouse;
  float near = exp(-dot(d, d) / max(1e-4, uPointerRadius * uPointerRadius));

  vec2 p = (uv - iMouse * uParallax) * uScale + d * near * uPointerStrength;

  vec2 q = vec2(fbm(p * uWarpScale + vec2(0.0, t * uDrift)),
                fbm(p * uWarpScale + vec2(4.7, 2.1) - t * uDrift * 0.6));
  float e = fbm(p + uWarp * q + vec2(t * 0.05, -t * 0.035)) * 0.5 + 0.5;

  float coat = fbm(vec2(p.x / max(0.2, uStreak), p.y) * uCoatScale * 3.0) * 0.5 + 0.5;

  vec2 ext = abs(uv) / vec2(0.5 * iResolution.x / iResolution.y, 0.5);
  float edge = max(ext.x, ext.y);
  float sheet = 1.0 - smoothstep(uBorder, uBorder + max(0.02, uBorderSoft), edge);
  sheet *= 0.75 + 0.25 * coat;

  float fib = snoise(vec2(uv.x * uFibreScale / max(0.2, uFibreAniso), uv.y * uFibreScale));

  float v = pow(clamp(e, 0.0, 1.0), uToe);
  v = mix(v, v * (0.7 + 0.6 * coat), uCoat);
  v += uWash * (fbm(p * 0.55 - vec2(t * 0.04, t * 0.02)) * 0.5);

  float steps = max(1.0, floor(uBandCount));
  float fs = v * steps;
  float banded = (floor(fs) + smoothstep(0.5 - uBandSoft * 0.5, 0.5 + uBandSoft * 0.5, fract(fs))) / steps;
  v = mix(v, banded, uBandAmount);

  v *= sheet;
  v -= near * uPointerBleach * 0.5;
  v += fib * uFibre;

  float f = clamp((v - uMidpoint) * uContrast + 0.5, 0.0, 1.0);

  vec3 col = ramp4(f);
  col += uColorD * uGlow * pow(f, 4.0);
  col = mix(uBg, col, smoothstep(0.0, max(0.01, uSink), f) * 0.90 + 0.10);

  col *= 1.0 - uVignette * dot(uv, uv);
  { float hgL = clamp(dot(col, vec3(0.299, 0.587, 0.114)), 0.0, 1.0);
    col += houseGrain(gl_FragCoord.xy) * uGrain * mix(1.0, 4.0 * hgL * (1.0 - hgL), 0.6); }
  col += triDither(gl_FragCoord.xy) * uDither;

  fragColor = vec4(clamp(col, 0.0, 1.0), 1.0);
}`;

function hexToVec3(hex: string): [number, number, number] {
  const n = Number.parseInt(hex.slice(1), 16);
  return [((n >> 16) & 255) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255];
}

function compile(gl: WebGL2RenderingContext, type: number, src: string) {
  const shader = gl.createShader(type);
  if (!shader) throw new Error("shader");
  gl.shaderSource(shader, src);
  gl.compileShader(shader);
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
    throw new Error(gl.getShaderInfoLog(shader) ?? "compile");
  }
  return shader;
}

export function CyanotypeBackground() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const gl = canvas.getContext("webgl2", {
      alpha: false,
      antialias: false,
      depth: false,
      stencil: false,
      powerPreference: "high-performance",
    });
    if (!gl) {
      canvas.style.display = "none";
      return;
    }

    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const speed = reduced ? 0 : CONFIG.speed;
    const cursor = reduced ? 0 : CONFIG.cursor;

    let program: WebGLProgram;
    try {
      program = gl.createProgram();
      gl.attachShader(program, compile(gl, gl.VERTEX_SHADER, VERT));
      gl.attachShader(program, compile(gl, gl.FRAGMENT_SHADER, FRAG));
      gl.linkProgram(program);
      if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
        throw new Error(gl.getProgramInfoLog(program) ?? "link");
      }
    } catch {
      canvas.style.display = "none";
      return;
    }

    gl.useProgram(program);
    gl.bindVertexArray(gl.createVertexArray());

    const loc = (name: string) => gl.getUniformLocation(program, name);
    const u1f = (name: string, value: number) => gl.uniform1f(loc(name), value);
    const u2f = (name: string, x: number, y: number) => gl.uniform2f(loc(name), x, y);
    const u3c = (name: string, hex: string) => {
      const [r, g, b] = hexToVec3(hex);
      gl.uniform3f(loc(name), r, g, b);
    };

    const applyConfig = () => {
      gl.useProgram(program);
      u3c("uBg", CONFIG.bgColor);
      u3c("uColorA", CONFIG.colorA);
      u3c("uColorB", CONFIG.colorB);
      u3c("uColorC", CONFIG.colorC);
      u3c("uColorD", CONFIG.colorD);
      u1f("uScale", CONFIG.scale);
      u1f("uSpeed", speed);
      u1f("uDrift", CONFIG.drift);
      u1f("uWarp", CONFIG.warp);
      u1f("uWarpScale", CONFIG.warpScale);
      u1f("uRoughness", CONFIG.roughness);
      u1f("uLacunarity", CONFIG.lacunarity);
      u1f("uCoat", CONFIG.coat);
      u1f("uCoatScale", CONFIG.coatScale);
      u1f("uStreak", CONFIG.streak);
      u1f("uBorder", CONFIG.border);
      u1f("uBorderSoft", CONFIG.borderSoft);
      u1f("uFibre", CONFIG.fibre);
      u1f("uFibreScale", CONFIG.fibreScale);
      u1f("uFibreAniso", CONFIG.fibreAniso);
      u1f("uToe", CONFIG.toe);
      u1f("uWash", CONFIG.wash);
      u1f("uBandAmount", CONFIG.bandAmount);
      u1f("uBandCount", CONFIG.bandCount);
      u1f("uBandSoft", CONFIG.bandSoft);
      u1f("uContrast", CONFIG.contrast);
      u1f("uMidpoint", CONFIG.midpoint);
      u1f("uSink", CONFIG.sink);
      u1f("uGlow", CONFIG.glow);
      u1f("uGrain", CONFIG.grain);
      u1f("uGrainAnim", CONFIG.grainAnim);
      u1f("uDither", CONFIG.dither);
      u1f("uVignette", CONFIG.vignette);
      u1f("uPointerRadius", CONFIG.pointerRadius);
      u1f("uPointerStrength", CONFIG.pointerStrength);
      u1f("uPointerBleach", CONFIG.pointerBleach);
      u1f("uParallax", CONFIG.parallax);
    };

    const resize = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, CONFIG.maxDpr);
      const w = Math.max(1, Math.round(window.innerWidth * dpr));
      const h = Math.max(1, Math.round(window.innerHeight * dpr));
      if (canvas.width !== w || canvas.height !== h) {
        canvas.width = w;
        canvas.height = h;
      }
      gl.viewport(0, 0, w, h);
      gl.useProgram(program);
      u2f("iResolution", w, h);
    };

    let resizeQueued = false;
    const onResize = () => {
      if (resizeQueued) return;
      resizeQueued = true;
      requestAnimationFrame(() => {
        resizeQueued = false;
        resize();
      });
    };

    const mouse = { x: 0, y: 0, ax: 0, ay: 0, tx: 0, ty: 0, restX: 0, restY: 0 };
    const aim = (e: PointerEvent) => {
      const a = window.innerWidth / window.innerHeight;
      mouse.tx = (e.clientX / window.innerWidth - 0.5) * a;
      mouse.ty = 0.5 - e.clientY / window.innerHeight;
    };

    let visible = true;
    const observer = new IntersectionObserver(
      (entries) => {
        visible = entries[0]?.isIntersecting ?? false;
      },
      { threshold: 0 },
    );
    observer.observe(canvas);

    applyConfig();
    resize();
    gl.drawArrays(gl.TRIANGLES, 0, 3);

    if (reduced) {
      window.addEventListener("resize", onResize, { passive: true });
      return () => {
        window.removeEventListener("resize", onResize);
        observer.disconnect();
      };
    }

    let prevT = performance.now();
    let clock = 0;
    let raf = 0;

    const frame = (now: number) => {
      raf = requestAnimationFrame(frame);
      const raw = now - prevT;
      prevT = now;
      if (!visible || document.hidden) return;
      const ms = raw > 50 ? 50 : raw < 4.167 ? 4.167 : raw;
      const s = ms > 36.7 ? 2.2 : ms * 0.06;
      clock += ms * 0.001;

      const kLead = 0.105 * s;
      const kBody = 0.043 * s;
      mouse.ax += (mouse.tx - mouse.ax) * kLead;
      mouse.ay += (mouse.ty - mouse.ay) * kLead;
      mouse.x += (mouse.ax - mouse.x) * kBody;
      mouse.y += (mouse.ay - mouse.y) * kBody;

      u1f("iTime", clock);
      if (!cursor) {
        mouse.tx = mouse.restX;
        mouse.ty = mouse.restY;
      }
      u2f("iMouse", mouse.x, mouse.y);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
    };

    window.addEventListener("resize", onResize, { passive: true });
    window.addEventListener("pointermove", aim, { passive: true });
    window.addEventListener("pointerdown", aim, { passive: true });
    raf = requestAnimationFrame(frame);

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", onResize);
      window.removeEventListener("pointermove", aim);
      window.removeEventListener("pointerdown", aim);
      observer.disconnect();
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      aria-hidden
      className="pointer-events-none fixed inset-0 z-0 h-full w-full"
      style={{ background: CONFIG.bgColor }}
    />
  );
}
