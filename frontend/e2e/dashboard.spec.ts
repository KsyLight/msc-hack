import { test, expect } from "@playwright/test";

test("dashboard, filters, ticket lifecycle and responsive layout", async ({
  page,
  request,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (err) => errors.push(err.message));
  const health = await (await request.get("/api/health")).json();
  const real = health.mode === "real";
  await page.goto("/");
  await expect(
    page.getByRole("heading", {
      name: real ? "Мониторинг коллекторов" : "Всё под контролем",
    }),
  ).toBeVisible();
  if (!real)
    await expect(
      page.getByText("Демонстрационный режим", { exact: true }),
    ).toBeVisible();
  await expect(page.locator("tbody tr")).toHaveCount(6);
  await expect(page.locator(".recharts-area-curve")).toHaveCount(2);
  if (real) {
    await expect(
      page.getByRole("heading", { name: "История сообщений о неисправности" }),
    ).toBeVisible();
    await page
      .getByRole("combobox", { name: "Период истории" })
      .selectOption("366");
    await expect(
      page.getByRole("combobox", { name: "Период истории" }),
    ).toHaveValue("366");
    await expect(page.locator(".object-ranking button")).toHaveCount(5);
  }
  await page.screenshot({
    path: `../reports/dashboard-${health.mode}-desktop.png`,
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
  if (real) {
    await expect(page.getByRole("dialog")).toContainText("Инженерная система");
    await expect(page.getByRole("dialog")).toContainText("Название датчика");
  }
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
  await page
    .getByRole("button", { name: "Состояние данных", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Доступность прогнозов" }),
  ).toBeVisible();
  if (real) {
    await expect(
      page.getByRole("heading", { name: "Каналы по типам оборудования" }),
    ).toBeVisible();
    await expect(page.getByText(/Нет данных за/)).toBeVisible();
    await page.screenshot({
      path: "../reports/data-quality-real.png",
      fullPage: true,
    });
  }
  await page
    .getByRole("button", { name: "Обзор системы", exact: true })
    .click();
  await page.setViewportSize({ width: 390, height: 844 });
  // Verify a fresh mobile load; do not capture the intermediate ResizeObserver frame.
  await page.reload();
  await expect(
    page.getByRole("heading", {
      name: real ? "Мониторинг коллекторов" : "Всё под контролем",
    }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Обзор системы", exact: true }),
  ).toBeVisible();
  await expect(page.locator(".recharts-area-curve")).toHaveCount(2);
  await expect
    .poll(async () =>
      page
        .locator(".recharts-wrapper")
        .evaluate((element) => element.getBoundingClientRect().width),
    )
    .toBeLessThan(390);
  await page.screenshot({
    path: `../reports/dashboard-${health.mode}-mobile.png`,
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
  expect(errors).toEqual([]);
});
