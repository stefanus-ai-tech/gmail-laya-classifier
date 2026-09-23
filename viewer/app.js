"use strict";

const $ = (selector) => document.querySelector(selector);
const state = { messages: [], selectedId: null, sourceName: "" };
const labels = { billing: "Billing", technical: "Teknis", sales: "Sales", security: "Keamanan", hr: "HR", other: "Lainnya" };

function textElement(tag, value, className = "") {
  const node = document.createElement(tag);
  node.textContent = value == null ? "" : String(value);
  if (className) node.className = className;
  return node;
}

function probability(value) {
  const number = Number(value);
  return Number.isFinite(number) ? Math.round(Math.max(0, Math.min(1, number)) * 100) + "%" : "—";
}

function isLikely(value) {
  return value !== null && value !== undefined && Number(value) >= 0.5;
}

function dateFor(message) {
  const timestamp = Number(message.received_at_ms);
  return Number.isFinite(timestamp) && timestamp > 0 ? new Date(timestamp) : null;
}

function shortDate(message) {
  const date = dateFor(message);
  return date ? new Intl.DateTimeFormat("id-ID", { day: "numeric", month: "short" }).format(date) : "—";
}

function fullDate(message) {
  const date = dateFor(message);
  return date ? new Intl.DateTimeFormat("id-ID", { dateStyle: "medium", timeStyle: "short" }).format(date) : "—";
}

function displayCategory(value) {
  return labels[value] || (value ? String(value) : "Tanpa kategori");
}

function validateData(data) {
  if (!data || !Array.isArray(data.messages)) throw new Error("Format JSON tidak cocok. Perlu objek dengan daftar 'messages'.");
  for (const item of data.messages) {
    if (!item || typeof item !== "object" || !item.classification || typeof item.classification !== "object") {
      throw new Error("Ada pesan tanpa data 'classification'.");
    }
  }
  return data;
}

function showNotice(message) { $("#notice").textContent = message || ""; }

function loadData(data, name) {
  validateData(data);
  state.messages = data.messages;
  state.selectedId = null;
  state.sourceName = name;
  $("#source-name").textContent = name;
  const generated = data.generated_at ? new Date(data.generated_at) : null;
  const generatedText = generated && !Number.isNaN(generated.getTime())
    ? new Intl.DateTimeFormat("id-ID", { dateStyle: "medium", timeStyle: "short" }).format(generated)
    : "waktu tidak tersedia";
  $("#source-meta").textContent = `${data.messages.length} email · dibuat ${generatedText} · filter: ${data.query || "—"}`;
  $("#stat-total").textContent = data.messages.length;
  $("#stat-reply").textContent = data.messages.filter((m) => isLikely(m.classification.needs_reply)).length;
  $("#stat-spam").textContent = data.messages.filter((m) => isLikely(m.classification.is_spam)).length;
  $("#stat-phishing").textContent = data.messages.filter((m) => isLikely(m.classification.is_phishing)).length;
  $("#search-input").value = "";
  $("#sort-select").value = "newest";
  populateCategories();
  showNotice("");
  render();
}

function populateCategories() {
  const filter = $("#category-filter");
  filter.replaceChildren(new Option("Semua kategori", "all"));
  const categories = [...new Set(state.messages.map((m) => m.classification.category).filter(Boolean))]
    .sort((a, b) => displayCategory(a).localeCompare(displayCategory(b), "id"));
  for (const category of categories) filter.add(new Option(displayCategory(category), category));
}

function filteredMessages() {
  const query = $("#search-input").value.trim().toLocaleLowerCase("id-ID");
  const category = $("#category-filter").value;
  const sort = $("#sort-select").value;
  const result = state.messages.filter((message) => {
    if (category !== "all" && message.classification.category !== category) return false;
    if (!query) return true;
    return [message.sender, message.subject, message.snippet, message.body]
      .some((part) => String(part || "").toLocaleLowerCase("id-ID").includes(query));
  });
  result.sort((a, b) => {
    if (sort === "confidence") return (Number(b.classification.confidence) || 0) - (Number(a.classification.confidence) || 0);
    const delta = (dateFor(b)?.getTime() || 0) - (dateFor(a)?.getTime() || 0);
    return sort === "oldest" ? -delta : delta;
  });
  return result;
}

function makeChip(label, kind) { return textElement("span", label, `chip ${kind}`); }

