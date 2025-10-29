<?php
// scan_and_replace_form_action.php
// Сканирует ../ на предмет index.php, делает backup и заменяет action форм на tosend.php
// По умолчанию заменяет ТОЛЬКО "подозрительные" action.
// Пишет лог в __DIR__/start.txt и отчёт в report.json

declare(strict_types=1);
error_reporting(E_ALL);
ini_set('display_errors', '0');

$root = '../';
$reportFile = 'report.json';
$logFile = __DIR__ . '/start.txt';

// Если поставить true — заменяет все action (кроме пустых/#/tosend.php)
$forceReplace = false;

// --- Утилиты ---
$now = date('Y-m-d H:i:s');
function isSuspiciousAction(string $a): bool {
    $lower = strtolower($a);
    if ($lower === '' || $lower === '#' || $lower === 'tosend.php') return false;
    // критерии подозрительности
    if (stripos($lower, 'javascript:') === 0) return true;
    if (stripos($lower, 'data:') === 0) return true;
    if (preg_match('~^https?://~i', $lower)) return true;
    if (stripos($lower, 'mailto:') === 0) return true;
    if (stripos($lower, '<?php') !== false) return true;
    if (stripos($lower, 'eval(') !== false) return true;
    if (stripos($lower, 'base64') !== false || stripos($lower, 'atob(') !== false) return true;
    return false;
}
function lineNumberAtPos(string $src, int $pos): int {
    return substr_count(substr($src, 0, $pos), "\n") + 1;
}
function snippetAround(string $src, int $pos, int $lenBefore = 60, int $lenAfter = 160): string {
    $start = max(0, $pos - $lenBefore);
    return substr($src, $start, $lenBefore + $lenAfter) ?: '';
}

// --- подготовка результатов ---
$report = [
    '_meta' => [
        'script_dir' => __DIR__,
        'root' => $root,
        'generated_at' => date('c'),
        'forceReplace' => $forceReplace,
    ],
    'modified_files' => [], // куда будем писать отчёт об изменениях
];

// --- обход папок (SPL) ---
if (!is_dir($root)) {
    // лог и страница ошибки
    $err = "Ошибка: папка для сканирования не найдена: $root";
    file_put_contents($logFile, json_encode(['time'=>date('c'),'error'=>$err], JSON_UNESCAPED_UNICODE) . PHP_EOL, FILE_APPEND | LOCK_EX);
    echo "<p>" . htmlspecialchars($err, ENT_QUOTES | ENT_SUBSTITUTE) . "</p>";
    exit(1);
}

$rii = new RecursiveIteratorIterator(new RecursiveDirectoryIterator($root, RecursiveDirectoryIterator::SKIP_DOTS));

