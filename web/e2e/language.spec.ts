import { test, expect, type BrowserContext, type Page } from "@playwright/test";
import { createHmac } from "node:crypto";

async function telegram(
  context: BrowserContext,
  id: number,
  language = "ru",
  dark = false,
) {
  // Isolate synthetic source addresses instead of weakening production login limits.
  await context.setExtraHTTPHeaders({
    "X-Forwarded-For": `192.0.2.${(id % 254) + 1}`,
  });
  const fields: Record<string, string> = {
    auth_date: String(Math.floor(Date.now() / 1000)),
    user: JSON.stringify({ id, first_name: "Алия", language_code: language }),
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
  await context.addInitScript(
    ({ initData, dark, language }) => {
      Object.defineProperty(window, "Telegram", {
        value: {
          WebApp: {
            initData,
            colorScheme: dark ? "dark" : "light",
            initDataUnsafe: { user: { language_code: language } },
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
    { initData: new URLSearchParams(fields).toString(), dark, language },
  );
}

async function preference(page: Page) {
  return await page.evaluate(async () => {
    const token = sessionStorage.getItem("nexcora.session");
    const response = await fetch("/api/v1/me", {
      headers: { Authorization: `Bearer ${token}` },
    });
    return await response.json();
  });
}

async function choose(page: Page, language: string) {
  await page.locator(".header select").selectOption(language);
  await expect
    .poll(async () => (await preference(page)).language_code)
    .toBe(language);
  await expect(page.locator("html")).toHaveAttribute("lang", language);
}

test("language persists across reopening and preserves the active draft and user content", async ({
  browser,
}) => {
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 },
    locale: "ru-RU",
  });
  await telegram(context, 97101);
  const page = await context.newPage();
  await page.goto("/draft");
  await page.getByLabel("Ваше имя").fill("Алия / Aliya");
  await page
    .getByLabel("Описание задачи")
    .fill("Бот для записи. Қазақша мәтін. Original English text.");
  const before = await page.locator("textarea").inputValue();
  await choose(page, "en");
  await expect(page.locator("textarea")).toHaveValue(before);
  await expect(page.locator(".bottom-nav")).toContainText("Services");
  await choose(page, "kk");
  await expect(page.locator("textarea")).toHaveValue(before);
  await expect(page.locator(".bottom-nav")).toContainText("Қызметтер");
  await page.screenshot({
    path: "artifacts/language/draft-390-kk.png",
    fullPage: true,
  });
  await expect
    .poll(async () =>
      page.evaluate(async () => {
        const token = sessionStorage.getItem("nexcora.session");
        const response = await fetch("/api/v1/me/draft", {
          headers: { Authorization: `Bearer ${token}` },
        });
        return (await response.json()).fields.description;
      }),
    )
    .toBe(before);
  await page.reload();
  await expect(page.locator(".header select")).toHaveValue("kk");
  await expect(page.locator("textarea")).toHaveValue(before);
  await expect(page.locator("input").first()).toHaveValue("Алия / Aliya");
  await context.close();
});

test("failed language save keeps the saved preference and unsaved form content", async ({
  browser,
}) => {
  const context = await browser.newContext({
    viewport: { width: 320, height: 740 },
    locale: "ru-RU",
  });
  await telegram(context, 97102);
  const page = await context.newPage();
  await page.goto("/draft");
  await page
    .getByLabel("Описание задачи")
    .fill("Мой текст должен остаться после ошибки.");
  await page.route("**/api/v1/me/language", (route) =>
    route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({
        error: {
          code: "temporarily_unavailable",
          message: "Сервис временно недоступен. Повторите позже.",
        },
      }),
    }),
  );
  await page.locator(".header select").selectOption("en");
  await expect(page.locator(".header select")).toHaveValue("ru");
  await expect(page.locator("html")).toHaveAttribute("lang", "ru");
  await expect(page.getByRole("alert")).toBeVisible();
  await expect(page.locator("textarea")).toHaveValue(
    "Мой текст должен остаться после ошибки.",
  );
  expect((await preference(page)).language_code).toBe("ru");
  await context.close();
});

test("English and Kazakh keep client and owner navigation usable at narrow widths", async ({
  browser,
}) => {
  for (const language of ["en", "kk"]) {
    const context = await browser.newContext({
      viewport: { width: 320, height: 740 },
      locale: "ru-RU",
    });
    await telegram(context, language === "en" ? 97103 : 97104, language, true);
    const page = await context.newPage();
    await page.goto("/services");
    await expect(page.locator(".header select")).toHaveValue(language);
    await expect(page.locator(".bottom-nav")).toBeVisible();
    await expect(page.locator("html")).toHaveAttribute("lang", language);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    const navigation = await page.locator(".bottom-nav").evaluate((nav) => ({
      height: nav.getBoundingClientRect().height,
      tops: [...nav.querySelectorAll("a")].map(
        (link) => link.getBoundingClientRect().top,
      ),
    }));
    expect(
      Math.max(...navigation.tops) - Math.min(...navigation.tops),
    ).toBeLessThan(1);
    expect(navigation.height).toBeLessThanOrEqual(100);
    await page.screenshot({
      path: `artifacts/language/services-320-${language}-dark.png`,
      fullPage: true,
    });
    await context.close();
  }
  const owner = await browser.newContext({
    viewport: { width: 768, height: 1024 },
    locale: "ru-RU",
  });
  await telegram(owner, 999);
  const page = await owner.newPage();
  await page.goto("/owner");
  await expect(page.locator(".bottom-nav")).toBeVisible();
  try {
    await choose(page, "kk");
    await page.screenshot({
      path: "artifacts/language/owner-768-kk.png",
      fullPage: true,
    });
    await choose(page, "en");
    await page.goto("/owner/notifications");
    await expect(page.locator("html")).toHaveAttribute("lang", "en");
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
  } finally {
    await choose(page, "ru");
    await owner.close();
  }
});

test("signed-out language choice survives reload without requiring account access", async ({
  browser,
}) => {
  const context = await browser.newContext({
    viewport: { width: 320, height: 740 },
    locale: "ru-RU",
  });
  await context.route("https://telegram.org/**", (route) => route.abort());
  const page = await context.newPage();
  await page.goto("/");
  await page.locator(".header select").selectOption("en");
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
  await expect(page.locator("h1")).not.toHaveText("Продолжим в Telegram");
  await page.reload();
  await expect(page.locator(".header select")).toHaveValue("en");
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await context.close();
});

test("custom historical service titles remain original even when they match a translated UI label", async ({
  browser,
}) => {
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 },
    locale: "ru-RU",
  });
  await telegram(context, 97105);
  const page = await context.newPage();
  await page.goto("/projects");
  await expect(page.locator(".bottom-nav")).toBeVisible();
  await choose(page, "en");
  await expect(
    page.getByRole("heading", { name: "Материалы", exact: true }),
  ).toBeVisible();
  await page.goto("/projects/971050");
  await expect(page.locator("h1")).toHaveText("Материалы");
  await choose(page, "kk");
  await expect(page.locator("h1")).toHaveText("Материалы");
  await context.close();
});

