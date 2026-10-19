import { test, expect, type BrowserContext } from "@playwright/test";
import { createHmac } from "node:crypto";

// These users and seeded examples exist only in server.py's temporary database.
// Telegram's external SDK is isolated; the API still verifies the actual HMAC.
async function telegram(context: BrowserContext, id: number) {
  const fields: Record<string, string> = {
    auth_date: String(Math.floor(Date.now() / 1000)),
    user: JSON.stringify({
      id,
      first_name: "Проверка кабинета",
      username: `workspace_${id}`,
    }),
  };
  const secret = createHmac("sha256", "WebAppData")
    .update("123456:synthetic-test-token")
    .digest();
  fields.hash = createHmac("sha256", secret)
    .update(
      Object.keys(fields)
        .sort()
        .map((key) => `${key}=${fields[key]}`)
        .join("\n"),
    )
    .digest("hex");
  await context.route("https://telegram.org/**", (route) => route.abort());
  await context.addInitScript((initData) => {
    Object.defineProperty(window, "Telegram", {
      value: {
        WebApp: {
          initData,
          colorScheme: "light",
          ready() {},
          expand() {},
          onEvent() {},
          offEvent() {},
          BackButton: { show() {}, hide() {}, onClick() {}, offClick() {} },
          openTelegramLink() {},
        },
      },
    });
  }, new URLSearchParams(fields).toString());
}

