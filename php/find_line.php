<?php
// Путь оставляем ровно как ты написал
$baseDir = '../../FB3';

// Что именно ищем в файле
$targetLine = "\$userDataApiKey = 'dxVf6dXj4R6WrXinfdBq';";

// Куда писать лог (рядом со скриптом)
$logFile = __DIR__ . '/userDataApiKey_log.txt';

if (!is_dir($baseDir)) {
    die("Базовая папка {$baseDir} не найдена\n");
}

// ищем все order.php внутри папок ../../FB3/*
$orderFiles = glob($baseDir . '/*/order.php');

if (!$orderFiles) {
    die("Файлы order.php не найдены в {$baseDir}\n");
}

foreach ($orderFiles as $filePath) {
    // читаем файл построчно
    $lines = @file($filePath, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES);
    if ($lines === false) {
        // если не удалось прочитать — логируем ошибку
        $logEntry = sprintf(
            "[%s] Ошибка чтения файла: %s\n",
            date('Y-m-d H:i:s'),
            $filePath
        );
        file_put_contents($logFile, $logEntry, FILE_APPEND);
        continue;
    }

    foreach ($lines as $lineNumber => $line) {
        // можно сравнивать по trim, чтобы не мешали пробелы/табуляция
        if (trim($line) === $targetLine) {
            $logEntry = sprintf(
                "[%s] Найдено в %s (строка %d): %s\n",
                date('Y-m-d H:i:s'),
                $filePath,
                $lineNumber + 1,
                trim($line)
            );
            file_put_contents($logFile, $logEntry, FILE_APPEND);
            // нашли — дальше этот файл не проверяем
            break;
        }
    }
}

echo "Готово, лог: " . $logFile . "\n";
