// Toolbar icons ("Network" set): each tool drawn from nodes and edges, on a
// 24×24 grid with a 1.6 px round stroke, in the text colour (the pressed tool
// takes the accent). .dot is a filled node, .faint secondary detail, .f a
// closed shape (outline only here).

const ICONS: Record<string, string> = {
  select: `<circle class="faint" cx="9" cy="9" r="5.5"/><circle class="dot" cx="9" cy="9" r="2.4"/><path class="f" d="m13.5 13 7 2.8-3 1.2-1.2 3z"/>`,
  lens: `<circle class="f" cx="9" cy="12" r="6"/><circle class="dot" cx="7.5" cy="13.5" r="1.6"/><circle class="dot" cx="10.5" cy="10.5" r="1.6"/><path d="M7.5 13.5l3-3"/><path d="M16 9h5M16.5 12H21M16 15h5" class="faint"/>`,
  path: `<path class="faint" d="M9 11 12 4"/><circle class="faint dot" cx="12" cy="4" r="1.3"/><path d="M4.5 18.5 9 11l6 3 4.5-8"/><circle cx="4.5" cy="18.5" r="2" class="f"/><circle class="dot" cx="9" cy="11" r="1.7"/><circle class="dot" cx="15" cy="14" r="1.7"/><circle cx="19.5" cy="6" r="2" class="f"/>`,
  heat: `<circle class="dot" cx="12" cy="12" r="2.4"/><g class="dot"><circle cx="12" cy="6.6" r="1.4"/><circle cx="17.4" cy="12" r="1.4"/><circle cx="12" cy="17.4" r="1.4"/><circle cx="6.6" cy="12" r="1.4"/></g><g class="dot faint"><circle cx="18" cy="5.5" r="1.1"/><circle cx="20.5" cy="17" r="1.1"/><circle cx="6" cy="19.5" r="1.1"/><circle cx="3.6" cy="7" r="1.1"/></g>`,
  paint: `<circle cx="8" cy="16" r="3.4" class="f"/><path class="f" d="M16.5 3.5s4 4.4 4 7.1a4 4 0 0 1-8 0c0-2.7 4-7.1 4-7.1z"/><path class="faint" d="M11.2 14.3 13.6 13"/>`,
  cluster: `<path class="f" stroke-dasharray="2.6 2.2" d="M4.5 9.5c0-3.6 3.8-5.5 7.5-5.5s7 2.3 7 5.6-3.4 5.9-7.2 5.9-7.3-2.4-7.3-6z"/><path d="M8.5 10.5 12 7.5l3.5 3"/><circle class="dot" cx="8.5" cy="10.5" r="1.6"/><circle class="dot" cx="12" cy="7.5" r="1.6"/><circle class="dot" cx="15.5" cy="10.5" r="1.6"/><path class="faint" d="M15.5 10.5 19 19"/><circle class="dot faint" cx="19" cy="19" r="1.6"/>`,
  search: `<circle class="f" cx="10.5" cy="10.5" r="6"/><circle class="dot" cx="10.5" cy="10.5" r="1.8"/><path d="m15 15 5 5"/>`,
  stop: `<rect class="f" x="6.5" y="6.5" width="11" height="11" rx="2"/>`,
};

/** An icon as an <svg> element (size in px), or null if there is none by that name. */
export function icon(name: string, size = 20): SVGSVGElement | null {
  const body = ICONS[name];
  if (!body) return null;
  const tpl = document.createElement("template");
  tpl.innerHTML = `<svg class="ticon" viewBox="0 0 24 24" width="${size}" height="${size}" aria-hidden="true" focusable="false">${body}</svg>`;
  return tpl.content.firstElementChild as SVGSVGElement;
}

/** Turn the header's text tool buttons into icon buttons. The name stays as a
 *  visually hidden label (so search, app toolbars and screen readers still
 *  find it) and leads the tooltip. Search and Stop get an icon before their text. */
export function iconizeToolbar(root: ParentNode = document) {
  for (const b of root.querySelectorAll<HTMLButtonElement>("header.toolbar [data-tool]")) {
    const name = b.dataset.tool!;
    const svg = icon(name);
    if (!svg || b.querySelector(".ticon")) continue;
    const label = (b.textContent ?? "").replace("◎", "").trim() || name;
    const span = document.createElement("span");
    span.className = "tool-label";
    span.textContent = label;
    b.replaceChildren(svg, span);
    b.classList.add("icon-tool");
    b.setAttribute("aria-label", label);
    if (b.title && !b.title.startsWith(label)) b.title = `${label}: ${b.title}`;
  }
  for (const [sel, name] of [["#search", "search"], ["#stop", "stop"]] as const) {
    const b = root.querySelector<HTMLElement>(sel);
    const svg = icon(name, 15);
    if (b && svg && !b.querySelector(".ticon")) b.prepend(svg);
  }
}
