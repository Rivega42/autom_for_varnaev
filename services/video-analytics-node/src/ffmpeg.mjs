/* Извлечение сырых кадров из RTSP-потока или видеофайла через ffmpeg.
 *
 * ffmpeg запускается дочерним процессом и пишет в stdout НЕсжатые кадры
 * (rawvideo, pix_fmt rgba) фиксированного размера WIDTH x HEIGHT — байты в
 * точности в раскладке ImageData.data, кадр передаётся в MediaPipe без
 * переупаковки. Размер фиксируем (по умолчанию 640x360, 16:9 — совпадает с
 * aspect движка): для нарезки потока на кадры нужен точный размер кадра в
 * байтах (w*h*4).
 *
 * Поток выдаётся как async-генератор кадров:
 *   { data: Uint8ClampedArray, width, height, ts, wallTs }
 * где ts — монотонное время кадра в мс (index * 1000/fps), wallTs — стенные
 * часы момента получения кадра.
 *
 * spawnImpl/ffmpegPath инъектируются для тестов (фейковый процесс без ffmpeg).
 */

import { spawn } from 'node:child_process';

/* Аргументы ffmpeg для источника: RTSP-поток (по TCP — UDP теряет пакеты на
 * Wi-Fi/нагруженной LAN) или видеофайл. -an/-sn отбрасывают аудио/субтитры. */
export function buildFfmpegArgs({ source, fps, width, height }) {
  const isRtsp = /^rtsps?:\/\//i.test(source);
  return [
    ...(isRtsp ? ['-rtsp_transport', 'tcp'] : []),
    '-i', source,
    '-an', '-sn',
    '-vf', `fps=${fps},scale=${width}:${height}`,
    '-f', 'rawvideo',
    '-pix_fmt', 'rgba',
    'pipe:1',
  ];
}

export async function* rawFrames({
  source,
  fps = 5,
  width = 640,
  height = 360,
  maxFrames = Infinity,
  ffmpegPath = 'ffmpeg',
  spawnImpl = spawn,
  log = () => {},
}) {
  const args = buildFfmpegArgs({ source, fps, width, height });
  const proc = spawnImpl(ffmpegPath, args, { stdio: ['ignore', 'pipe', 'pipe'] });

  // stderr обязательно дренируем (иначе пайп заполняется и ffmpeg встаёт);
  // храним хвост для диагностики, если процесс умрёт до первого кадра.
  let stderrTail = '';
  proc.stderr.on('data', (chunk) => {
    stderrTail = (stderrTail + chunk.toString()).slice(-2000);
  });

  const frameSize = width * height * 4;
  const msPerFrame = 1000 / fps;
  let buffered = Buffer.alloc(0);
  let index = 0;

  try {
    for await (const chunk of proc.stdout) {
      buffered = buffered.length ? Buffer.concat([buffered, chunk]) : chunk;
      // Чанки stdout не выровнены по границе кадра — копим до полного кадра.
      while (buffered.length >= frameSize) {
        const frame = buffered.subarray(0, frameSize);
        buffered = buffered.subarray(frameSize);
        yield {
          // Копия обязательна: subarray смотрит в переиспользуемый буфер.
          data: new Uint8ClampedArray(frame),
          width,
          height,
          ts: Math.round(index * msPerFrame),
          wallTs: Date.now(),
        };
        index++;
        if (index >= maxFrames) return;
      }
    }
    // Поток закончился (файл дочитан или RTSP оборвался). Для файла это норма;
    // если не получили ни кадра — поднимаем ошибку с хвостом stderr.
    if (index === 0) {
      throw new Error(`ffmpeg не выдал ни одного кадра из ${source}: ${stderrTail.trim()}`);
    }
    log(`ffmpeg: источник ${source} исчерпан, кадров: ${index}`);
  } finally {
    // Генератор закрыт (return/throw/break у потребителя) — гасим процесс.
    proc.kill('SIGKILL');
  }
}
