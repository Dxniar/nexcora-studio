interface TelegramWebApp {
  initData: string;
  colorScheme: "dark" | "light";
  safeAreaInset?: { top: number; bottom: number; left: number; right: number };
  contentSafeAreaInset?: { top: number; bottom: number };
  ready(): void;
  expand(): void;
  onEvent(name: string, callback: () => void): void;
  offEvent(name: string, callback: () => void): void;
  BackButton: {
    show(): void;
    hide(): void;
    onClick(callback: () => void): void;
    offClick(callback: () => void): void;
  };
  openTelegramLink(url: string): void;
  requestWriteAccess?(callback: (granted: boolean) => void): void;
}
declare global {
  interface Window {
    Telegram?: { WebApp: TelegramWebApp };
  }
}
export const telegram = () => window.Telegram?.WebApp;
export function syncTelegramTheme() {
  const app = telegram();
  const saved = localStorage.getItem("nexcora.theme");
  document.documentElement.dataset.theme =
    saved ||
    app?.colorScheme ||
    (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  const style = document.documentElement.style;
  style.setProperty(
    "--tg-top",
    `${(app?.safeAreaInset?.top || 0) + (app?.contentSafeAreaInset?.top || 0)}px`,
  );
  style.setProperty(
    "--tg-bottom",
    `${Math.max(app?.safeAreaInset?.bottom || 0, app?.contentSafeAreaInset?.bottom || 0)}px`,
  );
}
export function contactOwner(username: string) {
  const url = `https://t.me/${username.replace(/^@/, "")}`;
  const app = telegram();
  if (app) app.openTelegramLink(url);
  else window.open(url, "_blank", "noopener,noreferrer");
}
