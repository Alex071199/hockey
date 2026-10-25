<?php
// РФ-прокси для prime (1win): бэкенд и зрители ходят через этот хостинг,
// потому что 1win/CDN пускают только чистые российские IP.
// Загружается на бесплатный PHP-хостинг (beget и т.п.) в корень сайта.

$TOKEN = '6fab792217480cf00bd8eb6c09082217';

header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Methods: GET, OPTIONS');
header('Access-Control-Allow-Headers: *');
if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') {
    http_response_code(204);
    exit;
}

if (!hash_equals($TOKEN, (string)($_GET['t'] ?? ''))) {
    http_response_code(403);
    exit('forbidden');
}

$url = (string)($_GET['url'] ?? '');
if ($url === '') {
    http_response_code(400);
    exit('missing url');
}

$parts = parse_url($url);
if (!$parts || empty($parts['host']) || !in_array($parts['scheme'] ?? '', ['http', 'https'], true)) {
    http_response_code(400);
    exit('bad url');
}

$host = strtolower($parts['host']);
if ($host === 'localhost' || preg_match(
    '/^(127\.|192\.168\.|169\.254\.|10\.|172\.(1[6-9]|2[0-9]|3[0-1])\.)/',
    $host
)) {
    http_response_code(403);
    exit('private address');
}

$headers = [
    'User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    'Referer: https://1wixpv.life/',
    'Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language: ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
    'Upgrade-Insecure-Requests: 1',
];

if (function_exists('curl_init')) {
    $ch = curl_init($url);
    curl_setopt_array($ch, [
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_FOLLOWLOCATION => true,
        CURLOPT_CONNECTTIMEOUT => 10,
        CURLOPT_TIMEOUT => 30,
        CURLOPT_HTTPHEADER => $headers,
    ]);
    $body = curl_exec($ch);
    $code = (int)curl_getinfo($ch, CURLINFO_HTTP_CODE);
    $ctype = curl_getinfo($ch, CURLINFO_CONTENT_TYPE);
    $err = curl_error($ch);
    curl_close($ch);
    if ($body === false) {
        http_response_code(502);
        exit('upstream error: ' . $err);
    }
} else {
    $ctx = stream_context_create(['http' => [
        'method' => 'GET',
        'header' => implode("\r\n", $headers),
        'timeout' => 30,
        'follow_location' => 1,
        'ignore_errors' => true,
    ]]);
    $body = file_get_contents($url, false, $ctx);
    $code = 200;
    $ctype = 'application/octet-stream';
    foreach ($http_response_header ?? [] as $h) {
        if (preg_match('#^HTTP/\S+\s+(\d+)#', $h, $m)) { $code = (int)$m[1]; }
        if (stripos($h, 'Content-Type:') === 0) { $ctype = trim(substr($h, 13)); }
    }
    if ($body === false) {
        http_response_code(502);
        exit('upstream error');
    }
}

if ($ctype) {
    header('Content-Type: ' . $ctype);
}
header('Content-Length: ' . strlen($body));
http_response_code($code ?: 200);
echo $body;
