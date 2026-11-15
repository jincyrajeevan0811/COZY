/* COZY dashboard interactions */
(function () {
  "use strict";
  const $ = (s, c = document) => c.querySelector(s);
  const $$ = (s, c = document) => Array.from(c.querySelectorAll(s));

  // Sidebar toggle (mobile)
  const sidebar = $(".dash-sidebar"), backdrop = $(".sidebar-backdrop");
  $$("[data-sidebar-toggle]").forEach((b) => b.addEventListener("click", () => { sidebar.classList.toggle("open"); backdrop.classList.toggle("show"); }));
  backdrop && backdrop.addEventListener("click", () => { sidebar.classList.remove("open"); backdrop.classList.remove("show"); });

  // Toasts from Django messages
  $$(".toast[data-autoshow]").forEach((el) => new bootstrap.Toast(el, { delay: 5000 }).show());

  // Confirmation dialogs (uses a Bootstrap modal, falls back to confirm())
  const confirmModal = $("#confirmModal");
  document.addEventListener("submit", (e) => {
    const form = e.target;
    if (!form.matches("[data-confirm]") || form.dataset.confirmed) return;
    e.preventDefault();
    if (!confirmModal) { if (window.confirm(form.dataset.confirm)) { form.dataset.confirmed = "1"; form.submit(); } return; }
    $(".confirm-text", confirmModal).textContent = form.dataset.confirm;
    const modal = bootstrap.Modal.getOrCreateInstance(confirmModal);
    const ok = $(".confirm-ok", confirmModal);
    const handler = () => { form.dataset.confirmed = "1"; modal.hide(); form.submit(); };
    ok.onclick = handler;
    modal.show();
  });

  // Image previews for file inputs
  $$("input[type=file][accept*=image]").forEach((input) => {
    input.addEventListener("change", () => {
      let grid = input.parentElement.querySelector(".preview-grid");
      if (!grid) { grid = document.createElement("div"); grid.className = "preview-grid"; input.insertAdjacentElement("afterend", grid); }
      grid.innerHTML = "";
      Array.from(input.files).slice(0, 12).forEach((f) => {
        const img = document.createElement("img");
        img.src = URL.createObjectURL(f);
        img.onload = () => URL.revokeObjectURL(img.src);
        grid.appendChild(img);
      });
    });
  });

  // Select-all checkboxes for bulk actions
  $$("[data-select-all]").forEach((master) => master.addEventListener("change", () => {
    $$(master.dataset.selectAll).forEach((cb) => (cb.checked = master.checked));
  }));

  // Dynamic formset rows ("Add another")
  $$("[data-formset-add]").forEach((btn) => btn.addEventListener("click", () => {
    const prefix = btn.dataset.formsetAdd;
    const total = $(`#id_${prefix}-TOTAL_FORMS`);
    const tpl = $(`#${prefix}-empty`);
    const target = $(`#${prefix}-rows`);
    if (!total || !tpl || !target) return;
    const idx = parseInt(total.value, 10);
    const html = tpl.innerHTML.replace(/__prefix__/g, idx);
    target.insertAdjacentHTML("beforeend", html);
    total.value = idx + 1;
  }));

  // Subcategory filtering by selected category on product form
  const cat = $("#id_category"), sub = $("#id_subcategory");
  if (cat && sub && sub.dataset.map) {
    const map = JSON.parse(sub.dataset.map);
    const sync = () => {
      Array.from(sub.options).forEach((o) => { if (!o.value) return; o.hidden = String(map[o.value]) !== cat.value; });
      if (sub.selectedOptions[0] && sub.selectedOptions[0].hidden) sub.value = "";
    };
    cat.addEventListener("change", sync); sync();
  }

  // Auto-slug helper
  const title = $("#id_title") || $("#id_name"), slug = $("#id_slug");
  if (title && slug && !slug.value) {
    title.addEventListener("input", () => {
      if (slug.dataset.touched) return;
      slug.value = title.value.toLowerCase().trim().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
    });
    slug.addEventListener("input", () => (slug.dataset.touched = "1"));
  }

  // Stock adjust modal: fill target action + label
  const adjModal = $("#adjustModal");
  if (adjModal) {
    adjModal.addEventListener("show.bs.modal", (e) => {
      const btn = e.relatedTarget;
      $("form", adjModal).action = btn.dataset.action;
      $(".adj-label", adjModal).textContent = btn.dataset.label;
      $(".adj-current", adjModal).textContent = btn.dataset.current;
      const th = $("[name=low_stock_threshold]", adjModal); if (th) th.value = btn.dataset.threshold;
    });
  }

  // ---------------------------------------------------------------- charts (real data from the API)
  const chartEl = $("#salesChart");
  if (chartEl && window.Chart) {
    const rose = "#B76E79", gold = "#C9A66B", charcoal = "#2E2A28";
    const palette = [rose, gold, "#8FA9B8", "#9DB89A", "#D7A9A0", "#7E6F8E", "#E2C48E", "#5E8C6A", "#C0817A", "#A39486", "#6B8FA3"];
    Chart.defaults.font.family = "Jost, sans-serif";
    Chart.defaults.color = "#8C837D";
    let salesChart, statusChart, catChart, prodChart;
    const fmt = (v) => "₹" + Number(v).toLocaleString("en-IN");
    const load = async (period) => {
      const res = await fetch(`${chartEl.dataset.url}?period=${period}`, { headers: { Accept: "application/json" } });
      const d = await res.json();
      const sales = { labels: d.sales.labels, datasets: [
        { type: "line", label: "Revenue", data: d.sales.revenue, borderColor: rose, backgroundColor: "rgba(183,110,121,.12)", fill: true, tension: .35, yAxisID: "y", pointRadius: 3 },
        { type: "bar", label: "Orders", data: d.sales.orders, backgroundColor: "rgba(201,166,107,.45)", borderRadius: 6, yAxisID: "y1" },
      ] };
      if (salesChart) { salesChart.data = sales; salesChart.update(); }
      else salesChart = new Chart(chartEl, { data: sales, options: { maintainAspectRatio: false, interaction: { mode: "index", intersect: false },
        plugins: { legend: { position: "bottom" }, tooltip: { callbacks: { label: (c) => c.dataset.label === "Revenue" ? ` Revenue: ${fmt(c.raw)}` : ` Orders: ${c.raw}` } } },
        scales: { y: { ticks: { callback: fmt }, grid: { color: "#F1EAE2" } }, y1: { position: "right", grid: { display: false }, ticks: { precision: 0 } }, x: { grid: { display: false } } } } });
      if (!statusChart && $("#statusChart")) statusChart = new Chart($("#statusChart"), { type: "doughnut", data: { labels: d.status.labels, datasets: [{ data: d.status.values, backgroundColor: palette, borderWidth: 0 }] }, options: { maintainAspectRatio: false, cutout: "68%", plugins: { legend: { position: "bottom", labels: { boxWidth: 10 } } } } });
      if (!catChart && $("#categoryChart")) catChart = new Chart($("#categoryChart"), { type: "bar", data: { labels: d.categories.labels, datasets: [{ data: d.categories.values, backgroundColor: rose, borderRadius: 6 }] }, options: { maintainAspectRatio: false, indexAxis: "y", plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => fmt(c.raw) } } }, scales: { x: { ticks: { callback: fmt }, grid: { color: "#F1EAE2" } }, y: { grid: { display: false } } } } });
      if (!prodChart && $("#productChart")) prodChart = new Chart($("#productChart"), { type: "bar", data: { labels: d.products.labels, datasets: [{ data: d.products.values, backgroundColor: gold, borderRadius: 6 }] }, options: { maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { y: { ticks: { precision: 0 }, grid: { color: "#F1EAE2" } }, x: { grid: { display: false } } } } });
    };
    $$(".period-switch .btn").forEach((b) => b.addEventListener("click", () => {
      $$(".period-switch .btn").forEach((x) => x.classList.remove("active"));
      b.classList.add("active");
      load(b.dataset.period);
    }));
    load("daily");
  }
})();
