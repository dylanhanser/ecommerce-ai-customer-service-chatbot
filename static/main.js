const form = document.querySelector("#chatForm");
const input = document.querySelector("#questionInput");
const button = document.querySelector("#sendButton");
const chatWindow = document.querySelector("#chatWindow");
const pageLayout = document.querySelector(".page");
const internalDebugPanel = document.querySelector(".debug-card");
const demoProductList = document.querySelector("#demoProductList");
const selectedProduct = document.querySelector("#selectedProduct");
const demoCatalogToggle = document.querySelector("#demoCatalogToggle");
const demoCatalogBody = document.querySelector("#demoCatalogBody");

if (internalDebugPanel) {
  internalDebugPanel.remove();
}

if (pageLayout) {
  pageLayout.classList.add("chat-only");
}

if (demoCatalogToggle && demoCatalogBody) {
  demoCatalogToggle.addEventListener("click", () => {
    const isExpanded = demoCatalogToggle.getAttribute("aria-expanded") === "true";
    const nextExpanded = !isExpanded;
    demoCatalogBody.hidden = !nextExpanded;
    demoCatalogToggle.setAttribute("aria-expanded", String(nextExpanded));
    demoCatalogToggle.textContent = nextExpanded ? "收起商品" : "展开商品";
  });
}

function appendMessage(role, text) {
  const message = document.createElement("div");
  message.className = `message ${role}`;

  const avatar = document.createElement("div");
  avatar.className = "avatar";
  avatar.textContent = role === "user" ? "\u4f60" : "AI";

  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.appendChild(document.createTextNode(String(text ?? "")));

  message.appendChild(avatar);
  message.appendChild(bubble);
  chatWindow.appendChild(message);
  chatWindow.scrollTop = chatWindow.scrollHeight;
}

function setLoading(isLoading) {
  button.disabled = isLoading;
  input.disabled = isLoading;
  button.textContent = isLoading ? "\u751f\u6210\u4e2d..." : "\u53d1\u9001";
}

function setSelectedProduct(product) {
  if (!selectedProduct) {
    return;
  }
  selectedProduct.replaceChildren();
  selectedProduct.dataset.selectedProductId = product ? product.product_id : "";
  selectedProduct.classList.toggle("is-empty", !product);
  if (!product) {
    selectedProduct.textContent = "当前未选择商品";
    return;
  }

  const title = document.createElement("strong");
  title.textContent = `当前：${product.name}`;
  const classification = document.createElement("span");
  classification.className = "demo-data-label";
  classification.textContent = "模拟商品数据，仅用于功能演示";

  const details = document.createElement("div");
  details.className = "selected-product-details";
  const materials = product.construction || {};
  const detailRows = [
    [
      "材料",
      `鞋面${materials.upper_material} / 内里${materials.lining_material} / 鞋底${materials.sole_material}`,
    ],
    ["版型", product.fit_note],
    ["尺码", (product.available_sizes || []).map((size) => `${size}码`).join("、")],
    ["颜色", (product.available_colors || []).join("、")],
    [
      "鞋底",
      `跟高${materials.heel_height_cm ?? "未提供"}${
        materials.heel_height_cm == null ? "" : "厘米"
      } / 前掌厚度${materials.platform_height_cm ?? "未提供"}${
        materials.platform_height_cm == null ? "" : "厘米"
      }`,
    ],
    ["功能", product.key_function],
    ["销售", product.sale_type === "preorder" ? "预售" : "现货"],
  ];
  detailRows.forEach(([label, value]) => {
    const item = document.createElement("span");
    const labelNode = document.createElement("b");
    labelNode.textContent = `${label}：`;
    item.appendChild(labelNode);
    item.appendChild(document.createTextNode(String(value || "未提供")));
    details.appendChild(item);
  });

  selectedProduct.appendChild(title);
  selectedProduct.appendChild(classification);
  selectedProduct.appendChild(details);
}

function createProductAction(label, className) {
  const element = document.createElement("button");
  element.type = "button";
  element.className = className;
  element.textContent = label;
  return element;
}

function safeProductImageUrl(product) {
  if (typeof product.thumbnail_url !== "string" || !product.thumbnail_url) {
    return null;
  }
  const expectedPrefix = `/static/demo-products/${product.product_id}/`;
  if (
    !product.thumbnail_url.startsWith(expectedPrefix) ||
    product.thumbnail_url.includes("..") ||
    product.thumbnail_url.includes("\\") ||
    product.thumbnail_url.includes("?") ||
    product.thumbnail_url.includes("#")
  ) {
    return null;
  }
  return product.thumbnail_url;
}

function createProductPlaceholder(product) {
  const placeholder = document.createElement("div");
  placeholder.className = "demo-product-placeholder";
  placeholder.setAttribute("role", "img");
  placeholder.setAttribute("aria-label", product.thumbnail_alt || "暂无商品图片");
  placeholder.textContent = "暂无商品图片";
  return placeholder;
}

