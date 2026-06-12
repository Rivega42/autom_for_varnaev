/* MediaPipe PoseLandmarker (tasks-vision) в чистом Node.js — без браузера.
 *
 * Рецепт выработан спайком на хосте (#255). Ключевой факт: tasks-vision 0.10.x
 * заливает ЛЮБОЙ кадр (даже при delegate:'CPU') в граф через WebGL-текстуру —
 * пути «сырых пикселей» в JS-API нет, поэтому в Node обязателен настоящий
 * WebGL: пакет `gl` (headless-gl, ANGLE). Остальное закрывают полифиллы:
 *
 *  1. self = globalThis — бандл ищет фабрику wasm в self.ModuleFactory;
 *  2. ImageData — минимальный класс {data, width, height};
 *  3. importScripts — UMD-загрузчик wasm подключается через require();
 *  4. OffscreenCanvas — обёртка headless-gl, отдаёт контекст как «webgl2»
 *     с GLES3-шимом (fence sync, texStorage2D, VAO/инстансинг и адаптеры
 *     WebGL2-перегрузок с (view, offset) — readPixels/texImage2D/buffer*).
 *     Без «webgl2» MediaPipe падает (нет fence sync → Check failed);
 *  5. WebGLRenderingContext — пустышка: Emscripten проверяет, что контекст
 *     «webgl2» НЕ instanceof WebGLRenderingContext;
 *  6. fileset вручную {wasmLoaderPath, wasmBinaryPath} — без FilesetResolver
 *     (его fetch не умеет file://); .wasm Emscripten в Node читает сам;
 *  7. модель — modelAssetBuffer из fs (без fetch и HTTP-сервера).
 *
 * Загрузка ленивая: тесты CI модуль не импортируют (нужны нативный `gl`
 * и ассеты MediaPipe — ставятся npm-пакетом в образе воркера).
 */

import fs from 'node:fs';
import { createRequire } from 'node:module';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const require = createRequire(import.meta.url);

const GL_ALREADY_SIGNALED = 0x911a;
const GL_SIGNALED = 0x9119;
// Каналы пиксельных форматов WebGL: RGBA/RGB/LUMINANCE/ALPHA/LUMINANCE_ALPHA.
const CHANNELS = { 6408: 4, 6407: 3, 6409: 1, 6406: 1, 6410: 2 };

/* GLES3-шим поверх headless-gl (WebGL1): ровно то, что зовёт MediaPipe.
 * Всё однопоточно и на одном контексте, поэтому sync-объекты «всегда
 * сигнальные». КРИТИЧНО: WebGL2-перегрузки с (view, offset) переводим в
 * WebGL1-формы сами — headless-gl игнорирует offset и пишет в начало кучи
 * wasm (порча памяти и Aborted()). */
