function initSearch() {
  const input = document.getElementById("symbol-search");
  const results = document.getElementById("search-results");
  if (!input || !results) return;

  let debounceTimer;

  function renderResults(items) {
    if (!items.length) {
      results.innerHTML = '<div class="search-empty">No matches</div>';
      results.classList.add("open");
      return;
    }
    results.innerHTML = "";
    items.forEach(item => {
      const row = document.createElement("div");
      row.className = "search-item";
      row.innerHTML = `
        <span class="search-symbol">${item.symbol}</span>
        <span class="search-name">${item.name}</span>
        <span class="search-type">${item.type}</span>
      `;
      row.addEventListener("click", () => {
        window.location.href = `/chart/${encodeURIComponent(item.symbol)}`;
      });
      results.appendChild(row);
    });
    results.classList.add("open");
  }

  input.addEventListener("input", () => {
    clearTimeout(debounceTimer);
    const q = input.value.trim();
    if (q.length < 1) {
      results.innerHTML = "";
      results.classList.remove("open");
      return;
    }
    debounceTimer = setTimeout(async () => {
      try {
        const res = await fetch(`/api/search?q=${encodeURIComponent(q)}`);
        if (res.status === 401) {
          window.location.href = "/login";
          return;
        }
        const items = await res.json();
        renderResults(items);
      } catch (e) {
        results.innerHTML = '<div class="search-empty">Search unavailable</div>';
        results.classList.add("open");
      }
    }, 250);
  });

  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      const q = input.value.trim();
      if (q) window.location.href = `/chart/${encodeURIComponent(q.toUpperCase())}`;
    }
  });

  document.addEventListener("click", (e) => {
    if (!results.contains(e.target) && e.target !== input) {
      results.classList.remove("open");
    }
  });
}

document.addEventListener("DOMContentLoaded", initSearch);