function createProductMedia(product) {
  const media = document.createElement("div");
  media.className = "demo-product-media";
  const imageUrl = safeProductImageUrl(product);
  if (!imageUrl) {
    media.appendChild(createProductPlaceholder(product));
    return media;
  }

  const image = document.createElement("img");
  image.src = imageUrl;
  image.alt = product.thumbnail_alt || `${product.name}商品图片`;
  image.loading = "lazy";
  image.width = 320;
  image.height = 180;
  image.addEventListener(
    "error",
    () => {
      const placeholder = createProductPlaceholder(product);
      image.replaceWith(placeholder);
    },
    { once: true },
  );
  media.appendChild(image);
  return media;
}

async function selectDemoProduct(product) {
  const response = await fetch("/api/demo-products/select", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ product_id: product.product_id }),
  });
  if (!response.ok) {
    throw new Error("demo product selection failed");
  }
  const data = await response.json();
  setSelectedProduct(data.selected_product);
}

function renderDemoProducts(products, selectedProductId) {
  if (!demoProductList) {
    return;
  }
  demoProductList.replaceChildren();

  products.forEach((product) => {
    const card = document.createElement("article");
    card.className = "demo-product-card";
    card.dataset.productId = product.product_id;
    if (product.product_id === selectedProductId) {
      card.classList.add("selected");
    }

    const media = createProductMedia(product);

    const name = document.createElement("h3");
    name.textContent = product.name;

    const price = document.createElement("p");
    price.className = "demo-product-price";
    price.textContent = `¥${Number(product.display_price).toFixed(2)}`;

    const description = document.createElement("p");
    description.textContent = product.short_description;

    const tags = document.createElement("p");
    tags.className = "demo-product-tags";
    tags.textContent = `${product.fit_note} · ${product.key_function} · ${
      product.sale_type === "preorder" ? "预售" : "现货"
    }`;

    const actions = document.createElement("div");
    actions.className = "demo-product-actions";

    const viewLink = document.createElement("a");
    viewLink.href = product.product_path;
    viewLink.textContent = "查看商品";

    const consultButton = createProductAction("咨询这款", "product-consult-button");
    consultButton.addEventListener("click", async () => {
      consultButton.disabled = true;
      try {
        await selectDemoProduct(product);
        document
          .querySelectorAll(".demo-product-card.selected")
          .forEach((item) => item.classList.remove("selected"));
        card.classList.add("selected");
        input.focus();
      } catch {
        appendMessage("bot", "演示商品暂时无法选择，请稍后重试。");
      } finally {
        consultButton.disabled = false;
      }
    });

    const shareButton = createProductAction("复制链接", "product-share-button");
    shareButton.addEventListener("click", async () => {
      const shareUrl = new URL(product.product_path, window.location.origin).href;
      try {
        await navigator.clipboard.writeText(shareUrl);
        shareButton.textContent = "已复制";
      } catch {
        shareButton.textContent = "可打开查看商品复制";
      }
    });

    actions.appendChild(viewLink);
    actions.appendChild(consultButton);
    actions.appendChild(shareButton);
    card.appendChild(media);
    card.appendChild(name);
    card.appendChild(price);
    card.appendChild(description);
    card.appendChild(tags);
    card.appendChild(actions);
    demoProductList.appendChild(card);
  });
}

async function loadDemoProducts() {
  if (!demoProductList) {
    return;
  }
  try {
    const response = await fetch("/api/demo-products");
    if (!response.ok) {
      throw new Error("demo product list failed");
    }
    const data = await response.json();
    const products = Array.isArray(data.products) ? data.products : [];
    renderDemoProducts(products, data.selected_product_id || "");
    const current = products.find(
      (product) => product.product_id === data.selected_product_id,
    );
    setSelectedProduct(current || null);
  } catch {
    demoProductList.replaceChildren();
    const error = document.createElement("p");
    error.className = "demo-product-loading";
    error.appendChild(document.createTextNode("演示商品暂时无法加载。"));
    demoProductList.appendChild(error);
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const question = input.value.trim();

  appendMessage("user", question || "\uff08\u7a7a\u8f93\u5165\uff09");
  input.value = "";
  setLoading(true);

  try {
    const response = await fetch("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });

    const data = await response.json().catch(() => ({}));
    const answer =
      typeof data.final_answer === "string" && data.final_answer
        ? data.final_answer
        : "\u6682\u65f6\u65e0\u6cd5\u5904\u7406\uff0c\u8bf7\u7a0d\u540e\u91cd\u8bd5\u3002";
    appendMessage("bot", answer);
  } catch {
    appendMessage("bot", "\u6682\u65f6\u65e0\u6cd5\u5904\u7406\uff0c\u8bf7\u7a0d\u540e\u91cd\u8bd5\u3002");
  } finally {
    setLoading(false);
    input.focus();
  }
});

loadDemoProducts();