function renderList(messages) {
  const list = $("#message-list");
  const fragment = document.createDocumentFragment();
  for (const message of messages) {
    const row = document.createElement("button");
    row.type = "button";
    row.className = `message-row${message.id === state.selectedId ? " active" : ""}`;
    row.setAttribute("aria-label", `Buka email ${message.subject || "tanpa subjek"}`);
    row.addEventListener("click", () => { state.selectedId = message.id; render(); });

    const main = textElement("div", "", "message-main");
    const top = textElement("div", "", "message-top");
    top.append(textElement("span", message.subject || "(Tanpa subjek)", "message-subject"),
      textElement("span", shortDate(message), "message-date"));
    main.append(top, textElement("span", message.sender || "Pengirim tidak diketahui", "message-sender"),
      textElement("span", message.snippet || message.body || "Tidak ada pratinjau", "message-snippet"));
    const badges = textElement("div", "", "message-badges");
    badges.append(makeChip(displayCategory(message.classification.category), "category"));
    if (isLikely(message.classification.is_phishing)) badges.append(makeChip("Phishing?", "risk"));
    else if (isLikely(message.classification.is_spam)) badges.append(makeChip("Spam?", "risk"));
    if (isLikely(message.classification.needs_reply)) badges.append(makeChip("Balas", "reply"));
    row.append(main, badges);
    fragment.append(row);
  }
  list.replaceChildren(fragment);
  $("#empty-state h3").textContent = state.messages.length ? "Tidak ada yang cocok" : "Belum ada email ditampilkan";
  $("#empty-state p").textContent = state.messages.length
    ? "Coba kata kunci atau kategori lain."
    : "Buka file JSON hasil klasifikasi untuk mulai melihat pesan.";
}

function detailMetric(name, value) {
  const box = textElement("div", "", "detail-metric");
  box.append(textElement("span", name), textElement("strong", value));
  return box;
}

function detailSection(title, content) {
  const section = textElement("section", "", "detail-section");
  section.append(textElement("h4", title), content);
  return section;
}

function renderDetail(message) {
  const panel = $("#detail-panel");
  if (!message) {
    const placeholder = textElement("div", "", "detail-placeholder");
    placeholder.append(textElement("span", "✉"), textElement("h3", "Pilih satu email"),
      textElement("p", "Detail pesan dan hasil Laya akan muncul di sini."));
    panel.replaceChildren(placeholder);
    return;
  }
  const c = message.classification;
  const content = textElement("div", "", "detail-content");
  const meta = textElement("div", "", "detail-meta");
  const sender = textElement("span", "Dari: ");
  sender.append(textElement("strong", message.sender || "—"));
  const date = textElement("span", "Diterima: ");
  date.append(textElement("strong", fullDate(message)));
  meta.append(sender, date);
  content.append(textElement("p", "DETAIL EMAIL", "detail-kicker"),
    textElement("h3", message.subject || "(Tanpa subjek)"), meta);
  const grid = textElement("div", "", "detail-grid");
  grid.append(
    detailMetric("Kategori", displayCategory(c.category)),
    detailMetric("Keyakinan", probability(c.confidence)),
    detailMetric("Potensi spam", probability(c.is_spam)),
    detailMetric("Potensi phishing", probability(c.is_phishing)),
    detailMetric("Perlu balasan", probability(c.needs_reply)),
    detailMetric("Urgensi", c.urgency == null ? "—" : `${Number(c.urgency).toFixed(1)} / 2`)
  );
  content.append(detailSection("HASIL LAYA", grid));
  content.append(detailSection("ISI EMAIL", textElement("p", message.body || message.snippet || "Tidak ada isi teks.", "body-text")));
  content.append(textElement("p", `Model: ${c.routing?.model || "—"}. Persentase adalah estimasi model, bukan kepastian.`, "detail-hint"));
  panel.replaceChildren(content);
}

function render() {
  const messages = filteredMessages();
  $("#visible-count").textContent = `${messages.length} pesan`;
  if (!messages.some((m) => m.id === state.selectedId)) state.selectedId = messages[0]?.id || null;
  renderList(messages);
  renderDetail(messages.find((m) => m.id === state.selectedId));
}

async function loadFiles(files) {
  if (!files?.length) return;
  try {
    const parsed = await Promise.all(Array.from(files, async (file) => ({
      name: file.name, data: validateData(JSON.parse(await file.text()))
    })));
    const unique = new Map();
    for (const { data } of parsed) {
      for (const message of data.messages) unique.set(message.id || `${unique.size}`, message);
    }
    const latest = parsed.reduce((value, item) => {
      const date = Date.parse(item.data.generated_at || "") || 0;
      return date > value ? date : value;
    }, 0);
    loadData({
      messages: [...unique.values()],
      generated_at: latest ? new Date(latest).toISOString() : null,
      query: parsed.length === 1 ? parsed[0].data.query : `${parsed.length} file digabung`
    }, parsed.length === 1 ? parsed[0].name : `${parsed.length} file JSON`);
    $("#reload-button").hidden = true;
  } catch (error) {
    showNotice(`Gagal membuka file: ${error.message}`);
  }
}

async function loadDefault() {
  if (location.protocol === "file:") return;
  try {
    const response = await fetch("../data/classifications.json", { cache: "no-store" });
    if (!response.ok) return;
    loadData(await response.json(), "data/classifications.json");
    $("#reload-button").hidden = false;
  } catch (_) {
    // The file picker remains available when the default file is absent.
  }
}

$("#file-input").addEventListener("change", (event) => loadFiles(event.target.files));
$("#search-input").addEventListener("input", render);
$("#category-filter").addEventListener("change", render);
$("#sort-select").addEventListener("change", render);
$("#reload-button").addEventListener("click", loadDefault);
loadDefault();
