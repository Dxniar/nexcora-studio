import {
  test,
  expect,
  type APIRequestContext,
  type BrowserContext,
  type Page,
} from "@playwright/test";
import { createHmac } from "node:crypto";

// Identity passes the disposable fixture's real Telegram HMAC verification.
function signedInit(id: number) {
  const fields: Record<string, string> = {
    auth_date: String(Math.floor(Date.now() / 1000)),
    user: JSON.stringify({
      id,
      first_name: id === 999 ? "Владелец" : "Клиент проверки интерфейса",
      username: `readability_${id}`,
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
  return new URLSearchParams(fields).toString();
}

async function telegram(
  context: BrowserContext,
  id: number,
  dark: boolean,
  insets = false,
) {
  await context.route("https://telegram.org/**", (route) => route.abort());
  await context.addInitScript(
    ({ initData, dark, insets }) => {
      Object.defineProperty(window, "Telegram", {
        value: {
          WebApp: {
            initData,
            colorScheme: dark ? "dark" : "light",
            safeAreaInset: insets
              ? { top: 24, bottom: 34, left: 0, right: 0 }
              : undefined,
            contentSafeAreaInset: insets ? { top: 20, bottom: 0 } : undefined,
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
    { initData: signedInit(id), dark, insets },
  );
}

const longReference = "ProjectReferenceWithoutAnySpaces".repeat(9);
const description = `Нужна интеграция каталога и заявок с подробным журналом изменений. Идентификатор внешней системы: ${longReference}`;

async function seedProject(request: APIRequestContext, clientId: number) {
  const auth = await request.post("/api/v1/auth/telegram", {
    data: { init_data: signedInit(clientId) },
  });
  expect(auth.ok(), "synthetic fixture login").toBeTruthy();
  const { access_token } = await auth.json();
  const headers = { Authorization: `Bearer ${access_token}` };
  const draftResponse = await request.get("/api/v1/me/draft", { headers });
  expect(draftResponse.ok()).toBeTruthy();
  const draft = await draftResponse.json();
  const saved = await request.put("/api/v1/me/draft", {
    headers,
    data: {
      expected_version: draft.version,
      fields: {
        service_id: "api",
        name: "Клиент с длинным названием проекта для проверки переноса",
        description,
        budget: "Обсудим после уточнения деталей интеграции",
        deadline: "После согласования условий",
      },
    },
  });
  expect(saved.ok()).toBeTruthy();
  const submitted = await request.post("/api/v1/me/draft/submit", {
    headers: { ...headers, "Idempotency-Key": `readability-${clientId}` },
    data: {
      draft_id: draft.id,
      expected_version: (await saved.json()).version,
      attachments_version: draft.attachments.version,
    },
  });
  expect(submitted.ok()).toBeTruthy();
  return (await submitted.json()).id as number;
}

async function inspectReadability(page: Page, screen: string) {
  const findings = await page.evaluate(() => {
    const visible = (element: Element) => {
      const style = getComputedStyle(element);
      const rect = element.getBoundingClientRect();
      return (
        style.display !== "none" &&
        style.visibility !== "hidden" &&
        style.opacity !== "0" &&
        rect.width > 0 &&
        rect.height > 0
      );
    };
    const name = (element: Element) =>
      `${element.tagName.toLowerCase()} ${element.getAttribute("aria-label") || element.textContent?.trim() || element.getAttribute("placeholder") || ""}`
        .replace(/\s+/g, " ")
        .slice(0, 100);
    const fontProblems = (selector: string, minimum: number) =>
      [...document.querySelectorAll(selector)]
        .filter(visible)
        .flatMap((element) => {
          const size = parseFloat(getComputedStyle(element).fontSize);
          return size < minimum
            ? [`${name(element)}: ${size}px, expected at least ${minimum}px`]
            : [];
        });
    const controlProblems = [
      ...document.querySelectorAll(
        "button, a[href], input:not([type=file]), textarea, select, summary, label:has(input[type=file])",
      ),
    ]
      .filter(visible)
      .flatMap((element) => {
        const rect = element.getBoundingClientRect();
        return rect.height < 43.5 || rect.width < 43.5
          ? [
              `${name(element)}: target ${Math.round(rect.width)}×${Math.round(rect.height)}px, expected at least 44×44px`,
            ]
          : [];
      });
    const contentProblems = [
      ...document.querySelectorAll(
        "main .panel, main .project-card, main .service-card, main .preserve, main .project-excerpt, main .details dd",
      ),
    ]
      .filter(visible)
      .flatMap((element) =>
        element.scrollWidth > element.clientWidth + 1
          ? [
              `${name(element)}: content width ${element.scrollWidth}px exceeds ${element.clientWidth}px`,
            ]
          : [],
      );
    return {
      paragraphs: fontProblems("main p", 16),
      inputs: fontProblems(
        "main input:not([type=file]), main textarea, main select",
        16,
      ),
      labels: fontProblems(
        "main label > span, main label.upload-button, main dt",
        14,
      ),
      controls: controlProblems,
      content: contentProblems,
      documentWidth: document.documentElement.scrollWidth,
      viewportWidth: window.innerWidth,
    };
  });
  expect.soft(findings.paragraphs, `${screen}: readable body copy`).toEqual([]);
  expect.soft(findings.inputs, `${screen}: legible form values`).toEqual([]);
  expect.soft(findings.labels, `${screen}: legible labels`).toEqual([]);
  expect.soft(findings.controls, `${screen}: usable touch targets`).toEqual([]);
  expect
    .soft(findings.content, `${screen}: long content fits its container`)
    .toEqual([]);
  expect
    .soft(findings.documentWidth, `${screen}: no horizontal page scrolling`)
    .toBeLessThanOrEqual(findings.viewportWidth + 1);

  await page.evaluate(() =>
    window.scrollTo(0, document.documentElement.scrollHeight),
  );
  const clearance = await page.evaluate(() => {
    const nav = document.querySelector('nav[aria-label="Основная навигация"]');
    if (!nav || getComputedStyle(nav).position !== "fixed") return null;
    const navRect = nav.getBoundingClientRect();
    const bottoms = [
      ...document.querySelectorAll(
        "main p, main h3, main dd, main button, main a, main input:not([type=file]), main select, main textarea, main summary",
      ),
    ]
      .map((element) => element.getBoundingClientRect())
      .filter(
        (rect) =>
          rect.width > 0 &&
          rect.height > 0 &&
          rect.left < navRect.right &&
          rect.right > navRect.left,
      )
      .map((rect) => rect.bottom);
    if (!bottoms.length) return null;
    return {
      contentBottom: Math.max(...bottoms),
      navTop: navRect.top,
    };
  });
  if (clearance)
    expect
      .soft(
        clearance.contentBottom,
        `${screen}: last content can scroll above navigation`,
      )
      .toBeLessThanOrEqual(clearance.navTop + 1);
  await page.evaluate(() => window.scrollTo(0, 0));
}

async function visit(
  page: Page,
  path: string,
  heading: string | RegExp,
  artifact: string,
) {
  await page.goto(path);
  await expect(
    page.getByRole("heading", { name: heading, exact: true }),
  ).toBeVisible();
  await expect(page.locator(".loading")).toHaveCount(0);
  await inspectReadability(page, artifact);
  await page.screenshot({
    path: `artifacts/readability/${artifact}.png`,
    fullPage: true,
  });
}

// A bounded representative matrix covers every requested width and both themes.
const cases = [
  { width: 320, height: 740, dark: false },
  { width: 390, height: 844, dark: true },
  { width: 768, height: 1024, dark: false },
  { width: 1440, height: 900, dark: true },
];

for (const viewport of cases) {
  const suffix = `${viewport.width}-${viewport.dark ? "dark" : "light"}`;
  test(`readable client and owner screens at ${suffix}`, async ({
    browser,
    request,
  }) => {
    const clientId = 80_000 + viewport.width;
    const projectId = await seedProject(request, clientId);
    const context = await browser.newContext({ viewport });
    await telegram(context, clientId, viewport.dark);
    const client = await context.newPage();
    await visit(client, "/", "Ваши проекты", `client-home-${suffix}`);
    await visit(client, "/services", "Что создадим?", `services-${suffix}`);
    await visit(client, "/draft", "Новая заявка", `draft-${suffix}`);
    await visit(
      client,
      "/projects",
      "Мои проекты",
      `client-projects-${suffix}`,
    );
    await visit(
      client,
      `/projects/${projectId}`,
      "API-интеграция",
      `client-detail-${suffix}`,
    );
    await expect(
      client.locator(".preserve", { hasText: longReference }),
    ).toHaveText(description);
    await visit(client, "/profile", "Профиль", `profile-${suffix}`);
    await context.close();

    const ownerContext = await browser.newContext({ viewport });
    await telegram(ownerContext, 999, viewport.dark);
    const owner = await ownerContext.newPage();
    await visit(owner, "/owner", "Рабочий обзор", `owner-home-${suffix}`);
    await visit(
      owner,
      "/owner/projects",
      "Проекты студии",
      `owner-projects-${suffix}`,
    );
    await visit(
      owner,
      "/owner/notifications",
      "Уведомления",
      `notifications-${suffix}`,
    );
    await visit(
      owner,
      `/owner/projects/${projectId}`,
      "API-интеграция",
      `owner-detail-${suffix}`,
    );
    const proposalButton = owner.getByRole("button", {
      name: "Новое предложение",
      exact: true,
    });
    await proposalButton.click();
    await expect(owner.getByLabel("Объём работ")).toBeVisible();
    await expect(
      owner
        .locator(".editor")
        .getByRole("heading", { name: "Новое предложение", exact: true }),
    ).toBeInViewport();
    await expect
      .poll(() =>
        owner.evaluate(() =>
          Boolean(document.activeElement?.closest(".editor")),
        ),
      )
      .toBe(true);
    await inspectReadability(owner, `proposal-editor-${suffix}`);
    await owner.screenshot({
      path: `artifacts/readability/proposal-editor-${suffix}.png`,
      fullPage: true,
    });
    await owner
      .getByRole("button", { name: "Закрыть редактор", exact: true })
      .click();
    await expect(proposalButton).toBeFocused();
    await ownerContext.close();
  });
}

test("Telegram entry explanation remains readable on the narrowest screen", async ({
  browser,
}) => {
  const context = await browser.newContext({
    viewport: { width: 320, height: 740 },
  });
  await context.route("https://telegram.org/**", (route) => route.abort());
  const page = await context.newPage();
  await visit(page, "/", "Продолжим в Telegram", "telegram-entry-320-light");
  await page.getByRole("button", { name: "Переключить тему" }).click();
  await inspectReadability(page, "telegram-entry-320-dark");
  await page.screenshot({
    path: "artifacts/readability/telegram-entry-320-dark.png",
    fullPage: true,
  });
  await context.close();
});

test("keyboard users can skip navigation without a persistent overlay", async ({
  browser,
}) => {
  const context = await browser.newContext();
  await context.route("https://telegram.org/**", (route) => route.abort());
  const page = await context.newPage();
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Продолжим в Telegram" }),
  ).toBeVisible();
  const skip = page.locator(".skip-link");
  await expect(skip).toHaveCSS("opacity", "0");
  await page.keyboard.press("Tab");
  await expect(skip).toBeFocused();
  await expect(skip).toHaveCSS("opacity", "1");
  await page.keyboard.press("Enter");
  await expect(page.locator("main")).toBeFocused();
  await expect(skip).toHaveCSS("opacity", "0");
  await context.close();
});

test("200 percent text preserves forms, safe areas and desktop navigation", async ({
  browser,
}) => {
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 },
  });
  await telegram(context, 89_390, false, true);
  await context.addInitScript(() => {
    document.addEventListener("DOMContentLoaded", () => {
      document.documentElement.style.fontSize = "200%";
    });
  });
  const page = await context.newPage();
  await visit(page, "/draft", "Новая заявка", "draft-390-text-200-safe-area");
  await expect(page.locator("html")).toHaveCSS("font-size", "32px");
  await expect(page.locator(".shell")).toHaveCSS("padding-top", "60px");
  await expect(page.locator(".bottom-nav")).toHaveCSS("padding-bottom", "42px");
  const brokenNavigationWords = await page
    .locator(".bottom-nav > a > span")
    .evaluateAll((labels) =>
      labels.flatMap((label) => {
        const text = label.firstChild;
        if (!text?.textContent) return [];
        return [...text.textContent.matchAll(/\S+/g)].flatMap((word) => {
          const range = document.createRange();
          range.setStart(text, word.index!);
          range.setEnd(text, word.index! + word[0].length);
          return range.getClientRects().length > 1 ? [word[0]] : [];
        });
      }),
    );
  expect(
    brokenNavigationWords,
    "navigation labels keep whole words at enlarged text",
  ).toEqual([]);
  await page
    .getByLabel("Описание задачи")
    .fill("Описание проекта при увеличенном тексте");
  await page.getByLabel("Описание задачи").focus();
  await expect(page.getByLabel("Описание задачи")).toBeFocused();
  await inspectReadability(page, "draft at 200 percent text with safe areas");
  await context.close();
  const ownerContext = await browser.newContext({
    viewport: { width: 1440, height: 900 },
  });
  await telegram(ownerContext, 999, true);
  await ownerContext.addInitScript(() => {
    document.addEventListener("DOMContentLoaded", () => {
      document.documentElement.style.fontSize = "200%";
    });
  });
  const owner = await ownerContext.newPage();
  await visit(owner, "/owner", "Рабочий обзор", "owner-1440-text-200");
  const navBounds = await owner.locator(".bottom-nav").boundingBox();
  for (const link of await owner.locator(".bottom-nav > a").all()) {
    const bounds = await link.boundingBox();
    expect(
      bounds!.x + bounds!.width,
      "enlarged sidebar links fit navigation",
    ).toBeLessThanOrEqual(navBounds!.x + navBounds!.width);
  }
  await ownerContext.close();
});
