/* ATKO: operator chat oynasi */
(function () {
  const $ = (id) => document.getElementById(id);
  const esc = ATKO.esc;
  const layout = $("chat-layout");
  const STATUS = {
    new: "🆕 Yangi", contacted: "📞 Aloqada", thinking: "🤔 O'ylab ko'radi", trial: "🎓 Bepul darsga yozildi",
    accepted: "✅ Kursga qabul qilindi", rejected: "❌ Rad etdi",
  };
  const REJECT = ["Narx qimmat", "Vaqt to'g'ri kelmadi", "Boshqa markazni tanladi", "Qiziqmay qoldi", "Aloqaga chiqmadi", "Boshqa"];

  let tab = "queue", current = null, data = null, templates = [], pendingFile = null, recorder = null, recChunks = [];

  // ------------------------------------------------ ro'yxat
  document.querySelectorAll("#chat-tabs button").forEach((b) => (b.onclick = () => {
    document.querySelectorAll("#chat-tabs button").forEach((x) => x.classList.remove("active"));
    b.classList.add("active"); tab = b.dataset.tab; loadList();
  }));
  let qTimer;
  $("chat-q").oninput = () => { clearTimeout(qTimer); qTimer = setTimeout(loadList, 300); };

  async function loadList() {
    try {
      const j = await ATKO.api(`/api/chats?tab=${tab}&q=${encodeURIComponent($("chat-q").value)}`);
      ["queue", "mine", "active"].forEach((k) => { const el = $("cnt-" + k); el.textContent = j.counts[k]; el.classList.toggle("hot", k === "queue" && j.counts[k] > 0); });
      const box = $("chat-items");
      if (!j.items.length) { box.innerHTML = `<div class="empty">${tab === "queue" ? "Navbat bo'sh 🎉" : "Chatlar yo'q"}</div>`; return; }
      box.innerHTML = j.items.map((c) => {
        const lock = c.operator ? (c.operator_id === ATKO.me ? `<span class="pill pill-active">Siz</span>` : `<span class="lock">🔒 ${esc(c.operator)} suhbatlashmoqda</span>`) : "";
        const temp = c.temperature === "hot" ? "🔥" : c.temperature === "warm" ? "🌤" : c.temperature === "cold" ? "❄️" : "";
        return `<a class="chat-item ${c.id === current ? "sel" : ""}" data-id="${c.id}" href="/chats/${c.id}">
          <div class="row1"><span class="name">${temp} ${esc(c.lead_name)}</span><span class="time">${esc(c.requested)}</span></div>
          <div class="last">${esc(c.last)}</div>
          <div class="meta"><span class="pill pill-${c.status}">${esc(c.reason)}</span>${c.off_hours ? '<span class="pill">🌙 ish vaqtidan tashqari</span>' : ""}${lock}${c.unread && c.operator_id === ATKO.me ? `<span class="unread">${c.unread}</span>` : ""}</div></a>`;
      }).join("");
      box.querySelectorAll(".chat-item").forEach((a) => (a.onclick = (e) => { e.preventDefault(); openChat(Number(a.dataset.id)); }));
    } catch (e) { ATKO.toast(e.message, "danger"); }
  }

  // ------------------------------------------------ chat
  async function openChat(id, keepScroll) {
    current = id;
    history.replaceState(null, "", `/chats/${id}`);
    layout.classList.add("has-chat");
    document.querySelectorAll(".chat-item").forEach((a) => a.classList.toggle("sel", Number(a.dataset.id) === id));
    try { data = await ATKO.api(`/api/chats/${id}`); } catch (e) { ATKO.toast(e.message, "danger"); return; }
    $("conv-empty").hidden = true; $("conv-body").hidden = false;
    renderHead(); renderMessages(keepScroll); renderPanel();
  }
  $("back-btn").onclick = () => { layout.classList.remove("has-chat"); current = null; history.replaceState(null, "", "/chats"); };

  function renderHead() {
    const c = data.chat, l = data.lead;
    $("h-name").textContent = l.name;
    $("h-sub").innerHTML = [l.phone ? `📱 <a href="tel:${esc(l.phone)}">${esc(l.phone)}</a>` : "📱 telefon yo'q",
      l.username ? `<a href="https://t.me/${esc(l.username)}" target="_blank">@${esc(l.username)}</a>` : "",
      `<span class="pill pill-${c.status}">${{ waiting: "⏳ Navbatda", active: "💬 Faol", closed: "🔒 Yopilgan" }[c.status]}</span>`,
      l.blocked ? '<span class="pill pill-danger">⛔ Botni bloklagan</span>' : ""].filter(Boolean).join(" · ");
    const acts = [];
    if (c.status === "waiting") acts.push(`<button class="btn btn-success" id="a-claim">✋ Menga ochdim</button>`);
    if (c.status === "active" && (data.is_mine || ATKO.isAdmin)) {
      acts.push(`<button class="btn btn-sm btn-ghost" id="a-transfer">🔁 O'tkazish</button>`);
      acts.push(`<button class="btn btn-sm btn-danger" id="a-close">🔒 Chatni yopish</button>`);
    }
    acts.push(`<button class="btn btn-sm btn-ghost" id="a-panel" title="Lead kartasi">👤</button>`);
    $("h-actions").innerHTML = acts.join("");
    const b = $("banner");
    b.className = "lock-banner"; b.hidden = false;
    if (c.status === "waiting") b.textContent = "⏳ Lead operatorni kutmoqda. Suhbatni boshlash uchun «Menga ochdim» tugmasini bosing.";
    else if (c.status === "active" && data.is_mine) { b.classList.add("mine"); b.textContent = "✅ Bu chat sizda. AI bu lead uchun vaqtincha o'chirilgan."; }
    else if (c.status === "active") b.textContent = `🔒 Bu chat bilan ${c.operator} suhbatlashmoqda` + (ATKO.isAdmin ? " (admin sifatida yozishingiz mumkin)" : "");
    else { b.classList.add("closed"); b.textContent = "🔒 Chat yopilgan. Lead qayta murojaat qilsa, yangi chat navbatga tushadi."; }
    $("composer").hidden = !data.can_write;
    if ($("a-claim")) $("a-claim").onclick = claim;
    if ($("a-close")) $("a-close").onclick = closeChat;
    if ($("a-transfer")) $("a-transfer").onclick = openTransfer;
    $("a-panel").onclick = () => $("lead-panel").classList.toggle("show");
  }

  function fileHtml(m) {
    if (!m.file_url) return "";
    const u = esc(m.file_url);
    if (m.kind === "photo") return `<img src="${u}" alt="rasm" loading="lazy">`;
    if (m.kind === "voice" || m.kind === "audio" || (m.mime || "").startsWith("audio/")) return `<audio controls preload="none" src="${u}"></audio>`;
    if (m.kind === "video" || m.kind === "video_note") return `<video controls preload="metadata" src="${u}"></video>`;
    return `<a class="file" href="${u}" target="_blank" download>📎 ${esc(m.file_name || "fayl")}</a>`;
  }
  const WHO = { lead: "Mijoz", ai: "🤖 AI", operator: "Operator", bot: "🤖 Bot", system: "" };
  function msgHtml(m) {
    if (m.sender === "system") return `<div class="msg system" data-id="${m.id}">ℹ️ ${esc(m.text)}<span class="time">${m.time}</span></div>`;
    const who = m.sender === "operator" ? `👨‍💼 ${esc(m.staff || "Operator")}` : m.sender === "lead" ? esc(data ? data.lead.name : "Mijoz") : WHO[m.sender] || m.sender;
    const tr = m.transcript ? `<div class="transcript">📝 ${esc(m.transcript)}</div>` : (m.kind === "voice" ? `<div class="transcript" data-tr="${m.id}" hidden></div>` : "");
    const action = m.sender === "lead" && m.text && /^(🔘|📱 Kontakt|\/)/.test(m.text) ? " action" : "";
    return `<div class="msg ${m.sender}${action}" data-id="${m.id}"><div class="who">${who}${action ? ' <span class="act-tag">tugma</span>' : ""}</div>${fileHtml(m)}${m.text ? `<div class="text">${esc(m.text)}</div>` : ""}${tr}<div class="time">${m.time}</div></div>`;
  }
  function renderMessages() {
    let last = "", html = "";
    data.messages.forEach((m) => { if (m.date !== last) { html += `<div class="day-sep">${m.date}</div>`; last = m.date; } html += msgHtml(m); });
    $("msgs").innerHTML = html || '<div class="empty">Xabarlar yo\'q</div>';
    scrollDown();
  }
  function scrollDown() { const box = $("msgs"); setTimeout(() => (box.scrollTop = box.scrollHeight), 30); }
  function appendMessage(m) {
    if (!data || m.lead_id !== data.lead.id) return;
    if (document.querySelector(`.msg[data-id="${m.id}"]`)) return;
    data.messages.push(m);
    const box = $("msgs");
    const near = box.scrollHeight - box.scrollTop - box.clientHeight < 200;
    box.insertAdjacentHTML("beforeend", msgHtml(m));
    if (near || m.sender !== "lead") scrollDown();
  }
  $("msgs").addEventListener("click", (e) => {
    if (e.target.tagName === "IMG") {
      const lb = document.createElement("div"); lb.className = "lightbox"; lb.innerHTML = `<img src="${e.target.src}">`;
      lb.onclick = () => lb.remove(); document.body.appendChild(lb);
    }
  });

  // ------------------------------------------------ lead paneli
  function renderPanel() {
    const l = data.lead;
    const opts = Object.entries(STATUS).map(([k, v]) => `<option value="${k}" ${k === l.status ? "selected" : ""}>${v}</option>`).join("");
    const rej = REJECT.map((r) => `<option ${r === l.reject_reason ? "selected" : ""}>${r}</option>`).join("");
    $("lead-panel").innerHTML = `
      <div class="card-head" style="margin-bottom:6px"><h3 style="margin:0">👤 ${esc(l.name)}</h3><a class="btn btn-sm btn-ghost" href="/leads/${l.id}" target="_blank">Karta ↗</a></div>
      <dl class="kv">
        <dt>Telefon</dt><dd>${l.phone ? `<a href="tel:${esc(l.phone)}">${esc(l.phone)}</a>` : "—"}</dd>
        <dt>Telegram</dt><dd>${l.username ? "@" + esc(l.username) : l.tg_id}</dd>
        <dt>Til</dt><dd>${l.lang === "ru" ? "🇷🇺 Rus" : "🇺🇿 O'zbek"}</dd>
        <dt>Maqsad</dt><dd>${esc(l.goal || "—")}</dd>
        <dt>Format</dt><dd>${esc(l.format || "—")}</dd>
        <dt>Daraja</dt><dd>${esc(l.level || "—")}</dd>
        <dt>Shahar</dt><dd>${esc(l.city || "—")}</dd>
        <dt>Tarif</dt><dd>${esc(l.tariff || "—")}</dd>
        <dt>Manba</dt><dd>${esc(l.source || "To'g'ridan-to'g'ri")}</dd>
        <dt>Qiziqish</dt><dd>${esc(l.temperature || "—")}</dd>
        <dt>Bepul dars</dt><dd>${l.trial ? "🎁 So'ragan" : "—"}</dd>
        <dt>Ro'yxatdan</dt><dd>${esc(l.created)}</dd>
      </dl>
      <h3>📌 Status</h3>
      <div class="field"><select id="p-status">${opts}</select></div>
      <div class="field" id="p-reason-wrap" ${l.status === "rejected" ? "" : "hidden"}><select id="p-reason"><option value="">— Rad etish sababi —</option>${rej}</select></div>
      <button class="btn btn-sm" id="p-status-save">Saqlash</button>
      <h3>🤖 AI xulosa <button class="btn btn-sm btn-ghost" id="p-sum" style="float:right">↻</button></h3>
      <div class="summary-box" id="p-summary">${esc(l.summary || "Xulosa hali tayyor emas")}</div>
      <h3>💬 Izohlar (xulosa)</h3>
      <div class="field"><textarea id="p-comment" placeholder="Lead bo'yicha xulosangiz..."></textarea></div>
      <button class="btn btn-sm" id="p-comment-save">Qo'shish</button>
      <div id="p-comments" style="margin-top:10px">${data.comments.map(commentHtml).join("") || '<div class="muted">Izohlar yo\'q</div>'}</div>
      <h3>🕘 Murojaatlar tarixi</h3>
      ${data.history.map((h) => `<div class="comment"><b>#${h.id}</b> ${esc(h.status)} · ${esc(h.operator)}<small>${esc(h.time)}${h.rating ? " · " + "⭐".repeat(h.rating) : ""}${h.comment ? " · «" + esc(h.comment) + "»" : ""}</small></div>`).join("")}`;
    $("p-status").onchange = () => ($("p-reason-wrap").hidden = $("p-status").value !== "rejected");
    $("p-status-save").onclick = async () => {
      try {
        const st = $("p-status").value;
        await ATKO.api(`/api/leads/${l.id}/status`, { status: st, reason: st === "rejected" ? $("p-reason").value : "" });
        ATKO.toast("Status saqlandi: " + STATUS[st], "success"); data.lead.status = st;
      } catch (e) { ATKO.toast(e.message, "danger"); }
    };
    $("p-comment-save").onclick = async () => {
      const t = $("p-comment").value.trim(); if (!t) return;
      try { await ATKO.api(`/api/leads/${l.id}/comments`, { text: t }); $("p-comment").value = ""; } catch (e) { ATKO.toast(e.message, "danger"); }
    };
    $("p-sum").onclick = async () => {
      $("p-summary").textContent = "⏳ Tayyorlanmoqda...";
      try { const j = await ATKO.api(`/api/chats/${current}/summary`, {}); $("p-summary").textContent = j.summary || "—"; }
      catch (e) { $("p-summary").textContent = e.message; }
    };
  }
  function commentHtml(c) { return `<div class="comment">${esc(c.text)}<small>${esc(c.staff)} · ${esc(c.time)}</small></div>`; }

  // ------------------------------------------------ harakatlar
  async function claim() {
    try { await ATKO.api(`/api/chats/${current}/claim`, {}); ATKO.toast("✅ Chat sizga biriktirildi", "success"); await openChat(current); loadList(); $("msg-input").focus(); }
    catch (e) { ATKO.toast(e.message, "danger"); openChat(current); loadList(); }
  }
  async function closeChat() {
    if (!confirm("Chatni yopasizmi? Leadga «Chat yopildi» xabari va baholash so'rovi yuboriladi.")) return;
    try { await ATKO.api(`/api/chats/${current}/close`, {}); ATKO.toast("Chat yopildi", "success"); await openChat(current); loadList(); }
    catch (e) { ATKO.toast(e.message, "danger"); }
  }
  async function openTransfer() {
    const j = await ATKO.api("/api/staff/available");
    $("transfer-select").innerHTML = j.items.filter((s) => s.id !== data.chat.operator_id)
      .map((s) => `<option value="${s.id}" ${s.load >= s.max ? "disabled" : ""}>${s.online ? "🟢" : "⚪"} ${esc(s.name)} (${esc(s.display)}) — ${s.load}/${s.max}</option>`).join("");
    $("transfer-modal").hidden = false;
  }
  $("transfer-ok").onclick = async () => {
    try { await ATKO.api(`/api/chats/${current}/transfer`, { to_staff_id: $("transfer-select").value }); $("transfer-modal").hidden = true; ATKO.toast("Chat o'tkazildi", "success"); openChat(current); loadList(); }
    catch (e) { ATKO.toast(e.message, "danger"); }
  };

  // ------------------------------------------------ yuborish
  async function send() {
    const input = $("msg-input"), text = input.value.trim();
    if (!text && !pendingFile) return;
    $("send-btn").disabled = true;
    try {
      if (pendingFile) {
        const fd = new FormData(); fd.append("file", pendingFile.file, pendingFile.name); fd.append("caption", text); fd.append("as_voice", pendingFile.voice ? "true" : "false");
        await ATKO.api(`/api/chats/${current}/upload`, fd); clearFile();
      } else await ATKO.api(`/api/chats/${current}/send`, { text });
      input.value = "";
    } catch (e) { ATKO.toast(e.message, "danger"); }
    $("send-btn").disabled = false; input.focus();
  }
  $("send-btn").onclick = send;
  $("msg-input").onkeydown = (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } };
  function setFile(file, name, voice) {
    pendingFile = { file, name, voice };
    $("attach-preview").hidden = false;
    $("attach-preview").innerHTML = `${voice ? "🎙" : "📎"} ${esc(name)} (${(file.size / 1024 / 1024).toFixed(2)} MB) <button class="btn btn-sm btn-ghost" id="clear-file">✕</button>`;
    $("clear-file").onclick = clearFile;
  }
  function clearFile() { pendingFile = null; $("attach-preview").hidden = true; $("file-input").value = ""; }
  $("file-input").onchange = () => { const f = $("file-input").files[0]; if (f) setFile(f, f.name, false); };

  $("rec-btn").onclick = async () => {
    if (recorder && recorder.state === "recording") { recorder.stop(); return; }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mime = ["audio/ogg;codecs=opus", "audio/webm;codecs=opus", "audio/webm"].find((m) => window.MediaRecorder && MediaRecorder.isTypeSupported(m)) || "";
      recorder = new MediaRecorder(stream, mime ? { mimeType: mime } : {});
      recChunks = [];
      recorder.ondataavailable = (e) => e.data.size && recChunks.push(e.data);
      recorder.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        const type = recorder.mimeType || "audio/webm";
        const blob = new Blob(recChunks, { type });
        setFile(blob, "ovozli_xabar." + (type.includes("ogg") ? "ogg" : "webm"), true);
        $("rec-btn").textContent = "🎙 Ovoz"; $("rec-status").innerHTML = "";
      };
      recorder.start();
      $("rec-btn").textContent = "⏹ To'xtatish"; $("rec-status").innerHTML = '<span class="rec">● Yozilmoqda...</span>';
    } catch (e) { ATKO.toast("Mikrofonga ruxsat berilmadi", "danger"); }
  };

  async function loadTemplates() {
    try {
      templates = (await ATKO.api("/api/templates")).items;
      $("tpl-select").innerHTML = '<option value="">🧩 Shablonlar</option>' + templates.map((t) => `<option value="${t.id}">${esc(t.title)}</option>`).join("");
    } catch (e) {}
  }
  $("tpl-select").onchange = () => {
    const t = templates.find((x) => String(x.id) === $("tpl-select").value);
    if (t) { $("msg-input").value = data && data.lead.lang === "ru" ? t.ru : t.uz; $("msg-input").focus(); }
    $("tpl-select").value = "";
  };
  $("ai-btn").onclick = async () => {
    $("ai-btn").disabled = true; $("ai-btn").textContent = "⏳ AI...";
    try { const j = await ATKO.api(`/api/chats/${current}/suggest`, {}); $("msg-input").value = j.text; $("msg-input").focus(); }
    catch (e) { ATKO.toast(e.message, "danger"); }
    $("ai-btn").disabled = false; $("ai-btn").textContent = "🤖 AI taklif";
  };

  // ------------------------------------------------ real vaqt
  ATKO.on("message", (m) => {
    appendMessage(m);
    if (m.sender === "lead" && m.operator_id === ATKO.me && (m.chat_id !== current || document.hidden)) {
      ATKO.notify("💬 Yangi xabar", (m.text || m.kind || "").slice(0, 80), `/chats/${m.chat_id}`, "new");
    }
    loadList();
  });
  ATKO.on("transcript", (t) => {
    const el = document.querySelector(`[data-tr="${t.id}"]`);
    if (el) { el.hidden = false; el.textContent = "📝 " + t.transcript; }
    if (data) { const m = data.messages.find((x) => x.id === t.id); if (m) m.transcript = t.transcript; }
  });
  ["chat_new", "chat_claimed", "chat_closed", "chat_transferred"].forEach((ev) => ATKO.on(ev, (c) => {
    loadList();
    if (current && c.id === current) openChat(current, true);
  }));
  ATKO.on("chat_rated", (r) => { if (r.chat_id === current) openChat(current, true); });
  ATKO.on("lead_summary", (s) => { if (data && s.lead_id === data.lead.id && $("p-summary")) $("p-summary").textContent = s.summary || ""; });
  ATKO.on("lead_comment", (c) => {
    if (data && c.lead_id === data.lead.id && $("p-comments")) {
      const box = $("p-comments"); if (!box.querySelector(".comment")) box.innerHTML = "";
      box.insertAdjacentHTML("afterbegin", commentHtml(c));
    }
  });
  ATKO.on("lead_updated", (u) => { if (data && u.lead_id === data.lead.id && !u.status) openChat(current, true); });

  ATKO.on("poll", () => { loadList(); if (current) openChat(current, true); });

  loadTemplates();
  loadList();
  setInterval(loadList, 60000);
  if (layout.dataset.open) openChat(Number(layout.dataset.open));
})();
