import { test, expect, BrowserContext, Page } from "@playwright/test";
import { createHmac } from "node:crypto";

// The SDK is external UI plumbing; identity still passes the real backend HMAC check.
function signedInit(id: number) {
  const fields: Record<string, string> = {
    auth_date: String(Math.floor(Date.now() / 1000)),
    user: JSON.stringify({
      id,
      first_name: id === 999 ? "Владелец" : "Алия",
      username: `synthetic_${id}`,
    }),
  };
  const secret = createHmac("sha256", "WebAppData")
    .update("123456:synthetic-test-token")
    .digest();
  fields.hash = createHmac("sha256", secret)
    .update(
      Object.keys(fields)
        .sort()
        .map((k) => `${k}=${fields[k]}`)
        .join("\n"),
    )
    .digest("hex");
  return new URLSearchParams(fields).toString();
}
async function telegram(context: BrowserContext, id: number, dark = false) {
  await context.route("https://telegram.org/**", (route) => route.abort());
  await context.addInitScript(
    ({ initData, dark }) => {
      Object.defineProperty(window, "Telegram", {
        value: {
          WebApp: {
            initData,
            colorScheme: dark ? "dark" : "light",
            ready() {},
            expand() {},
            onEvent() {},
            offEvent() {},
            BackButton: { show() {}, hide() {}, onClick() {}, offClick() {} },
            openTelegramLink() {},
          },
        },
      });
    },
    { initData: signedInit(id), dark },
  );
}
async function reload(page: Page) {
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Telegram-бот", exact: true }),
  ).toBeVisible();
}

