async function fetchConfig() {
  const res = await fetch("/config");
  if (!res.ok) {
    throw new Error("Falha ao carregar /config");
  }
  return await res.json();
}

function buildCard(cam) {
  const card = document.createElement("div");
  card.className = "card cam-card";
  card.dataset.camId = cam.id;
  card.innerHTML = `
    <div class="card-title">${cam.label}</div>
    <div class="video-container">
      <img data-cam="${cam.id}" src="/video_feed/${cam.id}" alt="Stream ${cam.label}">
    </div>
    <div class="stats">
      <span class="stat">FPS: <b id="fps-${cam.id}">0</b></span>
      <span class="stat">Status: <b id="status-${cam.id}">Conectando...</b></span>
    </div>
    <div class="labels" id="labels-${cam.id}">Labels: <b>Sem dados</b></div>
    <div class="crop-box">
      <div class="crop-title">Último recorte</div>
      <img id="crop-${cam.id}" class="crop-img" alt="Recorte ${cam.label}" />
    </div>
  `;
  return card;
}

function updateLabels(camId, cam) {
  const labelsEl = document.getElementById("labels-" + camId);
  if (!labelsEl) return;
  const labels = cam.labels || {};
  const order = cam.label_order || [];
  let items = [];
  if (order.length > 0) {
    for (const name of order) {
      const val = labels[name];
      if (val !== undefined) items.push(`${name}: ${val}`);
    }
    for (const [k, v] of Object.entries(labels)) {
      if (!order.includes(k)) items.push(`${k}: ${v}`);
    }
  } else {
    items = Object.entries(labels).map(([k, v]) => `${k}: ${v}`);
  }
  labelsEl.innerHTML =
    items.length > 0
      ? "Labels: <b>" + items.join(" | ") + "</b>"
      : "Labels: <b>Sem dados</b>";
}

async function updateStats(cams) {
  try {
    const res = await fetch("/metrics");
    if (!res.ok) throw new Error();
    const data = await res.json();
    for (const cam of cams) {
      const camId = cam.id;
      const stat = data[camId];
      if (!stat) continue;
      const fpsEl = document.getElementById("fps-" + camId);
      const statusEl = document.getElementById("status-" + camId);
      if (fpsEl) fpsEl.textContent = stat.fps.toFixed(1);
      if (statusEl) statusEl.textContent = stat.status === "online" ? "Online" : "Offline";
      updateLabels(camId, stat);
    }
  } catch {
    for (const cam of cams) {
      const statusEl = document.getElementById("status-" + cam.id);
      if (statusEl) statusEl.textContent = "Offline";
    }
  }
}

function attachSwapHandlers() {
  const mainSlot = document.getElementById("main-slot");
  const thumbGrid = document.getElementById("thumb-grid");

  function setMainCard(card) {
    if (!card) return;
    const currentMain = mainSlot.firstElementChild;
    if (currentMain === card) return;
    if (currentMain) {
      thumbGrid.prepend(currentMain);
    }
    mainSlot.appendChild(card);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  const firstCard = thumbGrid.querySelector(".cam-card");
  setMainCard(firstCard);

  thumbGrid.addEventListener("click", (e) => {
    const card = e.target.closest(".cam-card");
    if (card) setMainCard(card);
  });

  mainSlot.addEventListener("click", (e) => {
    const card = e.target.closest(".cam-card");
    if (!card) return;
    thumbGrid.prepend(card);
    setMainCard(thumbGrid.querySelector(".cam-card"));
  });
}

async function updateCrops(cams) {
  try {
    const res = await fetch("/crops");
    if (!res.ok) return;
    const data = await res.json();
    const items = data.items || [];
    for (const cam of cams) {
      const item = items.find((it) => it.stream === cam.id);
      if (!item) continue;
      const img = document.getElementById("crop-" + cam.id);
      if (!img) continue;
      img.src = item.path + "?t=" + Math.floor(item.ts * 1000);
      img.style.display = "block";
    }
  } catch {}
}

async function boot() {
  const cfg = await fetchConfig();
  const cams = cfg.cameras || [];
  const grid = document.getElementById("thumb-grid");
  for (const cam of cams) {
    grid.appendChild(buildCard(cam));
  }
  attachSwapHandlers();
  setInterval(() => updateStats(cams), 1000);
  setInterval(() => updateCrops(cams), 1500);
}

boot().catch((err) => {
  const grid = document.getElementById("thumb-grid");
  grid.innerHTML = `<div class="card">Erro ao carregar configuração: ${err}</div>`;
});
