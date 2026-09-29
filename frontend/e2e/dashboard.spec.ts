import { test, expect } from "@playwright/test";

test("dashboard, filters, ticket lifecycle and responsive layout", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (err) => errors.push(err.message));
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Всё под контролем" }),
  ).toBeVisible();
  await expect(
    page.getByText("Демонстрационный контур", { exact: true }),
  ).toBeVisible();
  await expect(page.locator("tbody tr")).toHaveCount(6);
  await expect(page.locator(".recharts-area-curve")).toHaveCount(2);
  await page.screenshot({
    path: "../reports/dashboard-desktop.png",
    fullPage: true,
  });
  await page
    .getByRole("button", { name: "Журнал прогнозов", exact: true })
    .first()
    .click();
  await page
    .getByRole("combobox", { name: "Направление", exact: true })
    .selectOption("infrastructure");
  await page
    .getByRole("combobox", { name: "Риск", exact: true })
    .selectOption("high");
  await expect(page.locator("tbody tr").first()).toContainText(
    "Инфраструктура",
  );
  await page.locator("tbody .object-link").first().click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page
    .getByRole("textbox", { name: "Комментарий к заявке" })
    .fill("E2E: проверка локального сценария");
  await page
    .getByRole("button", { name: "Создать заявку на диагностику", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page.getByRole("button", { name: /Заявки на ремонт/ }).click();
  const ticket = page
    .locator(".ticket")
    .filter({ hasText: "E2E: проверка локального сценария" })
    .first();
  await expect(ticket).toBeVisible();
  await ticket.getByRole("button", { name: "Взять в работу" }).click();
  await expect(ticket).toContainText("В работе");
  await ticket.getByRole("button", { name: "Завершить", exact: true }).click();
  await expect(ticket).toContainText("Завершена");
  await page.reload();
  await page.getByRole("button", { name: /Заявки на ремонт/ }).click();
  await expect(
    page
      .locator(".ticket")
      .filter({ hasText: "E2E: проверка локального сценария" })
      .first(),
  ).toContainText("Завершена");
  await page.getByRole("button", { name: "Модели", exact: true }).click();
  await expect(page.locator(".model-card")).toHaveCount(2);
  await page
    .getByRole("button", { name: "Источники данных", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Прозрачность данных" }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Обзор системы", exact: true })
    .click();
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(
    page.getByRole("button", { name: "Обзор системы", exact: true }),
  ).toBeVisible();
  await expect(page.locator(".recharts-area-curve")).toHaveCount(2);
  await page.screenshot({
    path: "../reports/dashboard-mobile.png",
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
  expect(errors).toEqual([]);
});
