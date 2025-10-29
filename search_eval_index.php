

<?php
// scan_index_eval_in_svg_img.php
// Рекурсивно ищет JS eval(...) в <img> и <svg> внутри файлов index.php.
// Ничего не меняет — только читает. Сохраняет report.json в ../report.json

$root = '../';
$reportFile = 'report.json';

// --- Утилиты ---
function lineNumberAtPos(string $src, int $pos): int {
    return substr_count(substr($src, 0, $pos), "\n") + 1;
}

function snippetAround(string $src, int $pos, int $lenBefore = 40, int $lenAfter = 120): string {
    $start = max(0, $pos - $lenBefore);
    return substr($src, $start, $lenBefore + $lenAfter) ?: '';
}

// Защита от бесконечного рекурсивного чтения (например, если $root указывает на корень FS)
if (!is_dir($root)) {
    echo "Ошибка: папка для сканирования не найдена: $root\n";
    exit(1);
}

// --- Сканирование ---
$rii = new RecursiveIteratorIterator(new RecursiveDirectoryIterator($root, RecursiveDirectoryIterator::SKIP_DOTS));
$results = [];

foreach ($rii as $file) {
    if (!$file->isFile()) continue;
    if (strtolower($file->getFilename()) !== 'index.php') continue;

    $path = $file->getPathname();
    $src = @file_get_contents($path);
    if ($src === false) continue;

    $found = [];

    // 1) eval в <img ...> (например onload="eval(...)")
    if (preg_match_all('/<img\b[^>]*\beval\s*\(/i', $src, $m, PREG_OFFSET_CAPTURE)) {
        foreach ($m[0] as $occ) {
            $pos = $occ[1];
            $found[] = [
                'tag' => 'img',
                'line' => lineNumberAtPos($src, $pos),
                'snippet' => snippetAround($src, $pos),
            ];
        }
    }

    // 2) eval в встроенных <svg>...</svg>
    if (preg_match_all('/<svg\b[\s\S]*?<\/svg>/i', $src, $svgs, PREG_OFFSET_CAPTURE)) {
        foreach ($svgs[0] as $svg) {
            $fragment = $svg[0];
            $pos = $svg[1];
            if (stripos($fragment, 'eval(') !== false) {
                $found[] = [
                    'tag' => 'svg',
                    'line' => lineNumberAtPos($src, $pos),
                    'snippet' => snippetAround($src, $pos),
                ];
            }
        }
    }

    // 3) eval в инлайновых data:image/svg+xml или data URI в атрибутах (хорошая эвристика)
    // поиск "data:image/svg" поблизости и eval внутри
    if (preg_match_all('/data:image\/svg\+xml[^"\'>]*["\'][^"\']{0,200}eval\s*\(/i', $src, $dMatches, PREG_OFFSET_CAPTURE)) {
        foreach ($dMatches[0] as $occ) {
            $pos = $occ[1];
            $found[] = [
                'tag' => 'data-svg',
                'line' => lineNumberAtPos($src, $pos),
                'snippet' => snippetAround($src, $pos),
            ];
        }
    }

    if (!empty($found)) {
        $results[$path] = $found;
    }
}

// Сохраняем отчёт (попытаемся создать папку если нужно)
$dir = dirname($reportFile);
if (!is_dir($dir)) @mkdir($dir, 0777, true);
@file_put_contents($reportFile, json_encode($results, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE));

// --- Вывод для CLI ---
if (php_sapi_name() === 'cli') {
    if (empty($results)) {
        echo "Ничего не найдено (eval в <img>/<svg> в index.php).\n";
    } else {
        echo "Найдены файлы с eval в <img>/<svg> (сканирование $root):\n";
        foreach ($results as $file => $items) {
            echo " - $file\n";
            foreach ($items as $it) {
                $s = preg_replace("/\s+/", ' ', trim($it['snippet']));
                echo "    * {$it['tag']} (строка {$it['line']}): ..." . mb_substr($s, 0, 200) . "...\n";
            }
        }
    }
    echo "Отчёт записан в: $reportFile\n";
    exit;
}

// --- HTML вывод ---
?><!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<title>Scan index.php — eval в IMG/SVG</title>
<style>
body{font-family:system-ui,Arial,sans-serif;margin:20px}
.card{border:1px solid #ddd;padding:12px;margin:10px 0;border-radius:6px;background:#fff}
.snip{font-family:monospace;background:#f7f7f7;padding:6px;white-space:pre-wrap;margin-top:6px}
.empty{color:#666}
</style>
</head>
<body>
<h1>Поиск JS <code>eval(</code> в &lt;img&gt; / &lt;svg&gt; внутри файлов <code>index.php</code></h1>

<?php if (empty($results)): ?>
    <p class="empty">Ничего не найдено.</p>
<?php else: ?>
    <p>Найдено файлов: <?php echo count($results); ?>. Отчёт: <code><?php echo htmlspecialchars($reportFile, ENT_QUOTES | ENT_SUBSTITUTE); ?></code></p>
    <?php foreach ($results as $path => $items): ?>
        <div class="card">
            <strong><?php echo htmlspecialchars($path, ENT_QUOTES | ENT_SUBSTITUTE); ?></strong>
            <?php foreach ($items as $it): ?>
                <div style="margin-top:8px">
                    <div><b><?php echo strtoupper(htmlspecialchars($it['tag'])); ?></b> — строка <?php echo intval($it['line']); ?></div>
                    <div class="snip"><?php echo htmlspecialchars($it['snippet'], ENT_QUOTES | ENT_SUBSTITUTE); ?></div>
                </div>
            <?php endforeach; ?>
        </div>
    <?php endforeach; ?>
<?php endif; ?>

<hr>
<p>Отчёт сохранён в <code><?php echo htmlspecialchars($reportFile, ENT_QUOTES | ENT_SUBSTITUTE); ?></code></p>
</body>
</html>