function makeGles3Proxy(gl, canvas) {
  const vaoExt = gl.getExtension('OES_vertex_array_object');
  const instExt = gl.getExtension('ANGLE_instanced_arrays');
  const drawBufExt = gl.getExtension('WEBGL_draw_buffers');
  // texStorage2D эмулируем через texImage2D: sized-формат -> (format, type).
  const fmtMap = {
    0x8058: [gl.RGBA, gl.UNSIGNED_BYTE], // RGBA8
    0x8051: [gl.RGB, gl.UNSIGNED_BYTE], // RGB8
    0x8229: [gl.LUMINANCE, gl.UNSIGNED_BYTE], // R8 (приближение для WebGL1)
    0x8814: [gl.RGBA, gl.FLOAT], // RGBA32F
  };
  const gles3 = {
    fenceSync: () => ({}),
    deleteSync: () => {},
    isSync: () => true,
    clientWaitSync: () => GL_ALREADY_SIGNALED,
    waitSync: () => {},
    getSyncParameter: () => GL_SIGNALED,
    texStorage2D: (target, levels, ifmt, w, h) => {
      const [fmt, type] = fmtMap[ifmt] ?? [gl.RGBA, gl.UNSIGNED_BYTE];
      for (let l = 0; l < levels; l++) {
        gl.texImage2D(target, l, fmt, Math.max(1, w >> l), Math.max(1, h >> l), 0, fmt, type, null);
      }
    },
    createVertexArray: () => vaoExt.createVertexArrayOES(),
    deleteVertexArray: (v) => vaoExt.deleteVertexArrayOES(v),
    bindVertexArray: (v) => vaoExt.bindVertexArrayOES(v),
    isVertexArray: (v) => vaoExt.isVertexArrayOES(v),
    vertexAttribDivisor: (i, d) => instExt.vertexAttribDivisorANGLE(i, d),
    drawArraysInstanced: (m, f, c, p) => instExt.drawArraysInstancedANGLE(m, f, c, p),
    drawElementsInstanced: (m, c, t, o, p) => instExt.drawElementsInstancedANGLE(m, c, t, o, p),
    drawBuffers: (b) => drawBufExt.drawBuffersWEBGL(b),
    readBuffer: () => {},
    invalidateFramebuffer: () => {},
    readPixels: (x, y, w, h, fmt, type, view, offset) => {
      if (view && typeof offset === 'number' && offset > 0) {
        const ch = CHANNELS[fmt] ?? 4;
        return gl.readPixels(x, y, w, h, fmt, type, view.subarray(offset, offset + w * h * ch));
      }
      return gl.readPixels(x, y, w, h, fmt, type, view);
    },
    texSubImage2D: (...a) => {
      // WebGL2: (target,level,xo,yo,w,h,fmt,type,view,offset) — 10 аргументов.
      if (a.length === 10 && a[8] && typeof a[9] === 'number') {
        const n = a[4] * a[5] * (CHANNELS[a[6]] ?? 4);
        return gl.texSubImage2D(...a.slice(0, 8), a[8].subarray(a[9], a[9] + n));
      }
      return gl.texSubImage2D(...a);
    },
    bufferData: (...a) => {
      // WebGL2: (target, view, usage, srcOffset, length) — 5 аргументов.
      if (a.length === 5 && a[1] && typeof a[3] === 'number') {
        return gl.bufferData(a[0], a[1].subarray(a[3], a[3] + a[4]), a[2]);
      }
      return gl.bufferData(...a);
    },
    bufferSubData: (...a) => {
      // WebGL2: (target, dstByteOffset, view, srcOffset, length) — 5 аргументов.
      if (a.length === 5 && a[2] && typeof a[3] === 'number') {
        return gl.bufferSubData(a[0], a[1], a[2].subarray(a[3], a[3] + a[4]));
      }
      return gl.bufferSubData(...a);
    },
  };
  return new Proxy(gl, {
    get(target, prop) {
      if (prop === 'canvas') return canvas;
      if (prop in gles3) return gles3[prop];
      if (prop === 'texImage2D') {
        return (...a) => {
          // DOM-перегрузка: (target, level, ifmt, fmt, type, source-объект).
          if (a.length === 6 && a[5] && typeof a[5] === 'object') {
            const src = a[5];
            const px =
              src.data instanceof Uint8ClampedArray
                ? new Uint8Array(src.data.buffer, src.data.byteOffset, src.data.length)
                : src.data;
            return target.texImage2D(a[0], a[1], a[2], src.width, src.height, 0, a[3], a[4], px);
          }
          // WebGL2-перегрузка: (..., fmt, type, view, offset) — 10 аргументов.
          if (a.length === 10 && a[8] && typeof a[9] === 'number') {
            const n = a[3] * a[4] * (CHANNELS[a[6]] ?? 4);
            return target.texImage2D(...a.slice(0, 8), a[8].subarray(a[9], a[9] + n));
          }
          return target.texImage2D(...a);
        };
      }
      const v = target[prop];
      return typeof v === 'function' ? v.bind(target) : v;
    },
    set(target, prop, value) {
      target[prop] = value;
      return true;
    },
  });
}

/* Выполнить UMD-загрузчик wasm как classic script и вернуть фабрику модуля.
 *
 * Нельзя просто require(): в npm-пакете @mediapipe/tasks-vision стоит
 * "type": "module", и require() .js-файла возвращает пустой ESM-неймспейс
 * (Node ≥22.12 умеет require(esm) и не бросает ERR_REQUIRE_ESM) — UMD-ветка
 * `module.exports = ModuleFactory` в ESM-контексте не выполняется. Поэтому
 * исполняем код с CJS-окружением вручную. */
function loadUmdFactory(p) {
  const code = fs.readFileSync(p, 'utf8');
  const mod = { exports: {} };
  const localRequire = createRequire(pathToFileURL(p).href);
  new Function('module', 'exports', 'require', '__filename', '__dirname', 'self', code)(
    mod,
    mod.exports,
    localRequire,
    p,
    path.dirname(p),
    globalThis,
  );
  if (typeof mod.exports === 'function') return mod.exports;
  if (typeof globalThis.ModuleFactory === 'function') return globalThis.ModuleFactory;
  throw new Error(`UMD-загрузчик wasm не отдал фабрику: ${p}`);
}

