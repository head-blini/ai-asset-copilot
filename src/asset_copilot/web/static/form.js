"use strict";

const form = document.getElementById("budget-form");
const dirty = document.getElementById("dirty-message");
const exampleId = form.querySelector('[name="example_id"]');

function markChanged() {
  const result = document.getElementById("result");
  if (result) result.remove();
  if (dirty) dirty.hidden = false;
  if (exampleId.value) {
    exampleId.value = "";
    const badge = document.querySelector(".example-badge");
    if (badge) badge.textContent = "가상 예제를 수정했습니다. 새 계산은 직접 입력으로 표시됩니다.";
  }
}

function reindex(kind) {
  const rows = document.querySelectorAll(`#${kind}-rows [data-row="${kind}"]`);
  rows.forEach((row, index) => {
    row.querySelectorAll("[name]").forEach((input) => {
      const oldName = input.name;
      input.name = oldName.replace(new RegExp(`^${kind}\\.[0-9]+\\.`), `${kind}.${index}.`);
      input.id = input.name;
      const label = input.closest("label");
      if (label) label.htmlFor = input.id;
    });
    const heading = row.querySelector(".row-head strong");
    if (heading) heading.textContent = `${kind === "entry" ? "현금흐름" : kind === "goal" ? "목표" : "관측 납입"} ${index}`;
  });
}

document.querySelectorAll(".add-row").forEach((button) => {
  button.addEventListener("click", () => {
    const kind = button.dataset.kind;
    const list = document.getElementById(`${kind}-rows`);
    const index = list.querySelectorAll(`[data-row="${kind}"]`).length;
    const fragment = document.getElementById(`${kind}-template`).content.cloneNode(true);
    fragment.querySelectorAll("[name]").forEach((input) => {
      input.name = input.name.replace("__INDEX__", String(index));
      input.id = input.name;
      const label = input.closest("label");
      if (label) label.htmlFor = input.id;
    });
    list.append(fragment);
    list.lastElementChild.querySelector("input, select")?.focus();
    markChanged();
  });
});

document.addEventListener("click", (event) => {
  if (!event.target.classList.contains("remove-row")) return;
  const row = event.target.closest("[data-row]");
  const kind = row.dataset.row;
  row.remove();
  reindex(kind);
  markChanged();
});

form.addEventListener("input", markChanged);
form.addEventListener("change", markChanged);

document.querySelectorAll(".example-link").forEach((link) => {
  link.addEventListener("click", (event) => {
    if (!window.confirm("현재 입력을 버리고 가상 예제를 불러올까요?")) event.preventDefault();
  });
});
