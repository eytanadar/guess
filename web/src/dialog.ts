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
