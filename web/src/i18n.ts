import { useSyncExternalStore } from "react";
import en from "./locales/en";
import kk from "./locales/kk";

export type Language = "ru" | "en" | "kk";
export const languageNames: Record<Language, string> = {
  ru: "Русский",
  en: "English",
  kk: "Қазақша",
};
const LANGUAGE_KEY = "nexcora.language";
const catalogs: Record<Language, Record<string, string>> = { ru: {}, en, kk };
export function normalizeLanguage(value?: string | null): Language {
  const base = value?.toLowerCase().split(/[-_]/)[0];
  return base === "en" || base === "kk" ? base : "ru";
}
function initialLanguage(): Language {
  try {
    const saved = localStorage.getItem(LANGUAGE_KEY);
    if (saved === "ru" || saved === "en" || saved === "kk") return saved;
  } catch {
    /* language remains usable when storage is unavailable */
  }
  try {
    const data = window.Telegram?.WebApp.initData;
    if (data) {
      const user = JSON.parse(new URLSearchParams(data).get("user") || "null");
      if (typeof user?.language_code === "string")
        return normalizeLanguage(user.language_code);
    }
  } catch {
    /* Telegram authentication validates the signed payload separately */
  }
  return normalizeLanguage(navigator.language);
}
let language = initialLanguage();
document.documentElement.lang = language;
const listeners = new Set<() => void>();
export const getLanguage = () => language;
export const intlLocale = () =>
  ({ ru: "ru-RU", en: "en-GB", kk: "kk-KZ" })[language];
export function setLanguage(value: Language) {
  language = value;
  document.documentElement.lang = value;
  try {
    localStorage.setItem(LANGUAGE_KEY, value);
  } catch {
    /* optional cache */
  }
  listeners.forEach((listener) => listener());
}
export function useLanguage() {
  return useSyncExternalStore((listener) => {
    listeners.add(listener);
    return () => {
      listeners.delete(listener);
    };
  }, getLanguage);
}

// Accept only application-owned source text. User-entered content is rendered unchanged.
export function t(
  source: string,
  values: Record<string, string | number> = {},
): string {
  const conflictSuffix =
    "Данные обновлены. Проверьте условия и повторите действие.";
  if (source.endsWith(` ${conflictSuffix}`)) {
    return `${t(source.slice(0, -conflictSuffix.length - 1))} ${t(conflictSuffix)}`;
  }
  const lengthError = /^Поле «([^{}]+)»: от (\d+) до (\d+) символов\.$/.exec(
    source,
  );
  const textError = /^Поле «([^{}]+)» должно быть текстом\.$/.exec(source);
  const invalidField = /^Некорректное поле «([^{}]+)»\.$/.exec(source);
  const fields: Record<string, string> = {
    name: "Имя",
    description: "Описание задачи",
    budget: "Бюджет",
    deadline: "Срок",
    scope: "Объём работ",
    result: "Результат",
    revision_terms: "Условия правок",
    price_minor: "Цена",
    version: "Версия",
    attachments_version: "Материалы",
    proposal_version: "Предложение",
    delivery_version: "Результат",
    project_id: "Проект",
    limit: "Размер страницы",
    offset: "Страница",
  };
  if (lengthError)
    return t("Поле «{field}»: от {min} до {max} символов.", {
      field: t(fields[lengthError[1]] || lengthError[1]),
      min: number(Number(lengthError[2])),
      max: number(Number(lengthError[3])),
    });
  if (textError)
    return t("Поле «{field}» должно быть текстом.", {
      field: t(fields[textError[1]] || textError[1]),
    });
  if (invalidField)
    return t("Проверьте поле «{field}».", {
      field: t(fields[invalidField[1]] || invalidField[1]),
    });
  const template = catalogs[language][source] || source;
  return template.replace(/\{(\w+)\}/g, (match, name: string) =>
    Object.prototype.hasOwnProperty.call(values, name)
      ? String(values[name])
      : match,
  );
}
export function apiErrorMessage(error: {
  message: string;
  code: string;
  status: number;
}) {
  if (catalogs.en[error.message] && catalogs.kk[error.message])
    return error.message;
  if (/^Поле «.+»|^Некорректное поле «.+»/.test(error.message))
    return error.message;
  if (error.code === "invalid_input" || error.status === 422)
    return "Проверьте заполненные поля и повторите действие.";
  if (error.status === 401) return "Откройте приложение заново из Telegram.";
  if (error.status === 403) return "Действие недоступно.";
  if (error.status === 404) return "Запись не найдена.";
  if (error.status === 409)
    return "Данные изменились. Обновите страницу и повторите действие.";
  if (error.status === 429)
    return "Слишком много запросов. Повторите немного позже.";
  return "Не удалось выполнить запрос. Повторите позже.";
}
export const number = (value: number, options?: Intl.NumberFormatOptions) =>
  new Intl.NumberFormat(intlLocale(), options).format(value);
export function fileSize(bytes: number) {
  return bytes < 1024
    ? t("{size} Б", { size: number(bytes) })
    : t("{size} КБ", {
        size: number(bytes / 1024, {
          minimumFractionDigits: 1,
          maximumFractionDigits: 1,
        }),
      });
}
