// A modal dialog asking for one value (instead of the browser's prompt()).

export interface AskOptions {
  title: string;
  label?: string;
  value?: string;
  /** extra explanation under the title */
  note?: string;
  placeholder?: string;
  ok?: string;
  type?: "text" | "number" | "url";
}

/** Resolves to the entered text, or null if cancelled. */
export function ask(opts: AskOptions): Promise<string | null> {
  return new Promise((resolve) => {
    const dlg = document.createElement("dialog");
    dlg.className = "ask-dialog";
    const form = document.createElement("form");
    form.method = "dialog";
    const h = document.createElement("h3");
    h.textContent = opts.title;
    form.append(h);
    if (opts.note) {
      const p = document.createElement("p");
      p.textContent = opts.note;
      form.append(p);
    }
    const label = document.createElement("label");
    label.className = "ask-label";
    if (opts.label) label.append(opts.label);
    const input = document.createElement("input");
    input.type = opts.type ?? "text";
    if (opts.type === "number") input.step = "any";
    input.value = opts.value ?? "";
    input.placeholder = opts.placeholder ?? "";
    input.required = true;
    label.append(input);
    const actions = document.createElement("div");
    actions.className = "ask-actions";
    const cancel = document.createElement("button");
    cancel.type = "button";
    cancel.textContent = "Cancel";
    const ok = document.createElement("button");
    ok.type = "submit";
    ok.className = "primary";
    ok.textContent = opts.ok ?? "OK";
    actions.append(cancel, ok);
    form.append(label, actions);
    dlg.append(form);
    document.body.append(dlg);
    let result: string | null = null;
    form.addEventListener("submit", () => {
      result = input.value.trim() || null;
    });
    cancel.addEventListener("click", () => dlg.close());
    dlg.addEventListener("close", () => {
      dlg.remove();
      resolve(result);
    });
    dlg.showModal();
    input.focus();
    input.select();
  });
}

/** A modal question answered with one of several buttons (the last is the
 *  default). Resolves to the chosen button's value, or null if cancelled. */
export function choose(opts: { title: string; note?: string; choices: { label: string; value: string }[] }): Promise<string | null> {
  return new Promise((resolve) => {
    const dlg = document.createElement("dialog");
    dlg.className = "ask-dialog";
    const form = document.createElement("form");
    form.method = "dialog";
    const h = document.createElement("h3");
    h.textContent = opts.title;
    form.append(h);
    if (opts.note) {
      const p = document.createElement("p");
      p.textContent = opts.note;
      form.append(p);
    }
    const actions = document.createElement("div");
    actions.className = "ask-actions";
    const cancel = document.createElement("button");
    cancel.type = "button";
    cancel.textContent = "Cancel";
    actions.append(cancel);
    let result: string | null = null;
    const buttons = opts.choices.map((c, i) => {
      const b = document.createElement("button");
      b.type = "button";
      b.textContent = c.label;
      b.dataset.value = c.value;
      if (i === opts.choices.length - 1) b.className = "primary";
      b.onclick = () => {
        result = c.value;
        dlg.close();
      };
      return b;
    });
    actions.append(...buttons);
    form.append(actions);
    dlg.append(form);
    document.body.append(dlg);
    cancel.addEventListener("click", () => dlg.close());
    dlg.addEventListener("close", () => {
      dlg.remove();
      resolve(result);
    });
    dlg.showModal();
    buttons[buttons.length - 1]?.focus();
  });
}

/** A modal list of checkboxes in groups (the fields shown on hover). Resolves to
 *  the checked names by group key, or null if cancelled. */
export function pickFields(opts: {
  title: string; note?: string;
  groups: { key: string; label: string; fields: string[]; checked: string[] }[];
}): Promise<Record<string, string[]> | null> {
  return new Promise((resolve) => {
    const dlg = document.createElement("dialog");
    dlg.className = "ask-dialog pick-fields";
    const form = document.createElement("form");
    form.method = "dialog";
    const h = document.createElement("h3");
    h.textContent = opts.title;
    form.append(h);
    if (opts.note) {
      const p = document.createElement("p");
      p.textContent = opts.note;
      form.append(p);
    }
    const cols = document.createElement("div");
    cols.className = "pick-cols";
    const boxes: { key: string; name: string; box: HTMLInputElement }[] = [];
    for (const g of opts.groups) {
      const col = document.createElement("fieldset");
      const lg = document.createElement("legend");
      lg.textContent = g.label;
      col.append(lg);
      // the chosen ones first, in their order, then the rest
      const order = [...g.checked.filter((f) => g.fields.includes(f)), ...g.fields.filter((f) => !g.checked.includes(f))];
      for (const name of order) {
        const l = document.createElement("label");
        const box = document.createElement("input");
        box.type = "checkbox";
        box.checked = g.checked.includes(name);
        box.dataset.field = name;
        l.append(box, name);
        col.append(l);
        boxes.push({ key: g.key, name, box });
      }
      if (!order.length) col.append("(none)");
      cols.append(col);
    }
    form.append(cols);
    const actions = document.createElement("div");
    actions.className = "ask-actions";
    const all = document.createElement("button");
    all.type = "button";
    all.textContent = "Select all";
    all.onclick = () => boxes.forEach((b) => (b.box.checked = true));
    const none = document.createElement("button");
    none.type = "button";
    none.textContent = "Select none";
    none.title = "Clear every box: the tooltip shows just the label at first";
    none.onclick = () => boxes.forEach((b) => (b.box.checked = false));
    const spacer = document.createElement("span");
    spacer.style.flex = "1";
    const cancel = document.createElement("button");
    cancel.type = "button";
    cancel.textContent = "Cancel";
    const ok = document.createElement("button");
    ok.type = "submit";
    ok.className = "primary";
    ok.textContent = "Apply";
    actions.append(all, none, spacer, cancel, ok);
    form.append(actions);
    dlg.append(form);
    document.body.append(dlg);
    let result: Record<string, string[]> | null = null;
    form.addEventListener("submit", () => {
      result = Object.fromEntries(opts.groups.map((g) => [g.key, [] as string[]]));
      for (const b of boxes) if (b.box.checked) result[b.key].push(b.name);
    });
    cancel.addEventListener("click", () => dlg.close());
    dlg.addEventListener("close", () => {
      dlg.remove();
      resolve(result);
    });
    dlg.showModal();
    ok.focus();
  });
}
