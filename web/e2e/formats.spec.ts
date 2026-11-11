import { expect, test } from "@playwright/test";
import { boot, lastError } from "./helpers";
test("dropping files in Cytoscape and biology formats opens them", async ({ page }) => {
  await boot(page);
  const drop = async (name: string, text: string) => {
    await page.evaluate(async ([n, t]) => {
      const dt = new DataTransfer();
      dt.items.add(new File([t], n));
      document.dispatchEvent(new DragEvent("drop", { dataTransfer: dt, bubbles: true, cancelable: true }));
    }, [name, text]);
  };
  const count = () => page.evaluate(() => (window as any).__guess.renderer.nodes.size);
  await drop("net.sif", "A pp B C\nB pd D\n");
  await expect.poll(count).toBe(4);
  await drop("model.xml", '<?xml version="1.0"?><sbml xmlns="http://www.sbml.org/sbml/level3/version1/core" level="3" version="1"><model id="m"><listOfSpecies><species id="A" compartment="c"/><species id="B" compartment="c"/></listOfSpecies><listOfReactions><reaction id="r1" reversible="false"><listOfReactants><speciesReference species="A"/></listOfReactants><listOfProducts><speciesReference species="B"/></listOfProducts></reaction></listOfReactions></model></sbml>');
  await expect.poll(count).toBe(3);
  await expect(page.locator(".cell-code").last()).toContainText('makeFromFile("model.xml")');
  expect(await lastError(page)).toBeNull();
});
