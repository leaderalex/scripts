<?php
// scan_index_form_action.php
// Рекурсивно ищет теги <form> в index.php и анализирует атрибут action.
// Игнорирует пустой action, '#' и action="tosend.php".
// Пишет отчёт в report.json (в текущей рабочей директории) и строчку лога в __DIR__/start.txt.

declare(strict_types=1);
error_reporting(E_ALL);
ini_set('display_errors', '0'); // чтобы не ломать HTML, ошибки в error_log

$root = '../';
$reportFile = 'report.json';

// --- Утилиты ---
function lineNumberAtPos(string $src, int $pos): int {
    return substr_count(substr($src, 0, $pos), "\n") + 1;
}
function snippetAround(string $src, int $pos, int $lenBefore = 60, int $lenAfter = 160): string {
    $start = max(0, $pos - $lenBefore);
    return substr($src, $start, $lenBefore + $lenAfter) ?: '';
}
function classifyAction(?string $action): array {
    $flags = [];
    if ($action === null) return $flags;
    $a = trim($action);

    // игнорируем: пустой, #, tosend.php
    if ($a === '' || $a === '#' || strtolower($a) === 'tosend.php') return [];

    if (stripos($a, 'javascript:') === 0) $flags[] = 'javascript_uri';
    if (stripos($a, 'data:') === 0)       $flags[] = 'data_uri';
    if (preg_match('~^https?://~i', $a))  $flags[] = 'absolute_http';
    if (stripos($a, 'mailto:') === 0)     $flags[] = 'mailto';
    if (stripos($a, '<?php') !== false)   $flags[] = 'php_in_action';
    if (stripos($a, 'eval(') !== false)   $flags[] = 'eval_in_action';
    if (stripos($a, 'base64') !== false || stripos($a, 'atob(') !== false) $flags[] = 'base64_hint';
    return $flags;
}

// Проверка корня
if (!is_dir($root)) {
    error_log("Ошибка: папка для сканирования не найдена: $root");
    // покажем простую страницу, чтобы не был «белый экран»
    echo "<!doctype html><meta charset='utf-8'><p>Ошибка: папка для сканирования не найдена: <code>" . htmlspecialchars($root, ENT_QUOTES | ENT_SUBSTITUTE) . "</code></p>";
    exit;
}

// --- Сканирование ---
$rii = new RecursiveIteratorIterator(new RecursiveDirectoryIterator($root, RecursiveDirectoryIterator::SKIP_DOTS));
$results = [];

foreach ($rii as $file) {
    if (!$file->isFile()) continue;
    if (strtolower($file->getFilename()) !== 'index.php') continue;

    $path = $file->getPathname();
    $src = @file_get_contents($path);
    if ($src === false) {
        error_log("Предупреждение: не удалось прочитать $path");
        continue;
    }

    $found = [];

    if (preg_match_all('/<form\b[^>]*>/i', $src, $forms, PREG_OFFSET_CAPTURE)) {
        foreach ($forms[0] as $fm) {
            $tagText = $fm[0];
            $pos = $fm[1];

            // достаём action
            $action = null;
            if (preg_match('/\baction\s*=\s*(["\'])(.*?)\1/i', $tagText, $m)) {
                $action = $m[2];
            } elseif (preg_match('/\baction\s*=\s*([^\s>]+)/i', $tagText, $m)) {
                $action = $m[1];
            }

            // игнор без action / пустой / # / tosend.php
            if ($action === null) continue;
            $actTrim = trim($action);
            if ($actTrim === '' || $actTrim === '#' || strtolower($actTrim) === 'tosend.php') continue;

            $flags = classifyAction($action);
            if (empty($flags)) continue; // логируем только подозрительные

            $found[] = [
                'tag'     => 'form',
                'line'    => lineNumberAtPos($src, $pos),
                'action'  => $action,
                'flags'   => $flags,
                'snippet' => snippetAround($src, $pos),
            ];
        }
    }

    if (!empty($found)) {
        $results[$path] = $found;
    }
}