/* Полифиллы браузерных глобалов, которых ждёт vision_bundle. Идемпотентно. */
function installGlobals() {
  if (globalThis.self === globalThis && globalThis.OffscreenCanvas) return;
  const createGL = require('gl'); // headless-gl: настоящий WebGL 1.0 (ANGLE)

  globalThis.self = globalThis;

  globalThis.ImageData = class ImageData {
    constructor(dataOrWidth, widthOrHeight, height) {
      if (typeof dataOrWidth === 'number') {
        this.width = dataOrWidth;
        this.height = widthOrHeight;
        this.data = new Uint8ClampedArray(this.width * this.height * 4);
      } else {
        this.data = dataOrWidth;
        this.width = widthOrHeight;
        this.height = height ?? this.data.length / (4 * widthOrHeight);
      }
    }
  };

  globalThis.importScripts = (url) => {
    const p = String(url).startsWith('file:') ? fileURLToPath(String(url)) : String(url);
    globalThis.ModuleFactory = loadUmdFactory(p);
  };

  // Пустышка НАМЕРЕННО не совпадает с классом headless-gl: Emscripten отдаёт
  // контекст «webgl2» только если он НЕ instanceof WebGLRenderingContext.
  globalThis.WebGLRenderingContext = class WebGLRenderingContext {};

  globalThis.OffscreenCanvas = class OffscreenCanvas {
    constructor(width, height) {
      this._w = width;
      this._h = height;
      this._gl = null;
      this._proxy = null;
    }
    get width() {
      return this._w;
    }
    set width(v) {
      this._w = v;
      this._resize();
    }
    get height() {
      return this._h;
    }
    set height(v) {
      this._h = v;
      this._resize();
    }
    _resize() {
      if (this._gl) {
        const ext = this._gl.getExtension('STACKGL_resize_drawingbuffer');
        if (ext) ext.resize(Math.max(1, this._w), Math.max(1, this._h));
      }
    }
    getContext(type, attrs) {
      if (type !== 'webgl2' && type !== 'webgl' && type !== 'experimental-webgl') return null;
      if (!this._proxy) {
        const gl = createGL(Math.max(1, this._w), Math.max(1, this._h), attrs);
        if (!gl) return null;
        this._gl = gl;
        this._proxy = makeGles3Proxy(gl, this);
      }
      return this._proxy;
    }
  };
}

/* Известный риск tasks-vision в Node (google-ai-edge/mediapipe#5237):
 * вызов может молча зависнуть — каждый detect страхуем таймаутом. */
function withTimeout(promiseLike, ms, label) {
  return Promise.race([
    Promise.resolve(promiseLike),
    new Promise((_, rej) =>
      setTimeout(() => rej(new Error(`ТАЙМАУТ ${ms} мс: ${label}`)), ms).unref(),
    ),
  ]);
}

/* Обёртка лэндмаркера под контракт детектора mediapipeFrames:
 * detect(frame {data,width,height}, tsMs) -> {lm, world} | null.
 * Вынесена отдельно от загрузки ассетов — тестируется на фейке. */
export function wrapLandmarker(landmarker, { timeoutMs = 30_000 } = {}) {
  let lastTs = 0;
  return {
    async detect(frame, ts) {
      const img = new globalThis.ImageData(frame.data, frame.width, frame.height);
      // detectForVideo требует СТРОГО возрастающий timestamp.
      const t = Math.max(Math.round(ts), lastTs + 1);
      lastTs = t;
      const res = await withTimeout(
        landmarker.detectForVideo(img, t),
        timeoutMs,
        'PoseLandmarker.detectForVideo',
      );
      if (!res.landmarks || !res.landmarks.length) return null;
      const lm = res.landmarks[0].map((p) => ({
        x: p.x,
        y: p.y,
        z: p.z,
        visibility: p.visibility,
      }));
      const world = res.worldLandmarks?.[0]?.map((p) => ({ x: p.x, y: p.y, z: p.z })) ?? null;
      return { lm, world };
    },
    close() {
      landmarker.close();
    },
  };
}

/* Боевая фабрика детектора: полифиллы + бандл + wasm + модель. */
export async function createPoseDetector({
  modelPath,
  wasmDir,
  bundlePath,
  variant = 'vision_wasm_internal',
  timeoutMs = 30_000,
}) {
  installGlobals();
  // ImageData нужен бандлу как глобал ДО импорта (instanceof-проверки).
  const { PoseLandmarker } = await import(pathToFileURL(bundlePath).href);
  const fileset = {
    wasmLoaderPath: pathToFileURL(path.join(wasmDir, `${variant}.js`)).href,
    // .wasm Emscripten в Node читает сам через fs — обычный путь.
    wasmBinaryPath: path.join(wasmDir, `${variant}.wasm`),
  };
  const landmarker = await PoseLandmarker.createFromOptions(fileset, {
    baseOptions: {
      // Буфером из fs: fetch в Node не умеет file://.
      modelAssetBuffer: new Uint8Array(fs.readFileSync(modelPath)),
      delegate: 'CPU',
    },
    runningMode: 'VIDEO',
    numPoses: 1,
  });
  return wrapLandmarker(landmarker, { timeoutMs });
}
