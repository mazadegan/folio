import { invoke } from "@tauri-apps/api/core";

const queryEl = document.getElementById("query");
const outEl = document.getElementById("output");
const btn = document.getElementById("search");

async function runSearch() {
  const query = queryEl.value.trim();
  if (!query) {
    outEl.textContent = "Enter a query.";
    return;
  }
  outEl.textContent = "Running...";
  try {
    const result = await invoke("run_folio", { args: ["search", query] });
    outEl.textContent = result;
  } catch (err) {
    outEl.textContent = `Error: ${err}`;
  }
}

btn.addEventListener("click", runSearch);