// --- Логирование в файл рядом со скриптом ---
$logFile = __DIR__ . '/start.txt';
$logData = [
    'time'          => date('Y-m-d H:i:s'),
    'cwd'           => getcwd(),
    'script_dir'    => __DIR__,
    'results_total' => count($results),
    'files_counts'  => array_map('count', $results),
];
$line = json_encode($logData, JSON_UNESCAPED_UNICODE) . PHP_EOL;
$ok = @file_put_contents($logFile, $line, FILE_APPEND | LOCK_EX);
if ($ok === false) {
    error_log("Не удалось записать лог в $logFile (cwd=" . getcwd() . ")");
}

// --- Сохраняем отчёт ---
$dir = dirname($reportFile);
if ($dir !== '' && $dir !== '.' && !is_dir($dir)) {
    @mkdir($dir, 0777, true);
}
$reportJson = json_encode($results, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE);
if ($reportJson === false) {
    error_log('Ошибка JSON: ' . json_last_error_msg());
} else {
    $okReport = @file_put_contents($reportFile, $reportJson, LOCK_EX);
    if ($okReport === false) {
        error_log("Не удалось записать отчёт в $reportFile (cwd=" . getcwd() . ")");
    }
}

// --- HTML вывод ---
?><!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<title>Scan index.php — FORM action</title>
<style>
body{font-family:system-ui,Arial,sans-serif;margin:20px}
.card{border:1px solid #ddd;padding:12px;margin:10px 0;border-radius:6px;background:#fff}
.snip{font-family:monospace;background:#f7f7f7;padding:6px;white-space:pre-wrap;margin-top:6px}
.flag{display:inline-block;background:#fee;border:1px solid #f99;padding:2px 6px;margin:2px;border-radius:4px;font-size:12px}
.empty{color:#666}
small.meta{color:#555}
</style>
</head>
<body>
<h1>Поиск подозрительных <code>&lt;form&gt;</code> с нестандартным <code>action</code></h1>

<?php if (empty($results)): ?>
    <p class="empty">Ничего не найдено (все формы нормальные, пустые/“#”/“tosend.php” — игнорируются).</p>
<?php else: ?>
    <p>Найдено файлов: <?php echo count($results); ?>. Отчёт: <code><?php echo htmlspecialchars($reportFile, ENT_QUOTES | ENT_SUBSTITUTE); ?></code></p>
    <?php foreach ($results as $path => $items): ?>
        <div class="card">
            <strong><?php echo htmlspecialchars($path, ENT_QUOTES | ENT_SUBSTITUTE); ?></strong>
            <?php foreach ($items as $it): ?>
                <div style="margin-top:8px">
                    <div>
                        <b>FORM</b> — строка <?php echo intval($it['line']); ?>
                        <span>action: <?php echo htmlspecialchars($it['action'], ENT_QUOTES | ENT_SUBSTITUTE); ?></span>
                        <?php foreach ($it['flags'] as $fl): ?>
                            <span class="flag"><?php echo htmlspecialchars($fl, ENT_QUOTES | ENT_SUBSTITUTE); ?></span>
                        <?php endforeach; ?>
                    </div>
                    <div class="snip"><?php echo htmlspecialchars($it['snippet'], ENT_QUOTES | ENT_SUBSTITUTE); ?></div>
                </div>
            <?php endforeach; ?>
        </div>
    <?php endforeach; ?>
<?php endif; ?>

<hr>
<p class="meta">
Лог: <code><?php echo htmlspecialchars($logFile, ENT_QUOTES | ENT_SUBSTITUTE); ?></code><br>
Отчёт: <code><?php echo htmlspecialchars($reportFile, ENT_QUOTES | ENT_SUBSTITUTE); ?></code><br>
Рабочая директория (cwd): <code><?php echo htmlspecialchars(getcwd(), ENT_QUOTES | ENT_SUBSTITUTE); ?></code>
</p>
</body>
</html>