test("returning client sees the old active project and next action ahead of newer archive entries", async ({
  context,
  page,
}) => {
  await telegram(context, 92001);
  const projectRequests: string[] = [];
  page.on("request", (request) => {
    if (new URL(request.url()).pathname === "/api/v1/me/projects")
      projectRequests.push(request.url());
  });
  await page.goto("/");
  await expect(
    page.getByRole("heading", { level: 1, name: "Ваши проекты", exact: true }),
  ).toBeVisible();
  const active = page.locator('a.project-card[href="/projects/920001"]');
  await expect(active).toBeInViewport();
  await expect(active).toContainText("Исполнитель работает над проектом");
  await expect(page.locator(".project-card")).toHaveCount(1);
  expect(
    projectRequests.some(
      (url) => new URL(url).searchParams.get("active_only") === "true",
    ),
    "active projects are selected before server pagination",
  ).toBe(true);
  await expect(
    page.getByRole("heading", {
      name: "Расскажите о вашей задаче",
      exact: true,
    }),
  ).toHaveCount(0);
  await page.getByRole("button", { name: "Новая заявка", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Новая заявка", exact: true }),
  ).toBeVisible();
});

test("a first-time client keeps the explanation and original project CTA", async ({
  context,
  page,
}) => {
  await telegram(context, 92003);
  await page.goto("/");
  await expect(
    page.getByRole("heading", {
      name: "Здесь начнётся ваш первый проект",
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", {
      name: "Расскажите о вашей задаче",
      exact: true,
    }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Обсудить проект", exact: true })
    .click();
  await expect(page).toHaveURL(/\/draft$/);
  await expect(page.getByLabel("Описание задачи")).toBeVisible();
});

test("a client with only closed history can open the archive without a fake first-project state", async ({
  context,
  page,
}) => {
  await telegram(context, 92002);
  await page.goto("/");
  await expect(
    page.getByRole("heading", { level: 1, name: "Ваши проекты", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", {
      name: "Здесь начнётся ваш первый проект",
      exact: true,
    }),
  ).toHaveCount(0);
  await expect(page.locator("a.project-card")).toHaveCount(0);
  await page.getByRole("link", { name: /архив|Все проекты/i }).click();
  await expect(page).toHaveURL(/\/projects$/);
  await expect(
    page.locator('a.project-card[href="/projects/920030"]'),
  ).toBeVisible();
  await expect(
    page.locator('a.project-card[href="/projects/920031"]'),
  ).toBeVisible();
});

test("home request failure offers retry and does not claim an empty account", async ({
  context,
  page,
}) => {
  await telegram(context, 92001);
  await page.route("**/api/v1/me/projects**", (route) => route.abort("failed"));
  await page.goto("/");
  await expect(page.getByRole("alert")).toContainText("соединение");
  await expect(
    page.getByRole("heading", {
      name: "Здесь начнётся ваш первый проект",
      exact: true,
    }),
  ).toHaveCount(0);
  await page.unroute("**/api/v1/me/projects**");
  await page.getByRole("button", { name: "Повторить", exact: true }).click();
  await expect(
    page.locator('a.project-card[href="/projects/920001"]'),
  ).toBeVisible();
  await expect(page.getByRole("alert")).toHaveCount(0);
});

test("owner attention count opens only new, discussing and agreed projects", async ({
  context,
  page,
}) => {
  await telegram(context, 999);
  const summaryResponse = page.waitForResponse("**/api/v1/owner/summary");
  await page.goto("/owner");
  const summary = await (await summaryResponse).json();
  const attention = page.locator(".attention-panel");
  await expect(
    attention.getByRole("heading", { name: "Требуют внимания", exact: true }),
  ).toBeVisible();
  // API count is independently verified by backend tests. This boundary check
  // catches accidentally displaying total/new/waiting_client in this UI.
  await expect(attention.locator("strong")).toHaveText(
    String(summary.needs_response),
  );
  const action = attention.getByRole("link", {
    name: "Показать проекты, требующие внимания",
    exact: true,
  });
  await expect(action).toHaveAttribute(
    "href",
    "/owner/projects?attention=true",
  );
  await action.click();
  await expect(page.getByLabel("Этап проекта")).toHaveValue("attention");
  for (const projectId of [920100, 920101, 920102]) {
    await expect(
      page.locator(`a.project-card[href="/owner/projects/${projectId}"]`),
    ).toBeVisible();
  }
  for (const projectId of [920103, 920104, 920105, 920106, 920107]) {
    await expect(
      page.locator(`a.project-card[href="/owner/projects/${projectId}"]`),
    ).toHaveCount(0);
  }
  await page.reload();
  await expect(page.getByLabel("Этап проекта")).toHaveValue("attention");
  await expect(
    page.locator('a.project-card[href="/owner/projects/920101"]'),
  ).toBeVisible();
  await page.getByLabel("Этап проекта").selectOption("proposal_sent");
  await expect(
    page.locator('a.project-card[href="/owner/projects/920103"]'),
  ).toBeVisible();
  await expect(
    page.locator('a.project-card[href="/owner/projects/920100"]'),
  ).toHaveCount(0);
});

test("optional wishes remain collapsible and survive save, reload, review and submission", async ({
  context,
  page,
}) => {
  await telegram(context, 92004);
  await page.goto("/draft");
  await expect(
    page.getByRole("heading", { name: "Новая заявка", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", {
      name: "Хорошая задача начинается с разговора",
      exact: true,
    }),
  ).toHaveCount(0);
  await expect(
    page.getByText("Материалы видите вы и исполнитель.", { exact: true }),
  ).toBeVisible();
  const optional = page.locator("details.optional-fields");
  const disclosure = optional.locator("summary");
  await expect(disclosure).toHaveText("Дополнительно");
  await expect(optional).toHaveJSProperty("open", false);
  await expect(page.getByLabel("Ориентир по бюджету")).not.toBeVisible();
  await disclosure.click();
  await page.getByLabel("Услуга").selectOption("bot");
  await page.getByLabel("Ваше имя").fill("Клиент с пожеланиями");
  await page
    .getByLabel("Описание задачи")
    .fill("Нужен бот для записи клиентов с напоминаниями о занятиях.");
  await page.getByLabel("Ориентир по бюджету").fill("До 25 000 KZT");
  await page.getByLabel("Желаемый срок").fill("До конца следующего месяца");
  await expect(
    page.getByText("Черновик сохранён", { exact: true }),
  ).toBeVisible();
  await disclosure.click();
  await expect(page.getByLabel("Ориентир по бюджету")).not.toBeVisible();
  await page.reload();
  await expect(page.getByLabel("Ориентир по бюджету")).toBeVisible();
  await expect(page.getByLabel("Ориентир по бюджету")).toHaveValue(
    "До 25 000 KZT",
  );
  await expect(page.getByLabel("Желаемый срок")).toHaveValue(
    "До конца следующего месяца",
  );
  await page
    .getByRole("button", { name: "Проверить заявку", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Всё верно?", exact: true }),
  ).toBeVisible();
  await expect(page.locator("dd", { hasText: "До 25 000 KZT" })).toBeVisible();
  await expect(
    page.locator("dd", { hasText: "До конца следующего месяца" }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Отправить заявку", exact: true })
    .click();
  await expect(page).toHaveURL(/\/projects\/\d+$/);
  await expect(page.locator("dd", { hasText: "До 25 000 KZT" })).toBeVisible();
  await expect(
    page.locator("dd", { hasText: "До конца следующего месяца" }),
  ).toBeVisible();
  await page.reload();
  await expect(page.locator("dd", { hasText: "До 25 000 KZT" })).toBeVisible();
  await expect(
    page.locator("dd", { hasText: "До конца следующего месяца" }),
  ).toBeVisible();
});

test("a client can submit a complete request without opening optional wishes", async ({
  context,
  page,
}) => {
  await telegram(context, 92005);
  await page.goto("/draft");
  await expect(
    page.getByRole("heading", { name: "Новая заявка", exact: true }),
  ).toBeVisible();
  await page.getByLabel("Услуга").selectOption("api");
  await page.getByLabel("Ваше имя").fill("Клиент без пожеланий");
  await page
    .getByLabel("Описание задачи")
    .fill("Сохранять данные из API в CSV для дальнейшего анализа.");
  await expect(page.getByLabel("Ориентир по бюджету")).not.toBeVisible();
  await page
    .getByRole("button", { name: "Проверить заявку", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Отправить заявку", exact: true })
    .click();
  await expect(page).toHaveURL(/\/projects\/\d+$/);
  await expect(
    page.getByRole("heading", { name: "API-интеграция", exact: true }),
  ).toBeVisible();
});
