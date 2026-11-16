/* COZY storefront interactions (vanilla JS, Bootstrap 5) */
(function () {
  "use strict";

  const $ = (sel, ctx = document) => ctx.querySelector(sel);
  const $$ = (sel, ctx = document) => Array.from(ctx.querySelectorAll(sel));

  function getCookie(name) {
    const match = document.cookie.match(new RegExp("(^|;\\s*)" + name + "=([^;]*)"));
    return match ? decodeURIComponent(match[2]) : null;
  }
  const csrftoken = () => getCookie("csrftoken") || ($("[name=csrfmiddlewaretoken]") || {}).value;

  function formatINR(value) {
    const n = Number(value || 0);
    return "₹" + n.toLocaleString("en-IN", { minimumFractionDigits: n % 1 ? 2 : 0, maximumFractionDigits: 2 });
  }

  // ---------------------------------------------------------------- toasts
  function toast(message, type = "success") {
    let container = $("#toastContainer");
    if (!container) return alert(message);
    const icon = { success: "bi-check-circle", danger: "bi-exclamation-circle", error: "bi-exclamation-circle", warning: "bi-exclamation-triangle", info: "bi-info-circle" }[type] || "bi-bell";
    const el = document.createElement("div");
    el.className = `toast toast-cozy ${type}`;
    el.setAttribute("role", "status");
    el.innerHTML = `<div class="toast-body"><i class="bi ${icon} fs-5"></i><div class="flex-grow-1"></div><button type="button" class="btn-close ms-2" data-bs-dismiss="toast" aria-label="Close"></button></div>`;
    el.querySelector(".flex-grow-1").textContent = message;
    container.appendChild(el);
    const t = new bootstrap.Toast(el, { delay: 4000 });
    t.show();
    el.addEventListener("hidden.bs.toast", () => el.remove());
  }
  window.cozyToast = toast;
  $$(".toast[data-autoshow]").forEach((el) => new bootstrap.Toast(el, { delay: 5000 }).show());

  function setCount(selector, value) {
    $$(selector).forEach((el) => { el.textContent = value; el.dataset.count = value; });
  }

  async function postForm(url, data) {
    const res = await fetch(url, {
      method: "POST",
      headers: { "X-CSRFToken": csrftoken(), "X-Requested-With": "XMLHttpRequest", Accept: "application/json" },
      body: data,
      credentials: "same-origin",
    });
    let json = {};
    try { json = await res.json(); } catch (e) { /* non-JSON */ }
    return { ok: res.ok, status: res.status, json };
  }

  // ---------------------------------------------------------------- header
  const header = $(".site-header");
  if (header) {
    window.addEventListener("scroll", () => header.classList.toggle("scrolled", window.scrollY > 10), { passive: true });
  }

  // ---------------------------------------------------------------- search autocomplete
  $$("[data-autocomplete]").forEach((input) => {
    const box = input.parentElement.querySelector(".search-suggest");
    let timer;
    const render = (data) => {
      let html = "";
      if (data.products && data.products.length) {
        html += '<div class="suggest-label">Products</div>';
        data.products.forEach((p) => {
          html += `<a class="suggest-item" href="${p.url}">${p.image ? `<img src="${p.image}" alt="">` : '<img alt="">'}<div><div class="small fw-medium"></div><div class="small text-muted">${formatINR(p.price)}</div></div></a>`;
        });
      }
      if (data.categories && data.categories.length) {
        html += '<div class="suggest-label">Categories</div>';
        data.categories.forEach((c) => { html += `<a class="suggest-item" href="${c.url}"><i class="bi bi-grid"></i><span></span></a>`; });
      }
      if (!html && data.recent && data.recent.length) {
        html += '<div class="suggest-label">Recent searches</div>';
        data.recent.forEach(() => { html += `<a class="suggest-item recent"><i class="bi bi-clock-history"></i><span></span></a>`; });
      }
      if (data.search_url && data.products && data.products.length) html += `<a class="suggest-item justify-content-center small text-rose" href="${data.search_url}">See all results <i class="bi bi-arrow-right"></i></a>`;
      box.innerHTML = html;
      // Fill text safely (no HTML injection from product names)
      const names = $$(".suggest-item .fw-medium", box);
      (data.products || []).forEach((p, i) => { if (names[i]) names[i].textContent = p.name; });
      const cats = $$(".suggest-item .bi-grid + span", box);
      (data.categories || []).forEach((c, i) => { if (cats[i]) cats[i].textContent = c.name; });
      const recents = $$(".suggest-item.recent", box);
      (data.recent || []).forEach((r, i) => {
        if (recents[i]) { recents[i].querySelector("span").textContent = r; recents[i].href = `${input.form.action}?q=${encodeURIComponent(r)}`; }
      });
      box.classList.toggle("show", !!html);
    };
    const run = () => {
      fetch(`${input.dataset.autocomplete}?q=${encodeURIComponent(input.value.trim())}`, { headers: { Accept: "application/json" } })
        .then((r) => r.json()).then(render).catch(() => {});
    };
    input.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(run, 220); });
    input.addEventListener("focus", run);
    document.addEventListener("click", (e) => { if (!input.parentElement.contains(e.target)) box.classList.remove("show"); });
  });

  // ---------------------------------------------------------------- add to cart (AJAX)
  document.addEventListener("submit", async (e) => {
    const form = e.target.closest(".js-add-to-cart");
    if (!form) return;
    const submitter = e.submitter;
    if (submitter && submitter.name === "buy_now") return; // normal POST → checkout
    e.preventDefault();
    const btn = submitter || $("[type=submit]", form);
    if (form.dataset.requiresVariant && !$("[name=variant_id]", form).value) {
      toast("Please select an option first.", "warning");
      return;
    }
    if (btn) { btn.disabled = true; btn.dataset.label = btn.innerHTML; btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span>'; }
    const { ok, json } = await postForm(form.action, new FormData(form));
    if (btn) { btn.disabled = false; btn.innerHTML = btn.dataset.label; }
    if (json.cart_count !== undefined) setCount(".js-cart-count", json.cart_count);
    if (ok && window.cozyOpenMiniCart) {
      const qv = document.getElementById("quickViewModal");
      if (qv && qv.classList.contains("show")) bootstrap.Modal.getInstance(qv).hide();
      window.cozyOpenMiniCart();
    } else {
      toast(json.message || (ok ? "Added to bag" : "Something went wrong"), ok ? "success" : "danger");
    }
  });

  // ---------------------------------------------------------------- wishlist toggle
  document.addEventListener("click", async (e) => {
    const btn = e.target.closest(".js-wishlist");
    if (!btn) return;
    e.preventDefault();
    const { ok, status, json } = await postForm(btn.dataset.url, new FormData());
    if (status === 401 && json.login_url) { window.location.href = json.login_url; return; }
    if (!ok) { toast("Could not update wishlist", "danger"); return; }
    $$(`.js-wishlist[data-url="${btn.dataset.url}"]`).forEach((b) => b.classList.toggle("active", json.added));
    setCount(".js-wishlist-count", json.wishlist_count);
    toast(json.message, "success");
  });

  // ---------------------------------------------------------------- quick view
  const qvModal = $("#quickViewModal");
  document.addEventListener("click", async (e) => {
    const trigger = e.target.closest("[data-quick-view]");
    if (!trigger || !qvModal) return;
    e.preventDefault();
    const body = $(".modal-body", qvModal);
    body.innerHTML = '<div class="p-5 text-center"><span class="spinner-border text-secondary"></span></div>';
    bootstrap.Modal.getOrCreateInstance(qvModal).show();
    const res = await fetch(trigger.dataset.quickView, { headers: { "X-Requested-With": "XMLHttpRequest" } });
    body.innerHTML = await res.text();
    initProductForms(body);
  });

  // ---------------------------------------------------------------- quantity inputs
  document.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-qty]");
    if (!btn) return;
    const wrap = btn.closest(".qty-input");
    const input = $("input", wrap);
    const max = parseInt(input.max || "99", 10);
    const min = parseInt(input.min || "1", 10);
    let v = parseInt(input.value || "1", 10) + (btn.dataset.qty === "+" ? 1 : -1);
    v = Math.max(min, Math.min(max, v));
    input.value = v;
    input.dispatchEvent(new Event("change", { bubbles: true }));
  });
  $$(".js-auto-submit").forEach((input) => input.addEventListener("change", () => input.form.submit()));

  // ---------------------------------------------------------------- product page: gallery, zoom, variants
  function initProductForms(ctx = document) {
    $$(".pd-thumbs button", ctx).forEach((btn) => {
      btn.addEventListener("click", () => {
        const main = $(".pd-main img", btn.closest(".pd-gallery"));
        main.src = btn.dataset.full;
        $$(".pd-thumbs button", btn.closest(".pd-gallery")).forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
      });
    });
    $$(".pd-main", ctx).forEach((main) => {
      const img = $("img", main);
      if (!img) return;
      main.addEventListener("mousemove", (e) => {
        const r = main.getBoundingClientRect();
        img.style.transformOrigin = `${((e.clientX - r.left) / r.width) * 100}% ${((e.clientY - r.top) / r.height) * 100}%`;
      });
      main.addEventListener("mouseenter", () => main.classList.add("zooming"));
      main.addEventListener("mouseleave", () => main.classList.remove("zooming"));
    });
    $$("[data-variants]", ctx).forEach((form) => {
      const variants = JSON.parse(form.dataset.variants || "[]");
      const hidden = $("[name=variant_id]", form);
      const scope = form.closest("[data-product-scope]") || ctx;
      $$("input[name=variant_choice]", form).forEach((radio) => {
        radio.addEventListener("change", () => {
          const v = variants.find((x) => String(x.id) === radio.value);
          if (!v) return;
          hidden.value = v.id;
          const price = $(".js-price", scope), mrp = $(".js-mrp", scope), stock = $(".js-stock", scope), sku = $(".js-sku", scope);
          if (price) price.textContent = formatINR(v.price);
          if (mrp) { mrp.textContent = v.original_price && Number(v.original_price) > Number(v.price) ? formatINR(v.original_price) : ""; }
          if (sku) sku.textContent = v.sku;
          if (stock) {
            stock.className = "stock-pill js-stock " + (v.stock <= 0 ? "out" : v.stock <= 5 ? "low" : "in");
            stock.innerHTML = v.stock <= 0 ? '<i class="bi bi-x-circle"></i> Out of stock' : v.stock <= 5 ? `<i class="bi bi-hourglass-split"></i> Only ${v.stock} left` : '<i class="bi bi-check-circle"></i> In stock';
          }
          const qty = $("[name=quantity]", form);
          if (qty) qty.max = Math.max(1, Math.min(10, v.stock));
          $$("[type=submit]", form).forEach((b) => (b.disabled = v.stock <= 0));
        });
      });
    });
  }
  initProductForms();

  // ---------------------------------------------------------------- pincode check
  $$(".js-pincode-form").forEach((form) => {
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const out = $(".pincode-result", form.parentElement);
      const pin = $("input", form).value.trim();
      const res = await fetch(`${form.action}?pincode=${encodeURIComponent(pin)}`, { headers: { Accept: "application/json" } });
      const data = await res.json();
      out.className = "pincode-result " + (data.serviceable ? "text-success" : "text-danger");
      out.textContent = data.serviceable ? `${data.message} Estimated delivery: ${data.estimate}. ${data.cod ? "COD available." : "Prepaid only."}` : data.message;
    });
  });

  // ---------------------------------------------------------------- newsletter (AJAX)
  $$(".js-newsletter").forEach((form) => {
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const { ok, json } = await postForm(form.action, new FormData(form));
      toast(json.message || "Thank you!", ok ? "success" : "danger");
      if (ok) form.reset();
    });
  });

  // ---------------------------------------------------------------- reveal on scroll
  if ("IntersectionObserver" in window) {
    const io = new IntersectionObserver((entries) => {
      entries.forEach((en) => { if (en.isIntersecting) { en.target.classList.add("visible"); io.unobserve(en.target); } });
    }, { threshold: 0.12 });
    $$(".reveal").forEach((el) => io.observe(el));
  } else {
    $$(".reveal").forEach((el) => el.classList.add("visible"));
  }

  // ---------------------------------------------------------------- copy coupon codes
  document.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-copy]");
    if (!btn) return;
    navigator.clipboard && navigator.clipboard.writeText(btn.dataset.copy).then(() => toast(`Copied ${btn.dataset.copy}`, "success"));
  });

  // ---------------------------------------------------------------- checkout
  const checkout = $("#checkoutForm");
  if (checkout) {
    const newAddr = $("#newAddressFields");
    const syncAddress = () => {
      const sel = $("input[name=address_id]:checked", checkout);
      const isNew = !sel || sel.value === "new";
      if (newAddr) {
        newAddr.classList.toggle("d-none", !isNew);
        $$("input, select, textarea", newAddr).forEach((f) => { if (f.dataset.req === undefined) f.dataset.req = f.required ? "1" : "0"; f.required = isNew && f.dataset.req === "1"; });
      }
    };
    const markSelected = () => $$(".option-card", checkout).forEach((card) => card.classList.toggle("selected", !!$("input:checked", card)));
    const refresh = async () => {
      const params = new URLSearchParams();
      const sm = $("input[name=shipping_method]:checked", checkout); if (sm) params.set("shipping_method", sm.value);
      const pm = $("input[name=payment_method]:checked", checkout); if (pm) params.set("payment_method", pm.value);
      const ad = $("input[name=address_id]:checked", checkout); if (ad) params.set("address_id", ad.value);
      const res = await fetch(`${checkout.dataset.summaryUrl}?${params}`, { headers: { Accept: "application/json" } });
      if (!res.ok) return;
      const d = await res.json();
      ["subtotal", "coupon_discount", "shipping", "gift_wrap_charge", "cod_charge", "tax", "grand_total"].forEach((k) => {
        $$(`[data-sum="${k}"]`).forEach((el) => {
          el.textContent = k === "shipping" && Number(d[k]) === 0 ? "FREE" : (k === "coupon_discount" ? "−" : "") + formatINR(d[k]);
          const row = el.closest("[data-optional]"); if (row) row.classList.toggle("d-none", Number(d[k]) === 0);
        });
      });
      const errBox = $("#checkoutErrors");
      if (errBox) {
        errBox.innerHTML = "";
        (d.errors || []).filter((x) => !/bag is empty/i.test(x)).forEach((msg) => { const li = document.createElement("div"); li.className = "small text-danger mb-1"; li.textContent = "• " + msg; errBox.appendChild(li); });
      }
      const label = $("#placeOrderLabel");
      if (label && pm) label.textContent = pm.value === "cod" ? "Place order" : "Continue to payment";
    };
    checkout.addEventListener("change", (e) => {
      if (e.target.name === "address_id") syncAddress();
      if (["shipping_method", "payment_method", "address_id"].includes(e.target.name)) { markSelected(); refresh(); }
    });
    checkout.addEventListener("submit", () => { const b = $("#placeOrderBtn"); if (b) { b.disabled = true; b.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Processing…'; } });
    syncAddress(); markSelected(); refresh();
  }

  // ---------------------------------------------------------------- mini cart drawer
  const miniCart = $("#miniCart");
  const bagLink = $("[data-mini-cart]");
  if (miniCart && bagLink) {
    window.cozyOpenMiniCart = async () => {
      const body = $(".offcanvas-body", miniCart);
      bootstrap.Offcanvas.getOrCreateInstance(miniCart).show();
      try {
        const res = await fetch(bagLink.dataset.miniCart, { headers: { "X-Requested-With": "XMLHttpRequest" } });
        body.innerHTML = await res.text();
      } catch (e) { window.location.href = bagLink.href; }
    };
    bagLink.addEventListener("click", (e) => {
      if (window.innerWidth < 992 || e.metaKey || e.ctrlKey) return;
      e.preventDefault();
      window.cozyOpenMiniCart();
    });
  }

  // ---------------------------------------------------------------- product rails (arrows)
  $$("[data-rail]").forEach((btn) => btn.addEventListener("click", () => {
    const row = $(btn.dataset.rail);
    if (!row) return;
    row.scrollBy({ left: (btn.dataset.dir === "next" ? 1 : -1) * row.clientWidth * 0.9, behavior: "smooth" });
  }));

  // ---------------------------------------------------------------- homepage tabs
  $$("[data-tab-group]").forEach((group) => {
    const buttons = $$("button[data-tab]", group);
    buttons.forEach((b) => b.addEventListener("click", () => {
      buttons.forEach((x) => x.classList.toggle("active", x === b));
      $$(`[data-tab-panel="${group.dataset.tabGroup}"]`).forEach((p) => p.classList.toggle("d-none", p.dataset.panel !== b.dataset.tab));
    }));
  });

  // ---------------------------------------------------------------- offer countdown
  $$("[data-countdown]").forEach((el) => {
    const end = el.dataset.countdown ? new Date(el.dataset.countdown) : (() => { const d = new Date(); d.setHours(23, 59, 59, 0); return d; })();
    const tick = () => {
      let s = Math.max(0, Math.floor((end - new Date()) / 1000));
      const parts = { d: Math.floor(s / 86400), h: Math.floor((s % 86400) / 3600), m: Math.floor((s % 3600) / 60), s: s % 60 };
      Object.entries(parts).forEach(([k, v]) => { const n = $(`[data-unit="${k}"]`, el); if (n) n.textContent = String(v).padStart(2, "0"); });
    };
    tick(); setInterval(tick, 1000);
  });

  // ---------------------------------------------------------------- back to top & sticky buy bar
  const toTop = $(".to-top");
  if (toTop) {
    window.addEventListener("scroll", () => toTop.classList.toggle("show", window.scrollY > 900), { passive: true });
    toTop.addEventListener("click", () => window.scrollTo({ top: 0, behavior: "smooth" }));
  }
  const buyBar = $(".mobile-buy-bar"), buyForm = $(".pd-info .js-add-to-cart");
  if (buyBar && buyForm && "IntersectionObserver" in window) {
    new IntersectionObserver(([en]) => buyBar.classList.toggle("show", !en.isIntersecting && en.boundingClientRect.top < 0)).observe(buyForm);
    $("[data-buy-bar-submit]", buyBar).addEventListener("click", () => {
      const btn = $("button[type=submit]:not([name])", buyForm);
      if (btn) btn.click(); else buyForm.requestSubmit();
    });
  }

  // ---------------------------------------------------------------- confirmations
  document.addEventListener("submit", (e) => {
    const form = e.target.closest("[data-confirm]");
    if (form && !window.confirm(form.dataset.confirm)) e.preventDefault();
  });
})();
