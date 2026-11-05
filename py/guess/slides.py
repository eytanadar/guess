"""Presentations: a sequence of saved views (graph state + camera + a note) to
step through, with morphing between them (Kumu presentations, guided tours).

    addSlide("Departments by colour")     the current graph and view as a slide
    showSlide(0)                          go to a slide (animated)
    slides(); removeSlide(2); moveSlide(2, 0)

The View menu's Presentation mode adds slides with the current camera and
steps through them with the arrow keys.
"""
from .model import GuessError


def install(session):
    view = session.view
    g = session.graph
    view.slides = []

    def cmd(fn):
        session.register_command(fn.__name__, fn)
        return fn

    def announce(index=None):
        session.emit({"type": "slides", "slides": [{"note": s["note"]} for s in view.slides],
                      "index": index})

    @cmd
    def addSlide(note="", camera=None, at=None):
        """addSlide(note) saves the current graph (as a state) and view as a slide;
        camera=[x, y, zoom] is filled in by the page; at=k inserts it at k."""
        from .states import Snapshot
        key = f"slide:{len(view.slides) + 1}:{id(object())}"
        g.states[key] = Snapshot(g)
        slide = {"state": key, "note": str(note), "camera": list(camera) if camera else None}
        if at is None:
            view.slides.append(slide)
        else:
            view.slides.insert(int(at), slide)
        view.changed()
        announce(view.slides.index(slide))
        return len(view.slides) - 1 if at is None else int(at)

    @cmd
    def showSlide(index, duration=1200):
        """showSlide(k) morphs the graph to slide k's state and moves the camera."""
        k = int(index)
        if not 0 <= k < len(view.slides):
            raise GuessError(f"no slide {k} (there are {len(view.slides)})")
        s = view.slides[k]
        if s["state"] in g.states:
            session.system["morph"][0](s["state"], int(duration))
        if s["camera"]:
            session.emit({"type": "camera", "camera": s["camera"], "ms": int(duration)})
        announce(k)

    @cmd
    def slides():
        """The slides' notes, in order."""
        return [s["note"] for s in view.slides]

    @cmd
    def removeSlide(index):
        """removeSlide(k) deletes slide k."""
        k = int(index)
        if not 0 <= k < len(view.slides):
            raise GuessError(f"no slide {k}")
        s = view.slides.pop(k)
        g.states.pop(s["state"], None)
        view.changed()
        announce(min(k, len(view.slides) - 1) if view.slides else None)

    @cmd
    def moveSlide(index, to):
        """moveSlide(k, j) moves slide k to position j."""
        s = view.slides.pop(int(index))
        view.slides.insert(int(to), s)
        view.changed()
        announce(int(to))

    @cmd
    def noteSlide(index, note):
        """noteSlide(k, text) changes slide k's note."""
        view.slides[int(index)]["note"] = str(note)
        view.changed()
        announce(int(index))
