/* ATKO panel: WebSocket, bildirishnomalar, ovozli signal, toastlar */
(function () {
  const handlers = {};
  const ATKO = (window.ATKO = {
    me: Number(document.body.dataset.me || 0),
    isAdmin: document.body.dataset.role === "admin",
    on(evt, fn) { (handlers[evt] = handlers[evt] || []).push(fn); },
    emit(evt, data) { (handlers[evt] || []).forEach((fn) => { try { fn(data); } catch (e) { console.error(e); } }); },
  });

  // ---------------- API yordamchisi
  ATKO.api = async function (url, data, method) {
    const opts = { method: method || (data ? "POST" : "GET"), headers: {} };
    if (data instanceof FormData) opts.body = data;
    else if (data) { const fd = new FormData(); Object.entries(data).forEach(([k, v]) => fd.append(k, v)); opts.body = fd; }
    const r = await fetch(url, opts);
    if (r.status === 401) { location.href = "/login"; throw new Error("auth"); }
    let j = {};
    try { j = await r.json(); } catch (e) { j = { ok: r.ok }; }
    if (!r.ok || j.ok === false) throw new Error(j.error || "Xatolik yuz berdi");
    return j;
  };
  ATKO.setWaiting = (n) => document.querySelectorAll(".nav-waiting").forEach((b) => { b.hidden = !n; b.textContent = n; });

  // ---------------- mobil menyu (yon panel) va jadvallarni kartochkaga aylantirish
  const sidebar = document.getElementById("sidebar"), backdrop = document.getElementById("backdrop");
  function menu(open) {
    if (!sidebar) return;
    sidebar.classList.toggle("open", open);
    if (backdrop) backdrop.hidden = !open;
    document.body.classList.toggle("menu-open", open);
  }
  ["menu-btn", "menu-btn2"].forEach((id) => { const b = document.getElementById(id); if (b) b.onclick = () => menu(!sidebar.classList.contains("open")); });
  if (backdrop) backdrop.onclick = () => menu(false);
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") menu(false); });
  if (sidebar) sidebar.querySelectorAll("a").forEach((a) => a.addEventListener("click", () => menu(false)));
  ATKO.cardify = function (root) {
    // telefonda jadval qatorlari kartochka bo'lib ko'rinadi: har katakka ustun nomi yoziladi (CSS: data-label)
    (root || document).querySelectorAll(".table-wrap > table:not(.no-cards)").forEach((t) => {
      const head = t.querySelector("tr");
      if (!head || !head.querySelector("th")) return;
      const labels = [...head.children].map((th) => th.textContent.trim());
      if (labels.length < 3) return;
      t.classList.add("cards");
      t.querySelectorAll("tr").forEach((tr) => {
        if (tr === head) { tr.classList.add("head"); return; }
        let i = 0;
        [...tr.children].forEach((td) => {
          if (!td.hasAttribute("data-label") && labels[i]) td.setAttribute("data-label", labels[i]);
          if (td.childNodes.length > 1 && !td.querySelector(":scope > .cv")) {
            const w = document.createElement("div"); w.className = "cv";
            while (td.firstChild) w.appendChild(td.firstChild);
            td.appendChild(w);
          }
          if (td.colSpan > 1) td.classList.add("span");
          i += td.colSpan || 1;
        });
      });
    });
  };
  ATKO.cardify();
  document.body.addEventListener("htmx:afterSwap", (e) => ATKO.cardify(e.target));
  ATKO.esc = (s) => (s == null ? "" : String(s)).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  // ---------------- toastlar
  ATKO.toast = function (text, level, onClick) {
    const box = document.getElementById("toasts");
    if (!box) return;
    const el = document.createElement("div");
    el.className = "toast " + (level || "");
    el.textContent = text;
    el.onclick = () => { el.remove(); onClick && onClick(); };
    box.appendChild(el);
    setTimeout(() => el.remove(), level === "danger" ? 15000 : 7000);
  };

  // ---------------- ovozli signal (WebAudio — fayl kerak emas)
  let audioCtx = null;
  ATKO.beep = function (kind) {
    try {
      audioCtx = audioCtx || new (window.AudioContext || window.webkitAudioContext)();
      const notes = kind === "alert" ? [880, 660, 880] : [660, 990];
      notes.forEach((f, i) => {
        const o = audioCtx.createOscillator(), g = audioCtx.createGain();
        o.type = "sine"; o.frequency.value = f;
        o.connect(g); g.connect(audioCtx.destination);
        const t = audioCtx.currentTime + i * 0.18;
        g.gain.setValueAtTime(0.0001, t);
        g.gain.exponentialRampToValueAtTime(0.25, t + 0.02);
        g.gain.exponentialRampToValueAtTime(0.0001, t + 0.16);
        o.start(t); o.stop(t + 0.17);
      });
    } catch (e) { /* ovoz bloklangan */ }
  };
  document.addEventListener("click", () => { try { audioCtx = audioCtx || new (window.AudioContext || window.webkitAudioContext)(); audioCtx.resume(); } catch (e) {} }, { once: true });

  // ---------------- brauzer bildirishnomalari
  const nb = document.getElementById("notif-btn");
  function refreshNotifBtn() {
    if (!nb || !("Notification" in window)) return;
    nb.hidden = Notification.permission === "granted" || Notification.permission === "denied";
  }
  if (nb) nb.onclick = () => Notification.requestPermission().then(refreshNotifBtn);
  refreshNotifBtn();
  ATKO.notify = function (title, body, url, kind) {
    ATKO.beep(kind);
    if ("Notification" in window && Notification.permission === "granted" && (document.hidden || !document.hasFocus())) {
      const n = new Notification(title, { body, tag: url || title, requireInteraction: kind === "alert" });
      n.onclick = () => { window.focus(); if (url) location.href = url; n.close(); };
    }
  };

  // ---------------- onlayn holati
  const ot = document.getElementById("online-toggle");
  if (ot) ot.onchange = async () => {
    try {
      await ATKO.api("/api/me/online", { online: ot.checked });
      document.getElementById("online-label").textContent = ot.checked ? "Onlayn" : "Oflayn";
    } catch (e) { ot.checked = !ot.checked; ATKO.toast(e.message, "danger"); }
  };

  // ---------------- hisoblagichlar
  async function refreshCounters() {
    try {
      const c = await ATKO.api("/api/me/counters");
      ATKO.setWaiting(c.waiting);
      document.title = (c.waiting ? `(${c.waiting}) ` : "") + document.title.replace(/^\(\d+\)\s*/, "");
    } catch (e) {}
  }
  ATKO.refreshCounters = refreshCounters;

  // ---------------- WebSocket
  let ws, retry = 1000;
  function connect() {
    if (!ATKO.me) return;
    ws = new WebSocket((location.protocol === "https:" ? "wss://" : "ws://") + location.host + "/ws");
    ws.onopen = () => { retry = 1000; ATKO.wsConnected = true; refreshCounters(); };
    ws.onmessage = (e) => {
      let m; try { m = JSON.parse(e.data); } catch (_) { return; }
      ATKO.emit(m.event, m.data);
      ATKO.emit("*", m);
    };
    ws.onclose = (e) => {
      ATKO.wsConnected = false;
      if (e.code === 4401 || e.code === 4403) { location.href = "/login"; return; }
      setTimeout(connect, retry); retry = Math.min(retry * 2, 15000);
    };
  }
  setInterval(() => { try { ws && ws.readyState === 1 && ws.send("ping"); } catch (e) {} }, 25000);
  connect();

  // ---------------- global hodisalar
  ATKO.on("chat_new", (c) => {
    refreshCounters();
    ATKO.notify("🔔 Yangi murojaat", `${c.lead_name} · ${c.reason}`, `/chats/${c.id}`, "new");
    ATKO.toast(`🔔 Yangi murojaat: ${c.lead_name} (${c.reason})`, "", () => (location.href = `/chats/${c.id}`));
  });
  ATKO.on("chat_claimed", refreshCounters);
  ATKO.on("chat_closed", refreshCounters);
  ATKO.on("chat_transferred", (c) => {
    refreshCounters();
    if (c.operator_id === ATKO.me) {
      ATKO.notify("🔁 Sizga chat o'tkazildi", c.lead_name, `/chats/${c.id}`, "new");
      ATKO.toast(`🔁 Sizga chat o'tkazildi: ${c.lead_name}`, "success", () => (location.href = `/chats/${c.id}`));
    }
  });
  ATKO.on("alert", (a) => {
    ATKO.toast(a.text, a.level, a.chat_id ? () => (location.href = `/chats/${a.chat_id}`) : null);
    if (a.level === "danger" || a.level === "warning") ATKO.notify("⚠️ ATKO", a.text, a.chat_id ? `/chats/${a.chat_id}` : null, "alert");
  });
  ATKO.on("message", (m) => {
    if (m.sender === "lead" && m.chat_id && m.operator_id === ATKO.me && !location.pathname.startsWith("/chats")) {
      ATKO.notify("💬 Yangi xabar", (m.text || m.kind || "").slice(0, 80), `/chats/${m.chat_id}`, "new");
    }
  });
  refreshCounters();
  // tizim holati belgisi (admin uchun)
  async function refreshHealth() {
    if (!ATKO.isAdmin) return;
    try { const j = await ATKO.api("/api/system/brief"); const b = document.getElementById("nav-health"); if (b) b.hidden = !j.fails; } catch (e) {}
  }
  refreshHealth(); setInterval(refreshHealth, 120000);
  // WebSocket ishlamasa (masalan, proksi to'sib qo'ysa) — har 20 soniyada yangilab turamiz
  let lastWaiting = null;
  setInterval(async () => {
    if (ATKO.wsConnected) return;
    try {
      const c = await ATKO.api("/api/me/counters");
      if (lastWaiting !== null && c.waiting > lastWaiting) ATKO.notify("🔔 Yangi murojaat", "Navbatda " + c.waiting + " ta murojaat", "/chats", "new");
      lastWaiting = c.waiting;
      ATKO.setWaiting(c.waiting);
      ATKO.emit("poll", c);
    } catch (e) {}
  }, 20000);
})();
