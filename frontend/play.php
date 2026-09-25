<?php
require 'config.php';
$session = $_GET['session'] ?? '';
$page = $_GET['page'] ?? '';
if ($session === '') {
    header('Location: index.php');
    exit;
}
?>
<!DOCTYPE html>
<html lang="nl">
<head>
<meta charset="UTF-8">
<title>Minesweeper - pagina <?= htmlspecialchars($page) ?></title>
<style>
body { font-family: sans-serif; max-width: 520px; margin: 20px auto; text-align: center; }
h1 { font-size: 1.4em; }
#grid { display: inline-grid; grid-template-columns: repeat(13, 28px); gap: 2px; margin-top: 12px; }
#grid button { width: 28px; height: 28px; padding: 0; font-size: 0.8em; }
.flagged { background: #ffd54f; }
.revealed { background: #ddd; }
.mine { background: #e57373; }
#status { font-weight: bold; min-height: 1.4em; }
</style>
</head>
<body>
<h1>Je teletekst-pagina: <?= htmlspecialchars($page) ?></h1>
<p>Zet je ontvanger op pagina <?= htmlspecialchars($page) ?> om mee te kijken.</p>
<p id="status"></p>
<label><input type="checkbox" id="flagmode"> Vlagmodus</label>
<div id="grid"></div>
<p><button id="hangup">Ophangen</button></p>
<script>
const API = "<?= $API_BASE ?>";
const session = "<?= htmlspecialchars($session, ENT_QUOTES) ?>";
const grid = document.getElementById('grid');
const statusEl = document.getElementById('status');
const flagmode = document.getElementById('flagmode');
let cells = [];
let over = false;

function buildGrid(w, h) {
    grid.style.gridTemplateColumns = `repeat(${w}, 28px)`;
    grid.innerHTML = '';
    cells = [];
    for (let y = 0; y < h; y++) {
        const row = [];
        for (let x = 0; x < w; x++) {
            const btn = document.createElement('button');
            btn.addEventListener('click', () => makeMove(x, y));
            grid.appendChild(btn);
            row.push(btn);
        }
        cells.push(row);
    }
}

async function makeMove(x, y) {
    if (over) return;
    const action = flagmode.checked ? 'flag' : 'reveal';
    const res = await fetch(`${API}/game/${session}/${action}`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({x, y})
    });
    render(await res.json());
}

function render(data) {
    if (data.error) {
        statusEl.textContent = data.error;
        return;
    }
    if (cells.length === 0) {
        buildGrid(data.width, data.height);
    }
    for (let y = 0; y < data.height; y++) {
        for (let x = 0; x < data.width; x++) {
            const c = data.board[y][x];
            const btn = cells[y][x];
            btn.className = '';
            btn.textContent = '';
            if (c.state === 'revealed') {
                if (c.mine) {
                    btn.classList.add('mine');
                    btn.textContent = '*';
                } else {
                    btn.classList.add('revealed');
                    btn.textContent = c.value > 0 ? c.value : '';
                }
            } else if (c.state === 'flagged') {
                btn.classList.add('flagged');
                btn.textContent = '⚑';
            }
        }
    }
    if (data.status === 'won') {
        statusEl.textContent = 'Gewonnen!';
        over = true;
    } else if (data.status === 'lost') {
        statusEl.textContent = 'Helaas, een mijn geraakt.';
        over = true;
    } else {
        statusEl.textContent = `Nog ${data.mine_count - data.flagged_count} mijn(en) te markeren`;
    }
}

async function refresh() {
    const res = await fetch(`${API}/game/${session}`);
    render(await res.json());
}

document.getElementById('hangup').addEventListener('click', async () => {
    await fetch(`${API}/game/${session}/hangup`, {method: 'POST'});
    window.location = 'index.php';
});

refresh();
setInterval(refresh, 4000);
</script>
</body>
</html>
