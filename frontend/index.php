<?php require 'config.php'; ?>
<!DOCTYPE html>
<html lang="nl">
<head>
<meta charset="UTF-8">
<title>BMN Teletekst Spelletjes</title>
<style>
body { font-family: sans-serif; max-width: 480px; margin: 60px auto; text-align: center; }
button { font-size: 1.2em; padding: 12px 32px; cursor: pointer; }
</style>
</head>
<body>
<h1>Bel in en speel Minesweeper</h1>
<p>Zet je teletekst-ontvanger straks op de pagina die je krijgt toegewezen.</p>
<button id="bel">Bel</button>
<p id="status"></p>
<script>
const API = "<?= $API_BASE ?>";
document.getElementById('bel').addEventListener('click', async () => {
    const statusEl = document.getElementById('status');
    statusEl.textContent = 'Verbinden...';
    try {
        const res = await fetch(API + '/call', {method: 'POST'});
        const data = await res.json();
        if (data.error) {
            statusEl.textContent = data.error;
            return;
        }
        window.location = 'play.php?session=' + encodeURIComponent(data.session_id) + '&page=' + encodeURIComponent(data.page);
    } catch (e) {
        statusEl.textContent = 'Kan geen verbinding maken met de spelserver.';
    }
});
</script>
</body>
</html>