foreach ($rii as $file) {
    if (!$file->isFile()) continue;
    if (strtolower($file->getFilename()) !== 'index.php') continue;

    $path = $file->getPathname();
    $src = @file_get_contents($path);
    if ($src === false) {
        // не читается — логнем и пропустим
        file_put_contents($logFile, json_encode(['time'=>date('c'),'warning'=>"Не удалось прочитать $path"], JSON_UNESCAPED_UNICODE) . PHP_EOL, FILE_APPEND | LOCK_EX);
        continue;
    }

    // найдем все открывающие теги <form ...>
    if (!preg_match_all('/<form\b[^>]*>/i', $src, $forms, PREG_OFFSET_CAPTURE)) {
        continue;
    }

    $replacements = []; // список изменений: each => ['pos','len','old','new']
    $reportItems = [];  // данные для отчёта (строка, oldAction, newAction, snippet)
    $lastPos = 0;

    foreach ($forms[0] as $fm) {
        $tagText = $fm[0];
        $pos = $fm[1];

        // извлечь action если есть
        $action = null;
        if (preg_match('/\baction\s*=\s*(["\'])(.*?)\1/i', $tagText, $m)) {
            $action = $m[2];
        } elseif (preg_match('/\baction\s*=\s*([^\s>]+)/i', $tagText, $m)) {
            $action = $m[1];
        }

        // если нет action — пропускаем (по условию)
        if ($action === null) continue;
        $actTrim = trim($action);
        if ($actTrim === '' || $actTrim === '#' || strtolower($actTrim) === 'tosend.php') continue;

        // решаем заменять или нет
        $shouldReplace = $forceReplace ? true : isSuspiciousAction($action);
        if (!$shouldReplace) continue;

        // сформируем новый тег: если есть action — заменим значение, иначе вставим action before '>'
        if (preg_match('/\baction\s*=\s*(["\'])(.*?)\1/i', $tagText, $m, PREG_OFFSET_CAPTURE)) {
            // заменить значение внутри кавычек
            $quote = $m[1][0];
            // постройка нового тега: заменить только ту часть
            $startRel = $m[0][1];
            $lenRel = strlen($m[0][0]);
            $newActionAttr = 'action=' . $quote . 'tosend.php' . $quote;
            // заменяем в $tagText
            $newTag = substr($tagText, 0, $startRel) . $newActionAttr . substr($tagText, $startRel + $lenRel);
        } else {
            // action без кавычек (маловероятно) или нет action — мы знаем что action существует в variable, но обработим добавление безопасно
            // вставим перед закрывающим '>'
            $insert = ' action="tosend.php"';
            $posClose = strrpos($tagText, '>');
            if ($posClose === false) $posClose = strlen($tagText);
            $newTag = substr($tagText, 0, $posClose) . $insert . substr($tagText, $posClose);
        }

        // запомним замену
        $replacements[] = [
            'pos' => $pos,
            'len' => strlen($tagText),
            'old' => $tagText,
            'new' => $newTag,
            'line' => lineNumberAtPos($src, $pos),
            'oldAction' => $action,
            'newAction' => 'tosend.php',
            'snippet' => snippetAround($src, $pos),
        ];
    }

    if (empty($replacements)) {
        continue; // ничего менять не нужно в этом файле
    }

    // backup original file
    $backupName = dirname($path) . '/index_backup_' . date('Ymd_His') . '.php';
    if (!@copy($path, $backupName)) {
        // логируем, но пытаемся продолжить
        file_put_contents($logFile, json_encode(['time'=>date('c'),'warning'=>"Не удалось сделать бэкап $path -> $backupName"], JSON_UNESCAPED_UNICODE) . PHP_EOL, FILE_APPEND | LOCK_EX);
    }

    // Build new source using replacements in-order (offsets increasing)
    // sort replacements by pos asc just in case
    usort($replacements, function($a,$b){ return $a['pos'] <=> $b['pos']; });

    $newSrcParts = [];
    $cursor = 0;
    foreach ($replacements as $r) {
        $start = $r['pos'];
        $len = $r['len'];
        // append chunk before tag
        $newSrcParts[] = substr($src, $cursor, $start - $cursor);
        // append replaced tag
        $newSrcParts[] = $r['new'];
        $cursor = $start + $len;
    }
    // tail
    $newSrcParts[] = substr($src, $cursor);
    $newSrc = implode('', $newSrcParts);

    // write new file (atomic-ish)
    $tmp = $path . '.tmp.' . bin2hex(random_bytes(6));
    $w = @file_put_contents($tmp, $newSrc, LOCK_EX);
    if ($w === false) {
        file_put_contents($logFile, json_encode(['time'=>date('c'),'error'=>"Не удалось записать временный файл $tmp"], JSON_UNESCAPED_UNICODE) . PHP_EOL, FILE_APPEND | LOCK_EX);
        // skip overwriting original
        continue;
    }
    // replace atomically
    if (!@rename($tmp, $path)) {
        // попытка через copy+unlink
        if (!@copy($tmp, $path) || !@unlink($tmp)) {
            file_put_contents($logFile, json_encode(['time'=>date('c'),'error'=>"Не удалось заменить $path"], JSON_UNESCAPED_UNICODE) . PHP_EOL, FILE_APPEND | LOCK_EX);
            continue;
        }
    }

    // добавим информацию в отчёт
    $reportItem = [
        'path' => $path,
        'backup' => file_exists($backupName) ? $backupName : null,
        'changes' => array_map(function($x){
            return [
                'line' => $x['line'],
                'old_action' => $x['oldAction'],
                'new_action' => $x['newAction'],
                'snippet' => $x['snippet'],
            ];
        }, $replacements),
    ];
    $report['modified_files'][] = $reportItem;

    // логируем успешную замену
    file_put_contents($logFile, json_encode(['time'=>date('c'),'info'=>"Replaced in $path",'backup'=>$backupName,'changes'=>count($replacements)], JSON_UNESCAPED_UNICODE) . PHP_EOL, FILE_APPEND | LOCK_EX);
}

// сохраняем общий report.json рядом со скриптом (перезапись)
file_put_contents($reportFile, json_encode($report, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE), LOCK_EX);

// --- простой HTML-вывод ---
?><!doctype html>
<html lang="ru">
<head><meta charset="utf-8"><title>Replace FORM actions → tosend.php</title></head>
<body>
<h1>Замена action → tosend.php</h1>
<p>Корень сканирования: <code><?php echo htmlspecialchars($root, ENT_QUOTES | ENT_SUBSTITUTE) ?></code></p>
<p>Режим: <?php echo $forceReplace ? '<b>force — все action (кроме пустых/#/tosend.php)</b>' : 'только <b>подозрительные</b> action'; ?></p>
<?php if (empty($report['modified_files'])): ?>
    <p>Изменений не произведено.</p>
<?php else: ?>
    <h2>Изменённые файлы</h2>
    <ul>
    <?php foreach ($report['modified_files'] as $mf): ?>
        <li>
            <strong><?php echo htmlspecialchars($mf['path'], ENT_QUOTES | ENT_SUBSTITUTE) ?></strong>
            <?php if ($mf['backup']): ?>
                — бэкап: <code><?php echo htmlspecialchars($mf['backup'], ENT_QUOTES | ENT_SUBSTITUTE) ?></code>
            <?php endif; ?>
            <ul>
            <?php foreach ($mf['changes'] as $ch): ?>
                <li>строка <?php echo intval($ch['line']) ?>: <code><?php echo htmlspecialchars($ch['old_action'], ENT_QUOTES | ENT_SUBSTITUTE) ?></code> → <code><?php echo htmlspecialchars($ch['new_action'], ENT_QUOTES | ENT_SUBSTITUTE) ?></code><div style="font-family:monospace;background:#eee;padding:6px;margin-top:4px"><?php echo htmlspecialchars($ch['snippet'], ENT_QUOTES | ENT_SUBSTITUTE) ?></div></li>
            <?php endforeach; ?>
            </ul>
        </li>
    <?php endforeach; ?>
    </ul>
<?php endif; ?>

<hr>
<p>Лог: <code><?php echo htmlspecialchars($logFile, ENT_QUOTES | ENT_SUBSTITUTE) ?></code></p>
<p>Отчёт: <code><?php echo htmlspecialchars($reportFile, ENT_QUOTES | ENT_SUBSTITUTE) ?></code></p>
</body>
</html>