test("client and owner complete actual versioned proposal, revision and delivery with a file", async ({
  browser,
}) => {
  const clientContext = await browser.newContext({
    viewport: { width: 390, height: 844 },
  });
  await telegram(clientContext, 101);
  const client = await clientContext.newPage();
  await client.goto("/");
  await expect(
    client.getByRole("button", { name: "Обсудить проект", exact: true }),
  ).toBeVisible();
  await expect(
    client.getByRole("heading", { name: "Здесь начнётся ваш первый проект" }),
  ).toBeVisible();
  await client.screenshot({
    path: "artifacts/home-mobile-light.png",
    fullPage: true,
  });
  await client
    .getByRole("button", { name: "Обсудить проект", exact: true })
    .click();
  await client.getByLabel("Услуга").selectOption("bot");
  await client.getByLabel("Ваше имя").fill("Алия");
  await client
    .getByLabel("Описание задачи")
    .fill("Нужен Telegram-бот для записи на занятия и сбора заявок.");
  await client.getByLabel("Приложить файлы").setInputFiles({
    name: "brief.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("Synthetic browser test brief"),
  });
  await expect(
    client.getByText("Файл загружен", { exact: true }),
  ).toBeVisible();
  await expect(
    client.getByText("Черновик сохранён", { exact: true }),
  ).toBeVisible();
  await client.reload();
  await expect(client.getByLabel("Описание задачи")).toHaveValue(
    "Нужен Telegram-бот для записи на занятия и сбора заявок.",
  );
  await client
    .getByRole("button", { name: "Проверить заявку", exact: true })
    .click();
  await client
    .getByRole("button", { name: "Отправить заявку", exact: true })
    .click();
  await expect(client).toHaveURL(/\/projects\/\d+$/);
  await expect(
    client.getByRole("heading", { name: "Telegram-бот", exact: true }),
  ).toBeVisible();
  const id = new URL(client.url()).pathname.split("/").pop();
  const ownerContext = await browser.newContext({
    viewport: { width: 1280, height: 900 },
  });
  await telegram(ownerContext, 999);
  const owner = await ownerContext.newPage();
  await owner.goto("/");
  await expect(
    owner.getByRole("heading", { name: "Рабочий обзор" }),
  ).toBeVisible();
  await owner.screenshot({
    path: "artifacts/owner-dashboard-desktop-light.png",
    fullPage: true,
  });
  await owner.goto(`/owner/projects/${id}`);
  await owner
    .getByRole("button", { name: "Новое предложение", exact: true })
    .click();
  await owner
    .getByLabel("Объём работ")
    .fill("Меню бота, анкета записи, передача заявок владельцу.");
  await owner
    .getByLabel("Результат", { exact: true })
    .fill("Исходный код бота и инструкция по запуску проекта.");
  await owner.getByLabel("Цена", { exact: true }).fill("15000.50");
  await owner.getByLabel("Валюта").selectOption("KZT");
  await owner.getByLabel("Срок выполнения").fill("2099-12-20");
  await owner
    .getByLabel("Условия правок")
    .fill("Один раунд правок по согласованному объёму.");
  await owner
    .getByRole("button", { name: "Проверить предложение", exact: true })
    .click();
  await owner
    .getByRole("button", { name: "Опубликовать предложение", exact: true })
    .click();
  await expect(
    owner.getByText("Ждём согласования", { exact: true }).first(),
  ).toBeVisible();
  await reload(client);
  await expect(client.getByText(/15.*000,50/)).toBeVisible();
  await client
    .getByRole("button", { name: "Согласовать условия", exact: true })
    .click();
  await expect(
    client.getByText("Условия согласованы", { exact: true }).first(),
  ).toBeVisible();
  await reload(owner);
  await owner
    .getByRole("button", { name: "Начать работу", exact: true })
    .click();
  await owner
    .getByRole("button", { name: "Передать результат", exact: true })
    .click();
  await owner
    .getByLabel("Описание результата")
    .fill("Готовый бот с инструкцией для тестирования и запуска.");
  await owner
    .getByLabel("Ссылка на результат")
    .fill("https://example.org/result");
  await owner
    .getByRole("button", { name: "Отправить на приёмку", exact: true })
    .click();
  await reload(client);
  await client
    .getByRole("button", { name: "Нужны правки", exact: true })
    .click();
  await client
    .getByLabel("Комментарий")
    .fill("Пожалуйста, уточните инструкцию по запуску.");
  await client
    .getByRole("button", { name: "Отправить комментарий", exact: true })
    .click();
  await expect(
    client.getByText("В работе", { exact: true }).first(),
  ).toBeVisible();
  await reload(owner);
  await owner
    .getByRole("button", { name: "Передать результат", exact: true })
    .click();
  await owner
    .getByLabel("Описание результата")
    .fill("Инструкция дополнена согласно комментарию клиента.");
  await owner
    .getByLabel("Ссылка на результат")
    .fill("https://example.org/result-v2");
  await owner
    .getByRole("button", { name: "Отправить на приёмку", exact: true })
    .click();
  await reload(client);
  await client
    .getByRole("button", { name: "Принять результат", exact: true })
    .click();
  await expect(
    client.getByText("Завершён", { exact: true }).first(),
  ).toBeVisible();
  await expect(
    client.getByText("Пожалуйста, уточните инструкцию по запуску.", {
      exact: true,
    }),
  ).toBeVisible();
  const download = client.waitForEvent("download");
  await client.getByRole("button", { name: /Скачать brief.txt/ }).click();
  expect((await download).suggestedFilename()).toBe("brief.txt");
  await client.screenshot({
    path: "artifacts/client-mobile-light.png",
    fullPage: true,
  });
  await client.getByRole("button", { name: "Переключить тему" }).click();
  await client.screenshot({
    path: "artifacts/client-mobile-dark.png",
    fullPage: true,
  });
  await client.setViewportSize({ width: 1280, height: 900 });
  await client.screenshot({
    path: "artifacts/client-desktop-dark.png",
    fullPage: true,
  });
  await reload(owner);
  await owner.screenshot({
    path: "artifacts/owner-desktop-light.png",
    fullPage: true,
  });
  await owner.setViewportSize({ width: 390, height: 844 });
  await owner.screenshot({
    path: "artifacts/owner-mobile-light.png",
    fullPage: true,
  });
  await owner.getByRole("button", { name: "Переключить тему" }).click();
  await owner.screenshot({
    path: "artifacts/owner-mobile-dark.png",
    fullPage: true,
  });
  expect(
    await owner.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await owner.setViewportSize({ width: 1280, height: 900 });
  await owner.screenshot({
    path: "artifacts/owner-desktop-dark.png",
    fullPage: true,
  });
  await clientContext.close();
  await ownerContext.close();
});

test("outside Telegram has no fake login and clients cannot read owner or foreign projects", async ({
  browser,
}) => {
  const outside = await browser.newPage();
  await outside.goto("/");
  await expect(
    outside.getByRole("heading", { name: "Продолжим в Telegram" }),
  ).toBeVisible();
  await expect(outside.getByRole("button", { name: "Демо-вход" })).toHaveCount(
    0,
  );
  await outside.close();
  const context = await browser.newContext();
  await telegram(context, 202, true);
  const page = await context.newPage();
  await page.goto("/owner/projects");
  await expect(
    page.getByRole("heading", { name: "Кабинет владельца недоступен" }),
  ).toBeVisible();
  await page.goto("/projects/1");
  await expect(page.getByRole("alert")).toContainText("Запись не найдена");
  await page.goto("/services");
  await expect(
    page.getByRole("heading", { name: "Что создадим?" }),
  ).toBeVisible();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "artifacts/services-desktop-dark.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 360, height: 800 });
  await page.screenshot({
    path: "artifacts/services-mobile-dark.png",
    fullPage: true,
  });
  await context.close();
});

test("conflicting autosave preserves local text until an explicit reconciliation", async ({
  browser,
}) => {
  const context = await browser.newContext();
  await telegram(context, 303);
  const first = await context.newPage();
  const second = await context.newPage();
  await first.goto("/draft");
  await second.goto("/draft");
  await first
    .getByLabel("Описание задачи")
    .fill("Первая версия задачи, сохранённая в первом окне.");
  await expect(
    first.getByText("Черновик сохранён", { exact: true }),
  ).toBeVisible();
  await second
    .getByLabel("Описание задачи")
    .fill("Мои изменения во втором окне остаются для проверки.");
  await expect(second.getByRole("alert")).toContainText("Черновик изменился");
  await expect(second.getByLabel("Описание задачи")).toHaveValue(
    "Мои изменения во втором окне остаются для проверки.",
  );
  await second.getByRole("button", { name: "Сохранить мои изменения" }).click();
  await expect(
    second.getByText("Черновик сохранён", { exact: true }),
  ).toBeVisible();
  await second.reload();
  await expect(second.getByLabel("Описание задачи")).toHaveValue(
    "Мои изменения во втором окне остаются для проверки.",
  );
  await context.close();
});

test("lost submit response retries the same intent and creates only one project", async ({
  browser,
}) => {
  const context = await browser.newContext();
  await telegram(context, 404);
  const page = await context.newPage();
  await page.goto("/draft");
  await page.getByLabel("Услуга").selectOption("api");
  await page.getByLabel("Ваше имя").fill("Синтетический клиент");
  await page
    .getByLabel("Описание задачи")
    .fill("Получить данные через API и сохранить результат в CSV.");
  await page
    .getByRole("button", { name: "Проверить заявку", exact: true })
    .click();
  let firstKey: string | undefined;
  await page.route("**/api/v1/me/draft/submit", async (route) => {
    firstKey = route.request().headers()["idempotency-key"];
    await route.fetch(); // The real server commits, but the browser loses its response.
    await route.abort("failed");
    await page.unroute("**/api/v1/me/draft/submit");
  });
  await page
    .getByRole("button", { name: "Отправить заявку", exact: true })
    .click();
  await expect(page.getByRole("alert")).toContainText("соединение");
  const retried = page.waitForRequest("**/api/v1/me/draft/submit");
  await page
    .getByRole("button", { name: "Повторить действие", exact: true })
    .click();
  expect((await retried).headers()["idempotency-key"]).toBe(firstKey);
  await expect(
    page.getByRole("heading", { name: "API-интеграция", exact: true }),
  ).toBeVisible();
  await page.goto("/projects");
  await expect(page.getByRole("link", { name: /API-интеграция/ })).toHaveCount(
    1,
  );
  await context.close();
});

test("owner client view retains the draft and dashboard links filter the queue", async ({
  browser,
}) => {
  const context = await browser.newContext();
  await telegram(context, 999);
  const page = await context.newPage();
  await page.goto("/");
  await page.getByRole("link", { name: "Клиентский вид" }).click();
  await page
    .getByRole("button", { name: "Обсудить проект", exact: true })
    .click();
  await page
    .getByLabel("Описание задачи")
    .fill("Черновик владельца сохраняется при смене вида кабинета.");
  await expect(
    page.getByText("Черновик сохранён", { exact: true }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Кабинет владельца" }).click();
  await expect(
    page.getByRole("heading", { name: "Рабочий обзор" }),
  ).toBeVisible();
  await page.getByRole("link", { name: /Новые обращения/ }).click();
  await expect(page.getByLabel("Этап проекта")).toHaveValue("new");
  await page.getByRole("link", { name: "Обзор", exact: true }).click();
  await page.getByRole("link", { name: /Ждём клиента/ }).click();
  await expect(page.getByLabel("Этап проекта")).toHaveValue("proposal_sent");
  await page.getByRole("link", { name: "Клиентский вид" }).click();
  await page
    .getByRole("button", { name: "Обсудить проект", exact: true })
    .click();
  await expect(page.getByLabel("Описание задачи")).toHaveValue(
    "Черновик владельца сохраняется при смене вида кабинета.",
  );
  await page.screenshot({
    path: "artifacts/draft-mobile-light.png",
    fullPage: true,
  });
  await context.close();
});

test("notification preference survives reload and data deletion needs its explicit confirmation", async ({
  browser,
}) => {
  const context = await browser.newContext();
  await telegram(context, 505);
  const page = await context.newPage();
  await page.goto("/profile");
  const toggle = page.getByRole("switch", { name: "Уведомления в Telegram" });
  await expect(toggle).toHaveAttribute("aria-checked", "true");
  await toggle.click();
  await expect(toggle).toHaveAttribute("aria-checked", "false");
  await page.reload();
  await expect(toggle).toHaveAttribute("aria-checked", "false");
  await page
    .getByRole("button", { name: "Удалить мои данные", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Подтвердить удаление", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Отмена", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Профиль", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Удалить мои данные", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Подтвердить удаление", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Ваши данные удалены" }),
  ).toBeVisible();
  const token = await page.evaluate(() =>
    sessionStorage.getItem("nexcora.session"),
  );
  expect(token).toBeNull();
  await context.close();
});

test("offline navigation shows a recovery action and expired sessions require Telegram reentry", async ({
  browser,
}) => {
  const context = await browser.newContext();
  await telegram(context, 707);
  const page = await context.newPage();
  await page.goto("/");
  await expect(
    page.getByRole("button", { name: "Обсудить проект", exact: true }),
  ).toBeVisible();
  await context.setOffline(true);
  await page.getByRole("link", { name: "Мои проекты", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("соединение");
  await expect(page.getByRole("status")).toContainText("Нет соединения");
  await context.setOffline(false);
  await page.getByRole("button", { name: "Повторить", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Пока нет проектов" }),
  ).toBeVisible();
  await page.evaluate(async () => {
    await fetch("/api/v1/auth/logout", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${sessionStorage.getItem("nexcora.session")}`,
      },
    });
  });
  await page.getByRole("link", { name: "Профиль", exact: true }).click();
  await page.getByRole("switch", { name: "Уведомления в Telegram" }).click();
  await expect(
    page.getByRole("heading", { name: "Сессия завершена" }),
  ).toBeVisible();
  expect(
    await page.evaluate(() => sessionStorage.getItem("nexcora.session")),
  ).toBeNull();
  await context.close();
});
