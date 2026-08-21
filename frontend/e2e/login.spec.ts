import { expect, test } from "@playwright/test";

const PASSWORD = process.env.E2E_PASSWORD ?? "dev-senha-123";

test.beforeEach(async ({ page }) => {
  await page.goto("/login");
});

test("golden path: login leads to the dashboard with real data", async ({ page }) => {
  await page.getByLabel("Senha").fill(PASSWORD);
  await page.getByRole("button", { name: "Entrar" }).click();

  await expect(page.getByRole("heading", { name: "Minha Carteira" })).toBeVisible();
  // Data actually came from the API, not a placeholder.
  await expect(page.getByRole("region", { name: "Resumo da carteira" })).toBeVisible();
  await expect(page.getByText("Patrimônio total")).toBeVisible();
  await expect(page.getByRole("button", { name: "Sair" })).toBeVisible();
});

test("a wrong password keeps the user on the login screen", async ({ page }) => {
  await page.getByLabel("Senha").fill("senha-errada");
  await page.getByRole("button", { name: "Entrar" }).click();

  await expect(page.getByRole("alert")).toHaveText("Senha incorreta.");
  await expect(page.getByRole("button", { name: "Sair" })).toHaveCount(0);
});

test("the dashboard is not reachable without logging in", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveURL(/\/login$/);
});

test("logging out returns to the login screen", async ({ page }) => {
  await page.getByLabel("Senha").fill(PASSWORD);
  await page.getByRole("button", { name: "Entrar" }).click();
  await expect(page.getByRole("button", { name: "Sair" })).toBeVisible();

  await page.getByRole("button", { name: "Sair" }).click();
  await expect(page).toHaveURL(/\/login$/);
});
