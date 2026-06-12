/* Протокол очереди analysis_tasks — копия поведения Python-воркера.
 *
 * Node-воркер работает с ТОЙ ЖЕ таблицей analysis_tasks параллельно
 * Python-воркеру (#255): claim делается SELECT ... FOR UPDATE SKIP LOCKED и
 * UPDATE в ОДНОЙ транзакции — два воркера не возьмут одно задание, конкурент
 * при SKIP LOCKED просто пропустит залоченную строку.
 *
 * Все функции принимают `q` — async-функцию запроса `(sql, params) -> {rows}`
 * (в проде это client.query пакета pg, в тестах — фейк). Времена ставит
 * ПРИЛОЖЕНИЕ (ISO-строки UTC), не БД — как в Python-воркере.
 */

/* Взять старейшее задание из очереди (FIFO) и перевести его в running.
 * Возвращает задание или null, если очередь пуста. */
export async function claimNextTask(q, nowIso) {
  await q('BEGIN');
  try {
    const sel = await q(
      "SELECT id, source_type, source_ref, room_id, camera_id, pipeline, params " +
      "FROM analysis_tasks WHERE status = 'queued' " +
      'ORDER BY created_at LIMIT 1 FOR UPDATE SKIP LOCKED',
    );
    if (!sel.rows.length) {
      await q('COMMIT');
      return null;
    }
    const task = sel.rows[0];
    await q("UPDATE analysis_tasks SET status = 'running', started_at = $1 WHERE id = $2", [
      nowIso,
      task.id,
    ]);
    await q('COMMIT');
    return task;
  } catch (err) {
    await q('ROLLBACK');
    throw err;
  }
}

/* Завершить задание успешно: status=done, сводка в result (jsonb). */
export async function markDone(q, taskId, tsIso, result) {
  await q("UPDATE analysis_tasks SET status = 'done', finished_at = $1, result = $2 WHERE id = $3", [
    tsIso,
    JSON.stringify(result),
    taskId,
  ]);
}

/* Завершить задание с ошибкой: status=failed, текст ошибки. */
export async function markFailed(q, taskId, tsIso, error) {
  await q("UPDATE analysis_tasks SET status = 'failed', finished_at = $1, error = $2 WHERE id = $3", [
    tsIso,
    String(error),
    taskId,
  ]);
}

/* Отметка живости сервиса (watchdog планировщика, #284). */
export async function writeHeartbeat(q, service, tsIso) {
  await q(
    'INSERT INTO service_heartbeats (service, ts) VALUES ($1, $2) ' +
    'ON CONFLICT (service) DO UPDATE SET ts = EXCLUDED.ts',
    [service, tsIso],
  );
}

/* Камера задания: тумблеры аналитики и общий выключатель (null = камеры нет). */
export async function loadCamera(q, cameraId) {
  const res = await q('SELECT id, name, room_id, enabled, analytics FROM cameras WHERE id = $1', [
    cameraId,
  ]);
  return res.rows[0] ?? null;
}

/* ROI-зоны камеры в формате движка analysis-core.
 *
 * Ядро знает только типы table/floor/window (уборка/покрытие); зоны
 * forbidden/work обслуживает Python-детектор присутствия — до его вывода из
 * эксплуатации (#255 шаг 3) такие зоны Node-воркеру не передаются. */
export async function loadCameraZones(q, cameraId) {
  const res = await q(
    'SELECT id, zone_type, polygon, note FROM camera_zones WHERE camera_id = $1 ORDER BY id',
    [cameraId],
  );
  return res.rows
    .filter((r) => ['table', 'floor', 'window'].includes(r.zone_type))
    .map((r) => ({
      type: r.zone_type,
      pts: typeof r.polygon === 'string' ? JSON.parse(r.polygon) : r.polygon,
      zoneId: r.id,
      name: r.note ?? r.zone_type,
      cov: 0,
    }));
}
