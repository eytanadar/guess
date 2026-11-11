# Outbreak Explorer: an example GUESS app (epidemiology).
# A simulated primary school (classes, grades, teachers); everything here is invented.

makeFromFile("school-contacts-SIMULATED.gdf")
colorize(room)
legendFor(room)
zero = [None]     # patient zero (a list, so the handlers can change it)
runs = [0]

beta = Slider(0.01, 0.5, 0.1, 0.01, label="infection rate β")
gamma = Slider(0.01, 0.5, 0.1, 0.01, label="recovery rate γ")

def choose(n):
    zero[0] = n
    select([n])

graphevents.clickNode = choose

def zero_text():
    z = zero[0]
    return f"Patient zero: **{z.name}** ({z.role}, room {z.room})" if z else "*Click a pupil or teacher to choose patient zero.*"

def run():
    z = zero[0]
    if z is None:
        StatusBar.setStatus("Choose patient zero first: click someone")
        return
    runs[0] += 1
    spread([z], "SIR", beta=beta.value, gamma=gamma.value, seed=runs[0])
    colorBy(infected_at, yellow, red)
    (infected_at < 0).color = lightgray

def reached():
    try:
        hit = len(infected_at >= 0)
    except Exception:
        return "*No outbreak yet.*"
    return f"Reached **{hit}** of {len(g.nodes)} people ({100 * hit // len(g.nodes)}%)"

def reset():
    colorize(room)

ui.title("Outbreak Explorer", "simulated data")
ui.layout(
    left=Column(
        Markdown("""### How far does it spread?
Each run starts from **patient zero** and passes along the contacts of a
school day, with infection rate β and recovery rate γ (an SIR model).
Yellow was reached early, red late, grey never."""),
        Markdown(zero_text),
        Group("Disease", beta, gamma),
        Row(Button("Run an outbreak", onClick=run), Button("Reset colours", onClick=reset)),
        Markdown(reached)),
    sizes={"left": 300},
)
ui.menubar(Menu("Outbreak", MenuItem("Run", onClick=run), MenuItem("Reset colours", onClick=reset),
                "-", Action("png")), keep=["Help"])
ui.statusbar(Label(lambda: f"{len(g.nodes)} people · {len(g.edges)} contacts"))
