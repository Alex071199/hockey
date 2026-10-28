// Cloudflare Worker: прокси для player 1win (обход geo-блока).
// Бэкенд (Alwaysdata, FR) → Worker (CF edge) → video-translations.top-parser.com.
// Важно: отдаём байты как есть (м3u8 и HLS-сегменты — бинарные, .text() их ломает).

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    const corsHeaders = {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET, OPTIONS',
      'Access-Control-Allow-Headers': '*',
    };

    if (request.method === 'OPTIONS') {
      return new Response(null, { headers: corsHeaders });
    }

    const targetUrl = url.searchParams.get('url');
    if (!targetUrl) {
      return new Response(JSON.stringify({ error: 'Missing url parameter' }), {
        status: 400,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      });
    }

    try {
      // Заголовки имитируют браузер (Referer 1win — в белом списке)
      const headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
        'Referer': 'https://1wixpv.life/',
        'Accept': '*/*',
        'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
      };
      // пробрасываем Range — для дозагрузки сегментов плеером
      const range = request.headers.get('Range');
      if (range) headers['Range'] = range;

      const response = await fetch(targetUrl, { headers });
      const buf = await response.arrayBuffer();

      const out = {
        'Access-Control-Allow-Origin': '*',
        'Content-Type': response.headers.get('Content-Type') || 'application/octet-stream',
      };
      const cr = response.headers.get('Content-Range');
      if (cr) out['Content-Range'] = cr;
      const len = response.headers.get('Content-Length');
      if (len) out['Content-Length'] = len;

      return new Response(buf, { status: response.status, headers: out });
    } catch (err) {
      return new Response(JSON.stringify({ error: err.message }), {
        status: 502,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      });
    }
  },
};