test("a delayed language response cannot restore a signed-out session", async ({
  browser,
}) => {
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 },
    locale: "ru-RU",
  });
  await telegram(context, 97106);
  const page = await context.newPage();
  await page.goto("/profile");
  await expect(page.locator(".logout")).toBeVisible();
  let releaseResponse!: () => void;
  const release = new Promise<void>((resolve) => {
    releaseResponse = resolve;
  });
  let responsePrepared!: () => void;
  const prepared = new Promise<void>((resolve) => {
    responsePrepared = resolve;
  });
  await page.route("**/api/v1/me/language", async (route) => {
    const response = await route.fetch();
    responsePrepared();
    await release;
    await route.fulfill({ response });
  });
  await page.locator(".header select").selectOption("en");
  await prepared;
  try {
    await page.locator(".logout").click();
    await expect(page.locator(".auth-card")).toBeVisible();
    expect(
      await page.evaluate(() => sessionStorage.getItem("nexcora.session")),
    ).toBeNull();
    await page.evaluate(() => {
      document.documentElement.dataset.restoredSession = "false";
      new MutationObserver(() => {
        if (document.querySelector(".bottom-nav"))
          document.documentElement.dataset.restoredSession = "true";
      }).observe(document.body, { childList: true, subtree: true });
    });
    const response = page.waitForResponse("**/api/v1/me/language");
    releaseResponse();
    await response;
    await page.evaluate(
      () =>
        new Promise((resolve) =>
          requestAnimationFrame(() => requestAnimationFrame(resolve)),
        ),
    );
    await expect(page.locator(".auth-card")).toBeVisible();
    await expect(page.locator(".bottom-nav")).toHaveCount(0);
    expect(
      await page.evaluate(
        () => document.documentElement.dataset.restoredSession,
      ),
    ).toBe("false");
    expect(
      await page.evaluate(() => sessionStorage.getItem("nexcora.session")),
    ).toBeNull();
  } finally {
    releaseResponse();
    await context.close();
  }
});
