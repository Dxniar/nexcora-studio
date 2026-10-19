import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ReactNode,
  type FormEvent,
} from "react";
import {
  ArrowUpRight,
  ArrowRight,
  ArrowLeft,
  Plus,
  Home,
  Layers3,
  FolderOpen,
  UserRound,
  LayoutDashboard,
  Bell,
  Check,
  CheckCheck,
  Clock3,
  FileText,
  Download,
  Trash2,
  Sun,
  Moon,
  MessageCircle,
  RefreshCw,
  X,
  ChevronRight,
  BotMessageSquare,
  ScanSearch,
  Cable,
  ClipboardList,
  Paperclip,
  ShieldCheck,
  CircleHelp,
  LogOut,
  Languages,
  type LucideIcon,
} from "lucide-react";
import { api, ApiError, download, intent, json, session } from "./api";
import { contactOwner, syncTelegramTheme, telegram } from "./telegram";
import {
  t,
  number,
  fileSize,
  intlLocale,
  getLanguage,
  setLanguage,
  useLanguage,
  apiErrorMessage,
  normalizeLanguage,
  languageNames,
  type Language,
} from "./i18n";
import type {
  Attachments,
  Config,
  Draft,
  DraftFields,
  Notification,
  PageData,
  Project,
  Proposal,
  Service,
  Summary,
  User,
} from "./types";

const statuses: Record<string, string> = {
  new: "Получена",
  discussing: "Обсуждение",
  proposal_sent: "Ждём согласования",
  agreed: "Условия согласованы",
  in_progress: "В работе",
  review: "На приёмке",
  completed: "Завершён",
  closed: "Закрыт",
};
const historyNames: Record<string, string> = {
  submitted: "Обращение отправлено",
  discuss: "Начали обсуждение",
  publish_proposal: "Опубликовано предложение",
  accept_proposal: "Условия согласованы",
  request_changes: "Запрошены изменения условий",
  start: "Работа началась",
  update: "Обновление проекта",
  deliver: "Результат передан",
  accept_delivery: "Результат принят",
  request_revision: "Запрошены правки",
  close: "Обращение закрыто",
};
const defaults: DraftFields = {
  service_id: "",
  name: "",
  description: "",
  budget: "",
  deadline: "",
};
const date = (value: string) =>
  new Intl.DateTimeFormat(intlLocale(), {
    day: "numeric",
    month: "short",
    year: "numeric",
  }).format(new Date(value.length === 10 ? value + "T12:00:00" : value));
const money = (proposal: Proposal) =>
  new Intl.NumberFormat(intlLocale(), {
    style: "currency",
    currency: proposal.currency,
    minimumFractionDigits: 2,
  }).format(proposal.price_minor / 100);
const errorOf = (error: unknown) =>
  error instanceof ApiError
    ? apiErrorMessage(error)
    : error instanceof Error
      ? error.message
      : "Не удалось выполнить действие.";
function BrandMark({ large = false }: { large?: boolean }) {
  return (
    <svg
      className={`brand-symbol${large ? " big" : ""}`}
      viewBox="96 96 320 320"
      aria-hidden="true"
      focusable="false"
    >
      <path d="M142 126L190 126L320 265L320 132C320 128 322 126 326 126L370 126C380.667 126 386 131.333 386 142L386 370C386 380.667 380.667 386 370 386L340 386C336 386 332.667 384.667 330 382L190 228L190 380C190 384 188 386 184 386L142 386C131.333 386 126 380.667 126 370L126 142C126 131.333 131.333 126 142 126Z" />
    </svg>
  );
}
function go(path: string) {
  history.pushState({}, "", path);
  window.dispatchEvent(new PopStateEvent("popstate"));
  window.scrollTo({ top: 0 });
}
function Link({
  to,
  children,
  className = "",
  ...props
}: {
  to: string;
  children: ReactNode;
  className?: string;
  [key: string]: unknown;
}) {
  return (
    <a
      href={to}
      className={className}
      onClick={(e) => {
        if (!e.ctrlKey && !e.metaKey) {
          e.preventDefault();
          go(to);
        }
      }}
      {...props}
    >
      {children}
    </a>
  );
}
function Button({
  children,
  onClick,
  secondary = false,
  danger = false,
  disabled = false,
  type = "button",
  className = "",
}: {
  children: ReactNode;
  onClick?: () => void;
  secondary?: boolean;
  danger?: boolean;
  disabled?: boolean;
  type?: "button" | "submit";
  className?: string;
}) {
  return (
    <button
      type={type}
      className={`button ${secondary ? "secondary" : ""} ${danger ? "danger" : ""} ${className}`}
      onClick={onClick}
      disabled={disabled}
    >
      {children}
    </button>
  );
}
function Alert({
  message,
  retry,
  children,
}: {
  message: string;
  retry?: () => void;
  children?: ReactNode;
}) {
  return (
    <div className="alert" role="alert">
      <div>{t(message)}</div>
      {retry && (
        <button onClick={retry}>
          <RefreshCw size={16} />
          {t("Повторить")}
        </button>
      )}
      {children}
    </div>
  );
}
function Loading() {
  return (
    <div className="loading" role="status" aria-label={t("Загрузка")}>
      <span />
      <span />
      <span />
    </div>
  );
}
function Empty({
  title,
  children,
  icon = <FolderOpen size={28} />,
}: {
  title: string;
  children: ReactNode;
  icon?: ReactNode;
}) {
  return (
    <div className="empty">
      <div className="empty-icon">{icon}</div>
      <h3>{t(title)}</h3>
      <div className="muted">{children}</div>
    </div>
  );
}
function Heading({
  eyebrow,
  title,
  description,
  action,
  translateTitle = true,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  action?: ReactNode;
  translateTitle?: boolean;
}) {
  return (
    <div className="page-heading">
      <div>
        {eyebrow && <div className="eyebrow">{t(eyebrow)}</div>}
        <h1>{translateTitle ? t(title) : title}</h1>
        {description && <p>{t(description)}</p>}
      </div>
      {action}
    </div>
  );
}
function Field({
  label,
  children,
  hint,
}: {
  label: string;
  children: ReactNode;
  hint?: string;
}) {
  return (
    <label className="field">
      <span>{t(label)}</span>
      {children}
      {hint && <small>{t(hint)}</small>}
    </label>
  );
}
function Badge({ project }: { project: Project }) {
  return (
    <span className={`badge status-${project.status}`}>
      <span />
      {t(statuses[project.status] || project.status_label)}
    </span>
  );
}
function useResource<T>(path: string | null) {
  const [data, setData] = useState<T | null>(null),
    [error, setError] = useState(""),
    [loading, setLoading] = useState(true);
  const sequence = useRef(0);
  const load = useCallback(async () => {
    if (!path) {
      setLoading(false);
      return;
    }
    const n = ++sequence.current;
    setLoading(true);
    setError("");
    try {
      const result = await api<T>(path);
      if (n === sequence.current) setData(result);
    } catch (e) {
      if (n === sequence.current) setError(errorOf(e));
    } finally {
      if (n === sequence.current) setLoading(false);
    }
  }, [path]);
  useEffect(() => {
    setData(null);
    void load();
    return () => {
      sequence.current++;
    };
  }, [load]);
  return { data, setData, error, loading, load };
}
function useDraft(user: User | null) {
  const [draft, setDraft] = useState<Draft | null>(null),
    [fields, setFields] = useState<DraftFields>(defaults),
    [status, setStatus] = useState("Загрузка черновика…"),
    [error, setError] = useState(""),
    [conflict, setConflict] = useState(false);
  const current = useRef<Draft | null>(null),
    local = useRef<DraftFields>(defaults),
    saved = useRef(""),
    blocked = useRef(false),
    running = useRef<Promise<boolean> | null>(null);
  const load = useCallback(async (replace = true) => {
    const d = await api<Draft>("/me/draft");
    current.current = d;
    setDraft(d);
    if (replace) {
      const f = { ...defaults, ...d.fields };
      local.current = f;
      setFields(f);
      saved.current = JSON.stringify(f);
      blocked.current = false;
      setConflict(false);
      setError("");
      setStatus("Черновик сохранён");
    }
    return d;
  }, []);
  useEffect(() => {
    if (user)
      void load().catch((e) => {
        setError(errorOf(e));
        setStatus("Не удалось загрузить");
      });
  }, [user?.id, load]);
  const change = (name: keyof DraftFields, value: string) => {
    const f = { ...local.current, [name]: value };
    local.current = f;
    setFields(f);
    setStatus("Есть несохранённые изменения");
  };
  const save = useCallback(async (): Promise<boolean> => {
    if (blocked.current || !current.current) return false;
    if (running.current) {
      await running.current;
      if (blocked.current) return false;
      return save();
    }
    const snapshot = { ...local.current };
    const serialized = JSON.stringify(snapshot);
    if (serialized === saved.current) return true;
    setStatus("Сохраняем…");
    setError("");
    running.current = (async () => {
      try {
        const d = await api<Draft>(
          "/me/draft",
          json("PUT", {
            expected_version: current.current!.version,
            fields: snapshot,
          }),
        );
        current.current = d;
        setDraft(d);
        saved.current = serialized;
        setStatus(
          JSON.stringify(local.current) === serialized
            ? "Черновик сохранён"
            : "Есть несохранённые изменения",
        );
        return true;
      } catch (e) {
        if (e instanceof ApiError && e.status === 409) {
          blocked.current = true;
          setConflict(true);
          setError(
            "Черновик изменился в другом окне. Ваш текст остался на экране. Проверьте актуальную версию перед сохранением.",
          );
          try {
            await load(false);
          } catch {
            /* next explicit attempt can reload */
          }
        } else setError(errorOf(e));
        setStatus("Изменения не сохранены");
        return false;
      } finally {
        running.current = null;
      }
    })();
    const result = await running.current;
    if (result && JSON.stringify(local.current) !== saved.current)
      return save();
    return result;
  }, [load]);
  useEffect(() => {
    if (!draft || blocked.current || JSON.stringify(fields) === saved.current)
      return;
    const timer = setTimeout(() => {
      void save();
    }, 650);
    return () => clearTimeout(timer);
  }, [fields, draft?.version, save]);
  const reconcile = async () => {
    try {
      await load(false);
      blocked.current = false;
      setConflict(false);
      setError("");
      await save();
    } catch (e) {
      setError(errorOf(e));
    }
  };
  return {
    draft,
    fields,
    status,
    error,
    conflict,
    change,
    save,
    load,
    reconcile,
  };
}
type DraftController = ReturnType<typeof useDraft>;

export function App() {
  const language = useLanguage();
  const [path, setPath] = useState(location.pathname),
    [user, setUser] = useState<User | null>(null),
    [boot, setBoot] = useState(true),
    [authError, setAuthError] = useState(""),
    [expired, setExpired] = useState(false),
    [offline, setOffline] = useState(!navigator.onLine),
    [theme, setTheme] = useState("light"),
    [languageSaving, setLanguageSaving] = useState(false),
    [languageError, setLanguageError] = useState("");
  const languageRequest = useRef(false);
  const navigationRef = useRef<HTMLElement>(null);
  useEffect(() => {
    const nav = navigationRef.current;
    if (!nav) return;
    const measure = () => {
      if (getComputedStyle(nav).position === "fixed") {
        document.documentElement.style.setProperty(
          "--nav-clearance",
          `${Math.ceil(nav.getBoundingClientRect().height)}px`,
        );
      } else document.documentElement.style.removeProperty("--nav-clearance");
    };
    const observer = new ResizeObserver(measure);
    observer.observe(nav);
    window.addEventListener("resize", measure);
    measure();
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", measure);
      document.documentElement.style.removeProperty("--nav-clearance");
    };
  }, [user?.id]);
  const config = useResource<Config>("/config");
  const catalog = useResource<{ items: Service[] }>("/catalog");
  const draft = useDraft(user);
  const login = useCallback(async () => {
    setBoot(true);
    setAuthError("");
    try {
      let me: User;
      if (session.get()) me = await api<User>("/me");
      else {
        const initData = telegram()?.initData;
        if (!initData) {
          setBoot(false);
          return;
        }
        const result = await api<{ access_token: string; user: User }>(
          "/auth/telegram",
          json("POST", { init_data: initData }),
        );
        session.set(result.access_token);
        me = result.user;
      }
      setUser(me);
      setLanguage(normalizeLanguage(me.language_code));
      setExpired(false);
      if (me.is_owner && location.pathname === "/") go("/owner");
    } catch (e) {
      setAuthError(errorOf(e));
    } finally {
      setBoot(false);
    }
  }, []);
  useEffect(() => {
    syncTelegramTheme();
    setTheme(document.documentElement.dataset.theme || "light");
    const app = telegram();
    app?.ready();
    app?.expand();
    app?.onEvent("themeChanged", syncTelegramTheme);
    app?.onEvent("safeAreaChanged", syncTelegramTheme);
    app?.onEvent("contentSafeAreaChanged", syncTelegramTheme);
    void login();
    const route = () => setPath(location.pathname),
      online = () => setOffline(!navigator.onLine),
      end = () => {
        setUser(null);
        setExpired(true);
      };
    window.addEventListener("popstate", route);
    window.addEventListener("online", online);
    window.addEventListener("offline", online);
    window.addEventListener("nexcora:expired", end);
    return () => {
      window.removeEventListener("popstate", route);
      window.removeEventListener("online", online);
      window.removeEventListener("offline", online);
      window.removeEventListener("nexcora:expired", end);
      app?.offEvent("themeChanged", syncTelegramTheme);
      app?.offEvent("safeAreaChanged", syncTelegramTheme);
      app?.offEvent("contentSafeAreaChanged", syncTelegramTheme);
    };
  }, [login]);
  const ownerView = path.startsWith("/owner");
  useEffect(() => {
    const app = telegram(),
      back = () => go(ownerView ? "/owner/projects" : "/projects");
    const detail = /\/projects\/\d+$/.test(path) || path === "/draft";
    if (detail) {
      app?.BackButton.show();
      app?.BackButton.onClick(back);
    } else app?.BackButton.hide();
    return () => app?.BackButton.offClick(back);
  }, [path, ownerView]);
  const toggleTheme = () => {
    const value =
      document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    localStorage.setItem("nexcora.theme", value);
    document.documentElement.dataset.theme = value;
    setTheme(value);
  };
  const changeLanguage = async (value: Language) => {
    if (languageRequest.current || value === getLanguage()) return;
    const previous = getLanguage();
    setLanguageError("");
    setLanguage(value);
    if (!user) return;
    const requestToken = session.get();
    languageRequest.current = true;
    setLanguageSaving(true);
    try {
      const updated = await api<User>(
        "/me/language",
        json("PUT", { language_code: value }),
      );
      if (session.get() !== requestToken) return;
      setUser(updated);
      setLanguage(normalizeLanguage(updated.language_code));
    } catch {
      if (session.get() !== requestToken) return;
      setLanguage(previous);
      setLanguageError("Не удалось сохранить язык. Повторите попытку.");
    } finally {
      languageRequest.current = false;
      setLanguageSaving(false);
    }
  };
  const logout = async () => {
    await api("/auth/logout", json("POST", {}));
    session.clear();
    setUser(null);
    setExpired(true);
  };
  const nav = ownerView
    ? [
        { path: "/owner", label: "Обзор", icon: LayoutDashboard },
        { path: "/owner/projects", label: "Проекты", icon: FolderOpen },
        { path: "/owner/notifications", label: "Уведомления", icon: Bell },
      ]
    : [
        {
          path: user?.is_owner ? "/client" : "/",
          label: "Главная",
          icon: Home,
        },
        { path: "/services", label: "Услуги", icon: Layers3 },
        { path: "/projects", label: "Мои проекты", icon: FolderOpen },
        { path: "/profile", label: "Профиль", icon: UserRound },
      ];
  let content: ReactNode;
  const services = catalog.data?.items || [];
  if (boot) content = <Loading />;
  else if (!user)
    content = (
      <div className="auth-card">
        <BrandMark large />
        <span className="eyebrow">NEXCORA STUDIO</span>
        <h1>{expired ? t("Сессия завершена") : t("Продолжим в Telegram")}</h1>
        <p>
          {t(
            "Откройте Mini App из меню бота. Так мы сможем безопасно сохранить вашу задачу и показать только ваши проекты.",
          )}
        </p>
        {authError && <Alert message={authError} retry={() => void login()} />}
        <p className="muted">
          {expired
            ? t("Закройте и заново откройте приложение в Telegram.")
            : t("Вход выполняется через подтверждённый Telegram-аккаунт.")}
        </p>
      </div>
    );
  else if (ownerView && !user.is_owner)
    content = (
      <Empty title={t("Кабинет владельца недоступен")} icon={<ShieldCheck />}>
        <p>{t("Ваши проекты доступны в клиентском кабинете.")}</p>
        <Link to="/projects" className="text-link">
          {t("Открыть мои проекты")} <ArrowRight size={16} />
        </Link>
      </Empty>
    );
  else if (path === "/draft")
    content = <DraftPage controller={draft} services={services} />;
  else if (/^\/(owner\/)?projects\/\d+$/.test(path))
    content = (
      <ProjectPage
        id={Number(path.split("/").pop())}
        owner={ownerView}
        ownerUsername={config.data?.owner_username || ""}
      />
    );
  else if (path === "/services")
    content = (
      <Services
        services={services}
        loading={catalog.loading}
        error={catalog.error}
        retry={() => void catalog.load()}
        choose={(id) => {
          draft.change("service_id", id);
          go("/draft");
        }}
      />
    );
  else if (path === "/profile")
    content = (
      <Profile
        user={user}
        setUser={setUser}
        logout={logout}
        ownerUsername={config.data?.owner_username || ""}
      />
    );
  else if (path === "/owner/notifications") content = <Notifications />;
  else if (path === "/owner") content = <OwnerHome />;
  else if (path === "/projects" || path === "/owner/projects")
    content = <Projects owner={ownerView} />;
  else if (path === "/" || path === "/client")
    content = <ClientHome user={user} start={() => go("/draft")} />;
  else
    content = (
      <Empty title={t("Страница не найдена")}>
        <Link to={user.is_owner ? "/owner" : "/"} className="text-link">
          {t("На главную")} <ArrowRight size={16} />
        </Link>
      </Empty>
    );
  return (
    <div
      className={`shell ${ownerView ? "owner-shell" : ""} ${user ? "has-session" : ""}`}
    >
      <a className="skip-link" href="#main">
        {t("Перейти к содержимому")}
      </a>
      <header className="header">
        <Link
          to={ownerView ? "/owner" : user?.is_owner ? "/client" : "/"}
          className="brand"
        >
          <BrandMark />
          <span>
            Nexcora<span className="brand-caption">STUDIO</span>
          </span>
        </Link>
        <div className="header-actions">
          <label className="language-picker">
            <Languages size={18} aria-hidden="true" />
            <span className="sr-only">{t("Выбор языка")}</span>
            <select
              aria-label={t("Выбор языка")}
              aria-busy={languageSaving}
              value={language}
              disabled={languageSaving || boot}
              onChange={(event) =>
                void changeLanguage(event.target.value as Language)
              }
            >
              {(Object.keys(languageNames) as Language[]).map((code) => (
                <option key={code} value={code} lang={code}>
                  {languageNames[code]}
                </option>
              ))}
            </select>
          </label>
          {user?.is_owner && (
            <Link className="view-switch" to={ownerView ? "/client" : "/owner"}>
              {ownerView ? t("Клиентский вид") : t("Кабинет владельца")}
              <ArrowUpRight size={14} />
            </Link>
          )}
          <button
            className="icon-button"
            aria-label={t("Переключить тему")}
            onClick={toggleTheme}
          >
            {theme === "dark" ? <Sun size={19} /> : <Moon size={19} />}
          </button>
          {user && (
            <span className="avatar">{user.first_name.slice(0, 1) || "N"}</span>
          )}
        </div>
      </header>
      {languageSaving && (
        <p className="language-state" role="status">
          {t("Сохраняем язык…")}
        </p>
      )}
      {languageError && <Alert message={languageError} />}
      {offline && (
        <div className="offline" role="status">
          {t("Нет соединения. Изменения ещё не отправлены.")}
        </div>
      )}
      <div className={`workspace ${user ? "has-navigation" : ""}`}>
        {user && (
          <nav
            ref={navigationRef}
            className="bottom-nav"
            aria-label={t("Основная навигация")}
          >
            {nav.map((item) => {
              const active =
                path === item.path ||
                (item.path.endsWith("projects") &&
                  path.startsWith(item.path + "/"));
              return (
                <Link
                  to={item.path}
                  key={item.path}
                  className={active ? "active" : ""}
                  aria-current={active ? "page" : undefined}
                >
                  <item.icon size={21} />
                  <span>{t(item.label)}</span>
                </Link>
              );
            })}
          </nav>
        )}
        <main id="main" className="main" key={user?.id || "auth"} tabIndex={-1}>
          {content}
        </main>
      </div>
      <footer className="footer">
        <span>Nexcora Studio</span>
        <span>{t("Идея. Диалог. Результат.")}</span>
      </footer>
    </div>
  );
}

function ClientHome({ user, start }: { user: User; start: () => void }) {
  const projects = useResource<PageData<Project>>("/me/projects");
  const activeProjects = useResource<PageData<Project>>(
    "/me/projects?active_only=true",
  );
  const welcome = (
    <div className="welcome">
      {t("Рады видеть вас, {name}", { name: user.first_name })}
      <span className="tiny-dot" />
    </div>
  );
  if (projects.loading || (!projects.data && !projects.error))
    return (
      <>
        {welcome}
        <Loading />
      </>
    );
  if (projects.error)
    return (
      <>
        {welcome}
        <Alert
          message={projects.error}
          retry={() => {
            void projects.load();
            void activeProjects.load();
          }}
        />
      </>
    );
  if (projects.data!.total > 0)
    return (
      <div className="client-workspace">
        {welcome}
        <Heading
          title={t("Ваши проекты")}
          action={
            <Button onClick={start}>
              <Plus size={17} /> {t("Новая заявка")}
            </Button>
          }
        />
        <section
          className="client-projects"
          aria-labelledby="active-projects-heading"
        >
          <div className="section-title">
            <h2 id="active-projects-heading">{t("Активные проекты")}</h2>
            <Link to="/projects" className="text-link">
              {t("Все проекты")} <ArrowRight size={16} />
            </Link>
          </div>
          {activeProjects.loading ? (
            <Loading />
          ) : activeProjects.error ? (
            <Alert
              message={activeProjects.error}
              retry={() => void activeProjects.load()}
            />
          ) : activeProjects.data?.items.length ? (
            <div className="project-grid">
              {activeProjects.data.items.map((p) => (
                <ProjectCard key={p.id} project={p} />
              ))}
            </div>
          ) : (
            <Empty title={t("Нет активных проектов")}>
              <p>
                {t("Завершённые и закрытые проекты доступны в общем списке.")}
              </p>
            </Empty>
          )}
        </section>
      </div>
    );
  return (
    <>
      {welcome}
      <section className="hero">
        <div className="hero-copy">
          <span className="eyebrow">
            <span className="tiny-dot" /> {t("Клиентский кабинет")}
          </span>
          <h1>{t("Расскажите о вашей задаче")}</h1>
          <p>
            {t(
              "Опишите задачу и приложите материалы. Обсудим объём, стоимость и сроки. Условия, ход работы и результат будут доступны в вашем кабинете.",
            )}
          </p>
          <Button onClick={start}>
            {t("Обсудить проект")} <ArrowUpRight size={19} />
          </Button>
          <div className="hero-note">
            <ShieldCheck size={15} /> {t("Условия согласуем до начала работы")}
          </div>
        </div>
        <aside className="hero-guide" aria-labelledby="workflow-heading">
          <h2 id="workflow-heading">{t("Как проходит работа")}</h2>
          <ol>
            {[
              [t("Заявка"), t("Вы описываете задачу и добавляете материалы.")],
              [
                t("Условия"),
                t("Согласуем объём, стоимость и срок выполнения."),
              ],
              [
                t("Результат"),
                t("Вы проверяете работу и принимаете результат."),
              ],
            ].map(([title, text]) => (
              <li key={title}>
                <strong>{title}</strong>
                <p>{text}</p>
              </li>
            ))}
          </ol>
        </aside>
      </section>
      <div className="section-title">
        <h2>{t("Ваши проекты")}</h2>
        <Link to="/projects" className="text-link">
          {t("Все проекты")} <ArrowRight size={16} />
        </Link>
      </div>
      <div className="start-card">
        <div className="empty-icon">
          <FolderOpen size={24} />
        </div>
        <div>
          <h3>{t("Здесь начнётся ваш первый проект")}</h3>
          <p>{t("Задача, условия и история работы — в одном месте.")}</p>
        </div>
        <button
          className="circle-button"
          aria-label={t("Создать обращение")}
          onClick={start}
        >
          <Plus />
        </button>
      </div>
      <div className="quiet-note">
        <MessageCircle size={20} />
        <p>
          {t(
            "Не знаете, с чего начать? Просто опишите идею — детали обсудим вместе.",
          )}
        </p>
      </div>
    </>
  );
}
function Services({
  services,
  loading,
  error,
  retry,
  choose,
}: {
  services: Service[];
  loading: boolean;
  error: string;
  retry: () => void;
  choose: (id: string) => void;
}) {
  const icons: Record<string, LucideIcon> = {
    bot: BotMessageSquare,
    parser: ScanSearch,
    api: Cable,
    other: ClipboardList,
  };
  return (
    <>
      <Heading
        eyebrow={t("НАПРАВЛЕНИЯ")}
        title={t("Что создадим?")}
        description={t(
          "Выберите направление. Детали и возможность реализации обсудим по вашей задаче.",
        )}
      />
      {loading ? (
        <Loading />
      ) : error ? (
        <Alert message={error} retry={retry} />
      ) : (
        <div className="services-grid">
          {services.map((s) => {
            const Icon = icons[s.id] || ClipboardList;
            return (
              <article className="service-card" key={s.id}>
                <div className="service-top">
                  <span className="service-icon">
                    <Icon size={27} />
                  </span>
                  <h2>{t(s.title)}</h2>
                </div>
                <p>{t(s.summary)}</p>
                <ul>
                  {s.examples.map((e) => (
                    <li key={e}>
                      <Check size={14} />
                      {t(e)}
                    </li>
                  ))}
                </ul>
                <Button secondary onClick={() => choose(s.id)}>
                  {t("Обсудить задачу")} <ArrowUpRight size={17} />
                </Button>
              </article>
            );
          })}
        </div>
      )}
      <div className="quiet-note">
        <CircleHelp size={20} />
        <p>
          {t(
            "Стоимость и срок появятся в индивидуальном предложении после обсуждения.",
          )}
        </p>
      </div>
    </>
  );
}
function projectServiceTitle(project: Project) {
  const canonical: Record<string, string> = {
    bot: "Telegram-бот",
    parser: "Парсер",
    api: "API-интеграция",
    other: "Другая задача",
  };
  const source = project.service_id ? canonical[project.service_id] : undefined;
  return source && project.service_title === source
    ? t(source)
    : project.service_title;
}
function ProjectCard({
  project: p,
  owner = false,
}: {
  project: Project;
  owner?: boolean;
}) {
  return (
    <Link
      to={`${owner ? "/owner" : ""}/projects/${p.id}`}
      className="project-card"
    >
      <div className="card-meta">
        <span>{t("ПРОЕКТ #{id}", { id: number(p.id) })}</span>
        <span>{date(p.created_at)}</span>
      </div>
      <div className="project-title">
        <h3>{projectServiceTitle(p)}</h3>
        <ArrowUpRight size={19} />
      </div>
      {owner && <p className="client-name">{p.name}</p>}
      <p className="project-excerpt">{p.description}</p>
      <Badge project={p} />
      <div className="next-step">
        <Clock3 size={14} />
        <span>{t(p.next_action)}</span>
      </div>
    </Link>
  );
}
function Projects({ owner }: { owner: boolean }) {
  const [offset, setOffset] = useState(0),
    [filter, setFilter] = useState(
      owner && new URLSearchParams(location.search).get("attention") === "true"
        ? "attention"
        : new URLSearchParams(location.search).get("status") || "",
    ),
    [search, setSearch] = useState(""),
    [query, setQuery] = useState("");
  const resource = useResource<PageData<Project>>(
    `${owner ? "/owner" : "/me"}/projects?offset=${offset}${owner && filter === "attention" ? "&attention=true" : filter ? `&status=${filter}` : ""}${query ? `&search=${encodeURIComponent(query)}` : ""}`,
  );
  return (
    <>
      <Heading
        eyebrow={owner ? t("РАБОЧИЙ КАБИНЕТ") : t("ЛИЧНЫЙ КАБИНЕТ")}
        title={owner ? t("Проекты студии") : t("Мои проекты")}
        description={
          owner
            ? t("Следующий шаг по каждой задаче — на виду.")
            : t("От первого сообщения до принятого результата.")
        }
        action={
          !owner && (
            <Button onClick={() => go("/draft")}>
              <Plus size={17} />
              {t("Новое обращение")}
            </Button>
          )
        }
      />
      {owner && (
        <div className="filters">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              setQuery(search);
              setOffset(0);
            }}
          >
            <input
              aria-label={t("Поиск по номеру или имени")}
              placeholder={t("Номер проекта или имя")}
              value={search}
              maxLength={100}
              onChange={(e) => setSearch(e.target.value)}
            />
            <Button secondary type="submit">
              {t("Найти")}
            </Button>
          </form>
          <select
            aria-label={t("Этап проекта")}
            value={filter}
            onChange={(e) => {
              setFilter(e.target.value);
              setOffset(0);
            }}
          >
            <option value="">{t("Все этапы")}</option>
            <option value="attention">{t("Требуют внимания")}</option>
            {Object.entries(statuses).map(([key, text]) => (
              <option key={key} value={key}>
                {t(text)}
              </option>
            ))}
          </select>
        </div>
      )}
      {resource.loading ? (
        <Loading />
      ) : resource.error ? (
        <Alert message={resource.error} retry={() => void resource.load()} />
      ) : resource.data?.items.length ? (
        <>
          <div className="project-grid">
            {resource.data.items.map((p) => (
              <ProjectCard key={p.id} project={p} owner={owner} />
            ))}
          </div>
          <div className="pagination">
            <Button
              secondary
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - 10))}
            >
              <ArrowLeft size={16} /> {t("Назад")}
            </Button>
            <span>
              {t("{from}–{to} из {total}", {
                from: number(offset + 1),
                to: number(Math.min(offset + 10, resource.data.total)),
                total: number(resource.data.total),
              })}
            </span>
            <Button
              secondary
              disabled={offset + 10 >= resource.data.total}
              onClick={() => setOffset(offset + 10)}
            >
              {t("Далее")} <ArrowRight size={16} />
            </Button>
          </div>
        </>
      ) : (
        <Empty
          title={
            query || filter ? t("Ничего не найдено") : t("Пока нет проектов")
          }
        >
          <p>
            {owner
              ? t("Новые обращения появятся здесь.")
              : t(
                  "Расскажите о задаче — сохраним детали и обсудим следующий шаг.",
                )}
          </p>
          {!owner && (
            <Button onClick={() => go("/draft")}>
              {t("Обсудить проект")} <ArrowUpRight size={17} />
            </Button>
          )}
        </Empty>
      )}
    </>
  );
}
function FileList({
  attachments,
  editable = false,
  refresh,
}: {
  attachments: Attachments;
  editable?: boolean;
  refresh?: () => Promise<unknown>;
}) {
  const [error, setError] = useState(""),
    [busy, setBusy] = useState("");
  const remove = async (id: string) => {
    setBusy(id);
    setError("");
    try {
      await api(`/attachments/${id}`, { method: "DELETE" });
      await refresh?.();
    } catch (e) {
      setError(errorOf(e));
    } finally {
      setBusy("");
    }
  };
  const get = async (id: string, name: string) => {
    setError("");
    try {
      await download(id, name);
    } catch (e) {
      setError(errorOf(e));
    }
  };
  return (
    <>
      {attachments.items.map((file) => (
        <div className="file-row" key={file.id}>
          <FileText size={20} />
          <div>
            <strong>{file.filename}</strong>
            <small>
              {fileSize(file.size_bytes)} ·{" "}
              {file.state === "ready"
                ? t("Файл загружен")
                : file.state === "delete_pending"
                  ? t("Удаление ожидает очистки")
                  : file.state === "reserved"
                    ? t("Загрузка не завершена")
                    : file.state === "rejected"
                      ? t("Файл отклонён")
                      : t("Файл обрабатывается")}
              {file.error_code ? t(" · Ошибка загрузки") : ""}
            </small>
          </div>
          {file.state === "ready" && (
            <button
              className="icon-button"
              aria-label={t("Скачать {filename}", { filename: file.filename })}
              onClick={() => void get(file.id, file.filename)}
            >
              <Download size={18} />
            </button>
          )}
          {editable && file.state !== "delete_pending" && (
            <button
              className="icon-button"
              aria-label={t("Удалить {filename}", { filename: file.filename })}
              disabled={busy === file.id}
              onClick={() => void remove(file.id)}
            >
              <Trash2 size={18} />
            </button>
          )}
        </div>
      ))}
      {error && <Alert message={error} />}
    </>
  );
}
function DraftPage({
  controller: d,
  services,
}: {
  controller: DraftController;
  services: Service[];
}) {
  const [review, setReview] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [upload, setUpload] = useState<{
      filename?: string;
      done?: boolean;
    } | null>(null),
    [retry, setRetry] = useState<null | (() => Promise<void>)>(null),
    [additionalOpen, setAdditionalOpen] = useState(
      Boolean(d.draft?.fields.budget || d.draft?.fields.deadline),
    );
  const additionalDraftId = useRef(d.draft?.id);
  useEffect(() => {
    if (!d.draft || additionalDraftId.current === d.draft.id) return;
    additionalDraftId.current = d.draft.id;
    setAdditionalOpen(
      Boolean(d.draft.fields.budget || d.draft.fields.deadline),
    );
  }, [d.draft]);
  const uploadFiles = async (inputFiles: globalThis.FileList | null) => {
    const files = Array.from(inputFiles || []);
    if (!files.length) return;
    setError("");
    setBusy(true);
    try {
      if (!(await d.save())) return;
      let current = await d.load(false);
      for (const file of files) {
        if (current.attachments.count >= 5)
          throw new Error("Можно приложить не больше 5 файлов.");
        if (!/\.(txt|pdf|docx?|jpe?g|png|webp)$/i.test(file.name))
          throw new Error("Принимаются TXT, PDF, DOC/DOCX, JPG, PNG и WebP.");
        if (file.size === 0 || file.size > 10_485_760)
          throw new Error("Размер файла должен быть от 1 байта до 10 МиБ.");
        setUpload({ filename: file.name });
        const reserved = await intent<{ id: string }>("/me/draft/attachments", {
          filename: file.name,
          size_bytes: file.size,
          expected_attachments_version: current.attachments.version,
        });
        await api(`/attachments/${reserved.id}/content`, {
          method: "PUT",
          body: file,
          headers: { "Content-Type": "application/octet-stream" },
        });
        current = await d.load(false);
      }
      setUpload({ done: true });
    } catch (e) {
      setError(errorOf(e));
      await d.load(false).catch(() => undefined);
    } finally {
      setBusy(false);
    }
  };
  const check = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      if (await d.save()) setReview(true);
    } finally {
      setBusy(false);
    }
  };
  const send = async () => {
    if (!d.draft) return;
    const body = {
      draft_id: d.draft.id,
      expected_version: d.draft.version,
      attachments_version: d.draft.attachments.version,
    };
    const perform = async () => {
      setBusy(true);
      setError("");
      try {
        const project = await intent<Project>("/me/draft/submit", body);
        setRetry(null);
        go(`/projects/${project.id}`);
        await d.load();
      } catch (e) {
        setError(errorOf(e));
        if (e instanceof ApiError && e.status === 0) setRetry(() => perform);
        else if (e instanceof ApiError && e.status === 409) {
          setReview(false);
          await d.load(false);
        }
      } finally {
        setBusy(false);
      }
    };
    await perform();
  };
  if (!d.draft)
    return d.error ? (
      <Alert message={d.error} retry={() => void d.load()} />
    ) : (
      <Loading />
    );
  return (
    <>
      <button
        className="back-link"
        onClick={() => (review ? setReview(false) : go("/services"))}
      >
        <ArrowLeft size={16} />
        {review ? t("К редактированию") : t("К услугам")}
      </button>
      <Heading
        eyebrow={review ? t("ШАГ 02 / ПРОВЕРКА") : t("ШАГ 01 / ВАША ЗАДАЧА")}
        title={review ? t("Всё верно?") : t("Новая заявка")}
        description={
          review
            ? t(
                "После отправки исполнитель изучит детали. Условия согласуем отдельно.",
              )
            : t(
                "Расскажите, что хотите сделать. Черновик сохраняется автоматически.",
              )
        }
      />
      <div className="form-layout form-layout--compact">
        <section className="panel">
          {!review ? (
            <form onSubmit={(e) => void check(e)}>
              <Field label={t("Услуга")}>
                <select
                  required
                  value={d.fields.service_id}
                  onChange={(e) => d.change("service_id", e.target.value)}
                >
                  <option value="">{t("Выберите направление")}</option>
                  {services.map((s) => (
                    <option key={s.id} value={s.id}>
                      {t(s.title)}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label={t("Ваше имя")}>
                <input
                  required
                  minLength={2}
                  maxLength={80}
                  autoComplete="name"
                  value={d.fields.name}
                  onChange={(e) => d.change("name", e.target.value)}
                  placeholder={t("Как к вам обращаться")}
                />
              </Field>
              <Field
                label={t("Описание задачи")}
                hint={t(
                  "Какая задача, для кого и какой результат нужен? От 10 до 2 000 символов.",
                )}
              >
                <textarea
                  required
                  minLength={10}
                  maxLength={2000}
                  rows={6}
                  value={d.fields.description}
                  onChange={(e) => d.change("description", e.target.value)}
                  placeholder={t(
                    "Например: бот для записи на занятия с анкетой и уведомлениями…",
                  )}
                />
              </Field>
              <details
                className="optional-fields"
                open={additionalOpen}
                onToggle={(e) => setAdditionalOpen(e.currentTarget.open)}
              >
                <summary>{t("Дополнительно")}</summary>
                <div className="field-grid">
                  <Field
                    label={t("Ориентир по бюджету")}
                    hint={t("Необязательно")}
                  >
                    <input
                      maxLength={80}
                      value={d.fields.budget}
                      onChange={(e) => d.change("budget", e.target.value)}
                      placeholder={t("Сумма и валюта")}
                    />
                  </Field>
                  <Field label={t("Желаемый срок")} hint={t("Необязательно")}>
                    <input
                      maxLength={80}
                      value={d.fields.deadline}
                      onChange={(e) => d.change("deadline", e.target.value)}
                      placeholder={t("Когда нужен результат")}
                    />
                  </Field>
                </div>
              </details>
              <div className="upload-area">
                <Paperclip size={21} />
                <div>
                  <strong>{t("Материалы к задаче")}</strong>
                  <p>
                    {t(
                      "До 5 файлов по 10 МиБ: TXT, PDF, DOC/DOCX, JPG, PNG, WebP.",
                    )}
                  </p>
                </div>
                <label className={`upload-button ${busy ? "disabled" : ""}`}>
                  {t("Добавить")}
                  <input
                    aria-label={t("Приложить файлы")}
                    type="file"
                    multiple
                    accept=".txt,.pdf,.doc,.docx,.jpg,.jpeg,.png,.webp"
                    disabled={
                      busy || d.conflict || d.draft.attachments.count >= 5
                    }
                    onChange={(e) => {
                      void uploadFiles(e.target.files);
                      e.target.value = "";
                    }}
                  />
                </label>
              </div>
              {upload && (
                <p role="status" className="save-state">
                  {upload.done
                    ? t("Файл загружен")
                    : t("Загружаем {filename}…", {
                        filename: upload.filename || "",
                      })}
                </p>
              )}
              <FileList
                attachments={d.draft.attachments}
                editable
                refresh={() => d.load(false)}
              />
              {d.draft.attachments.items.some(
                (f) => f.state === "delete_pending",
              ) && (
                <div className="inline-note">
                  {t(
                    "Удаление выполняется в фоне. Обновите список после завершения очистки.",
                  )}{" "}
                  <button type="button" onClick={() => void d.load(false)}>
                    {t("Обновить файлы")}
                  </button>
                </div>
              )}
              <p className="draft-privacy">
                <ShieldCheck size={17} />
                <span>{t("Материалы видите вы и исполнитель.")}</span>
              </p>
              <div className="form-bottom">
                <span className="save-state" role="status">
                  {d.status === "Черновик сохранён" ? (
                    <CheckCheck size={16} />
                  ) : (
                    <Clock3 size={16} />
                  )}{" "}
                  {t(d.status)}
                </span>
                <Button
                  type="submit"
                  disabled={
                    busy ||
                    d.conflict ||
                    d.draft.attachments.items.some((f) => f.state !== "ready")
                  }
                >
                  {t("Проверить заявку")} <ArrowRight size={17} />
                </Button>
              </div>
            </form>
          ) : (
            <>
              <div className="review-eyebrow">{t("ОБРАЩЕНИЕ")}</div>
              <h2>
                {t(
                  services.find((s) => s.id === d.fields.service_id)?.title ||
                    "",
                )}
              </h2>
              <dl className="details">
                <div>
                  <dt>{t("Имя")}</dt>
                  <dd>{d.fields.name}</dd>
                </div>
                <div>
                  <dt>{t("Задача")}</dt>
                  <dd className="preserve">{d.fields.description}</dd>
                </div>
                {d.fields.budget && (
                  <div>
                    <dt>{t("Пожелание по бюджету")}</dt>
                    <dd>{d.fields.budget}</dd>
                  </div>
                )}
                {d.fields.deadline && (
                  <div>
                    <dt>{t("Пожелание по сроку")}</dt>
                    <dd>{d.fields.deadline}</dd>
                  </div>
                )}
              </dl>
              <FileList attachments={d.draft.attachments} />
              <p className="draft-privacy">
                <ShieldCheck size={17} />
                <span>{t("Материалы видите вы и исполнитель.")}</span>
              </p>
              <div className="inline-note">
                <ShieldCheck size={18} />{" "}
                {t(
                  "Обращение не означает согласование стоимости или оплату. Сначала обсудим объём и условия.",
                )}
              </div>
              <Button disabled={busy || !!retry} onClick={() => void send()}>
                {t("Отправить заявку")} <ArrowUpRight size={18} />
              </Button>
            </>
          )}
          {d.error && (
            <Alert message={d.error}>
              {d.conflict ? (
                <div className="alert-actions">
                  <button onClick={() => void d.load()}>
                    {t("Загрузить актуальный черновик")}
                  </button>
                  <button onClick={() => void d.reconcile()}>
                    {t("Сохранить мои изменения")}
                  </button>
                </div>
              ) : (
                <button onClick={() => void d.save()}>
                  {t("Повторить сохранение")}
                </button>
              )}
            </Alert>
          )}
          {error && (
            <Alert message={error}>
              {retry && (
                <button disabled={busy} onClick={() => void retry()}>
                  {t("Повторить действие")}
                </button>
              )}
            </Alert>
          )}
        </section>
      </div>
    </>
  );
}

function Terms({
  proposal,
  title = "Предложение",
}: {
  proposal: Proposal;
  title?: string;
}) {
  return (
    <div className="terms">
      <div className="section-title">
        <h2>{t(title)}</h2>
        <span className="version">
          {t("ВЕРСИЯ {version}", { version: number(proposal.version) })}
        </span>
      </div>
      <div className="terms-price">
        {money(proposal)}
        <span>{t("Срок: {date}", { date: date(proposal.deadline) })}</span>
      </div>
      <dl className="details">
        <div>
          <dt>{t("Объём работ")}</dt>
          <dd className="preserve">{proposal.scope}</dd>
        </div>
        <div>
          <dt>{t("Результат")}</dt>
          <dd className="preserve">{proposal.result}</dd>
        </div>
        <div>
          <dt>{t("Условия правок")}</dt>
          <dd className="preserve">{proposal.revision_terms}</dd>
        </div>
      </dl>
    </div>
  );
}
function ProjectPage({
  id,
  owner,
  ownerUsername,
}: {
  id: number;
  owner: boolean;
  ownerUsername: string;
}) {
  const resource = useResource<Project>(
      `${owner ? "/owner" : "/me"}/projects/${id}`,
    ),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [editor, setEditor] = useState(""),
    [retry, setRetry] = useState<null | (() => Promise<void>)>(null);
  const editorRef = useRef<HTMLElement>(null),
    editorTrigger = useRef<HTMLElement | null>(null);
  const openEditor = (kind: string) => {
    editorTrigger.current =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    setEditor(kind);
  };
  const closeEditor = () => {
    setEditor("");
    if (editorTrigger.current?.isConnected) editorTrigger.current.focus();
    editorTrigger.current = null;
  };
  useEffect(() => {
    setEditor("");
    editorTrigger.current = null;
    setError("");
    setRetry(null);
  }, [id, owner]);
  useEffect(() => {
    if (!editor || !editorRef.current) return;
    const heading = editorRef.current.querySelector("h2");
    if (heading) {
      heading.tabIndex = -1;
      heading.focus({ preventScroll: true });
    }
    editorRef.current.scrollIntoView({
      behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
        ? "auto"
        : "smooth",
      block: "start",
    });
  }, [editor]);
  const act = async (action: string, data: Record<string, unknown> = {}) => {
    const project = resource.data;
    if (!project) return;
    const path = `${owner ? "/owner" : "/me"}/projects/${id}/${action}`;
    const body = { expected_version: project.version, ...data };
    const perform = async () => {
      setBusy(true);
      setError("");
      try {
        const p = await intent<Project>(path, body);
        resource.setData(p);
        setEditor("");
        setRetry(null);
      } catch (e) {
        setError(
          e instanceof ApiError && e.status === 409
            ? `${errorOf(e)} Данные обновлены. Проверьте условия и повторите действие.`
            : errorOf(e),
        );
        if (e instanceof ApiError && e.status === 0) setRetry(() => perform);
        else if (e instanceof ApiError && e.status === 409) {
          setRetry(null);
          await resource.load();
        }
      } finally {
        setBusy(false);
      }
    };
    await perform();
  };
  if (resource.loading && !resource.data) return <Loading />;
  if (resource.error)
    return (
      <Alert message={resource.error} retry={() => void resource.load()} />
    );
  const p = resource.data;
  if (!p) return null;
  const allowed = (action: string) => p.allowed_actions.includes(action);
  const canAct = !busy && !retry;
  return (
    <>
      <Link to={owner ? "/owner/projects" : "/projects"} className="back-link">
        <ArrowLeft size={16} />
        {t("Все проекты")}
      </Link>
      <Heading
        eyebrow={`${t("ПРОЕКТ #{id}", { id: number(p.id) })} · ${date(p.created_at)}`}
        title={projectServiceTitle(p)}
        translateTitle={false}
        action={
          <button
            className="icon-button refresh"
            aria-label={t("Обновить проект")}
            onClick={() => void resource.load()}
          >
            <RefreshCw size={18} />
          </button>
        }
      />
      <div className="project-status">
        <Badge project={p} />
        <span>{t(p.next_action)}</span>
      </div>
      <div className="detail-layout">
        <div className="detail-main">
          {p.workflow === "legacy" && (
            <div className="inline-note">
              {p.workflow === "legacy"
                ? t(
                    "Историческое обращение. Условия и согласование не создавались автоматически.",
                  )
                : t("Условия проекта фиксируются в предложениях ниже.")}
            </div>
          )}
          {p.proposal && (
            <section className="panel proposal-panel">
              <Terms
                proposal={p.proposal}
                title={
                  p.accepted_proposal_version === p.proposal.version
                    ? t("Согласованные условия")
                    : t("Актуальное предложение")
                }
              />
              {p.accepted_proposal &&
                p.accepted_proposal.version !== p.proposal.version && (
                  <div className="inline-note">
                    {t(
                      "Продолжают действовать принятые условия версии {version}. Новая версия требует отдельного согласования.",
                      { version: number(p.accepted_proposal.version) },
                    )}
                  </div>
                )}
              {allowed("accept_proposal") && (
                <>
                  <p className="muted small">
                    {t(
                      "Подтверждение фиксирует объём, стоимость и условия. Оплата в приложении не проводится.",
                    )}
                  </p>
                  <div className="action-row">
                    <Button
                      disabled={!canAct}
                      onClick={() =>
                        void act("accept-proposal", {
                          proposal_version: p.proposal_version,
                        })
                      }
                    >
                      {t("Согласовать условия")} <Check size={17} />
                    </Button>
                    <Button
                      secondary
                      disabled={!canAct}
                      onClick={() => openEditor("request-changes")}
                    >
                      {t("Попросить изменения")}
                    </Button>
                  </div>
                </>
              )}
            </section>
          )}
          {p.accepted_proposal &&
            p.accepted_proposal.version !== p.proposal?.version && (
              <section className="panel">
                <Terms
                  proposal={p.accepted_proposal}
                  title={t("Согласованные условия")}
                />
              </section>
            )}
          {p.delivery && (
            <section className="panel">
              <div className="section-title">
                <h2>{t("Результат проекта")}</h2>
                <span className="version">
                  {t("ВЕРСИЯ {version}", {
                    version: number(p.delivery.version),
                  })}
                </span>
              </div>
              <p className="preserve">{p.delivery.description}</p>
              <a
                className="result-link"
                href={p.delivery.url}
                target="_blank"
                rel="noopener noreferrer"
              >
                {t("Открыть результат")} <ArrowUpRight size={17} />
              </a>
              {allowed("accept_delivery") && (
                <div className="action-row">
                  <Button
                    disabled={!canAct}
                    onClick={() =>
                      void act("accept-delivery", {
                        delivery_version: p.delivery_version,
                      })
                    }
                  >
                    {t("Принять результат")} <Check size={17} />
                  </Button>
                  <Button
                    secondary
                    disabled={!canAct}
                    onClick={() => openEditor("request-revision")}
                  >
                    {t("Нужны правки")}
                  </Button>
                </div>
              )}
            </section>
          )}
          {owner && p.allowed_actions.length > 0 && (
            <section className="panel">
              <h2>{t("Следующее действие")}</h2>
              <div className="owner-actions">
                {allowed("discuss") && (
                  <Button
                    secondary
                    disabled={!canAct}
                    onClick={() => void act("discuss")}
                  >
                    {t("Начать обсуждение")}
                  </Button>
                )}
                {allowed("publish_proposal") && (
                  <Button
                    disabled={!canAct}
                    onClick={() => openEditor("proposal")}
                  >
                    {t("Новое предложение")} <Plus size={17} />
                  </Button>
                )}
                {allowed("start") && (
                  <Button disabled={!canAct} onClick={() => void act("start")}>
                    {t("Начать работу")} <ArrowRight size={17} />
                  </Button>
                )}
                {allowed("update") && (
                  <Button
                    secondary
                    disabled={!canAct}
                    onClick={() => openEditor("update")}
                  >
                    {t("Добавить обновление")}
                  </Button>
                )}
                {allowed("deliver") && (
                  <Button
                    disabled={!canAct}
                    onClick={() => openEditor("deliver")}
                  >
                    {t("Передать результат")} <ArrowUpRight size={17} />
                  </Button>
                )}
                {allowed("close") && (
                  <button
                    className="text-button danger-text"
                    disabled={!canAct}
                    onClick={() => openEditor("close")}
                  >
                    {t("Закрыть обращение")}
                  </button>
                )}
              </div>
            </section>
          )}
          {editor && (
            <section className="panel editor" ref={editorRef}>
              <button
                aria-label={t("Закрыть редактор")}
                className="icon-button editor-close"
                onClick={closeEditor}
                disabled={busy}
              >
                <X size={18} />
              </button>
              {editor === "proposal" ? (
                <ProposalEditor
                  current={p.proposal}
                  busy={!canAct}
                  submit={(data) => void act("proposals", data)}
                />
              ) : editor === "deliver" ? (
                <DeliveryEditor
                  busy={!canAct}
                  submit={(data) => void act("deliver", data)}
                />
              ) : (
                <CommentEditor
                  kind={editor}
                  busy={!canAct}
                  submit={(text) =>
                    void act(
                      editor === "update" ? "updates" : editor,
                      editor === "close"
                        ? { reason: text }
                        : {
                            comment: text,
                            ...(editor === "request-changes"
                              ? { proposal_version: p.proposal_version }
                              : editor === "request-revision"
                                ? { delivery_version: p.delivery_version }
                                : {}),
                          },
                    )
                  }
                />
              )}
            </section>
          )}
          {error && (
            <Alert message={error}>
              {retry && (
                <button disabled={busy} onClick={() => void retry()}>
                  {t("Повторить действие")}
                </button>
              )}
            </Alert>
          )}
          <section className="panel">
            <h2>{t("История проекта")}</h2>
            <ol className="timeline">
              {p.history.map((event) => (
                <li key={event.id}>
                  <span className="timeline-dot" />
                  <div className="history-heading">
                    <strong>
                      {t(historyNames[event.kind] || "Изменение проекта")}
                    </strong>
                    <span>
                      {event.actor === "client"
                        ? t("Клиент")
                        : t("Исполнитель")}{" "}
                      · {date(event.created_at)} ·{" "}
                      {new Date(event.created_at).toLocaleTimeString(
                        intlLocale(),
                        {
                          hour: "2-digit",
                          minute: "2-digit",
                        },
                      )}
                    </span>
                  </div>
                  {typeof event.data.comment === "string" && (
                    <p className="preserve">{event.data.comment}</p>
                  )}
                  {typeof event.data.reason === "string" && (
                    <p className="preserve">{event.data.reason}</p>
                  )}
                  {typeof event.data.proposal_version === "number" && (
                    <small>
                      {t("Предложение версии {version}", {
                        version: number(event.data.proposal_version),
                      })}
                    </small>
                  )}
                </li>
              ))}
            </ol>
            {p.has_older_history && (
              <p className="muted small">
                {t("Показаны последние 200 событий.")}
              </p>
            )}
          </section>
          {p.proposals.length > 1 && (
            <details className="panel previous-terms">
              <summary>
                {t("Предыдущие предложения ({count})", {
                  count: number(p.proposals.length - 1),
                })}
              </summary>
              {p.proposals
                .filter((term) => term.version !== p.proposal_version)
                .map((term) => (
                  <Terms proposal={term} key={term.version} />
                ))}
            </details>
          )}
        </div>
        <aside className="detail-aside">
          <section className="panel">
            <span className="eyebrow">{t("ИСХОДНАЯ ЗАДАЧА")}</span>
            <h3>{p.name}</h3>
            <p className="preserve">{p.description}</p>
            <dl className="details compact">
              <div>
                <dt>{t("Пожелание по бюджету")}</dt>
                <dd>{p.budget || t("Не указан")}</dd>
              </div>
              <div>
                <dt>{t("Желаемый срок")}</dt>
                <dd>{p.deadline || t("Не указан")}</dd>
              </div>
            </dl>
            {p.attachments.items.length > 0 && (
              <>
                <h3>{t("Материалы")}</h3>
                <FileList attachments={p.attachments} />
              </>
            )}
            {owner && p.client?.username && (
              <button
                className="text-link text-button"
                onClick={() => contactOwner(p.client!.username!)}
              >
                {t("Написать клиенту")} <ArrowUpRight size={16} />
              </button>
            )}
            {!owner && ownerUsername && (
              <button
                className="text-link text-button"
                onClick={() => contactOwner(ownerUsername)}
              >
                {t("Связаться с исполнителем")} <MessageCircle size={16} />
              </button>
            )}
          </section>
          {p.close_reason && (
            <section className="panel">
              <h3>{t("Причина закрытия")}</h3>
              <p className="preserve">{p.close_reason}</p>
            </section>
          )}
        </aside>
      </div>
    </>
  );
}
function ProposalEditor({
  current,
  busy,
  submit,
}: {
  current: Proposal | null;
  busy: boolean;
  submit: (data: Record<string, unknown>) => void;
}) {
  const [preview, setPreview] = useState(false),
    [fields, setFields] = useState({
      scope: current?.scope || "",
      result: current?.result || "",
      price: current ? String(current.price_minor / 100) : "",
      currency: current?.currency || "KZT",
      deadline: current?.deadline || "",
      revision_terms: current?.revision_terms || "",
    });
  const set = (key: keyof typeof fields, value: string) =>
    setFields({ ...fields, [key]: value });
  const terms = {
    scope: fields.scope,
    result: fields.result,
    price_minor: Math.round(Number(fields.price) * 100),
    currency: fields.currency,
    deadline: fields.deadline,
    revision_terms: fields.revision_terms,
  };
  return (
    <>
      <h2>{preview ? t("Проверьте условия") : t("Новое предложение")}</h2>
      {preview ? (
        <>
          <Terms
            proposal={{
              ...terms,
              version: (current?.version || 0) + 1,
              created_at: new Date().toISOString(),
            }}
          />
          <p className="muted small">
            {t(
              "Публикация создаст новую неизменяемую версию. Клиент подтвердит её отдельно.",
            )}
          </p>
          <div className="action-row">
            <Button disabled={busy} onClick={() => submit(terms)}>
              {t("Опубликовать предложение")} <ArrowUpRight size={17} />
            </Button>
            <Button secondary disabled={busy} onClick={() => setPreview(false)}>
              {t("Редактировать")}
            </Button>
          </div>
        </>
      ) : (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            setPreview(true);
          }}
        >
          <Field label={t("Объём работ")}>
            <textarea
              required
              minLength={10}
              maxLength={3000}
              rows={4}
              value={fields.scope}
              onChange={(e) => set("scope", e.target.value)}
            />
          </Field>
          <Field label={t("Результат")}>
            <textarea
              required
              minLength={10}
              maxLength={2000}
              rows={3}
              value={fields.result}
              onChange={(e) => set("result", e.target.value)}
            />
          </Field>
          <div className="field-grid">
            <Field label={t("Цена")}>
              <input
                type="number"
                required
                min="0.01"
                max="10000000000"
                step="0.01"
                value={fields.price}
                onChange={(e) => set("price", e.target.value)}
              />
            </Field>
            <Field label={t("Валюта")}>
              <select
                value={fields.currency}
                onChange={(e) => set("currency", e.target.value)}
              >
                {["KZT", "USD", "EUR", "RUB"].map((c) => (
                  <option key={c}>{c}</option>
                ))}
              </select>
            </Field>
          </div>
          <Field label={t("Срок выполнения")}>
            <input
              type="date"
              required
              min={new Date().toISOString().slice(0, 10)}
              value={fields.deadline}
              onChange={(e) => set("deadline", e.target.value)}
            />
          </Field>
          <Field label={t("Условия правок")}>
            <textarea
              required
              minLength={2}
              maxLength={1000}
              rows={3}
              value={fields.revision_terms}
              onChange={(e) => set("revision_terms", e.target.value)}
            />
          </Field>
          <Button type="submit" disabled={busy}>
            {t("Проверить предложение")} <ArrowRight size={17} />
          </Button>
        </form>
      )}
    </>
  );
}
function DeliveryEditor({
  busy,
  submit,
}: {
  busy: boolean;
  submit: (data: Record<string, unknown>) => void;
}) {
  const [description, setDescription] = useState(""),
    [url, setUrl] = useState("");
  return (
    <>
      <h2>{t("Передать результат")}</h2>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          submit({ description, url });
        }}
      >
        <Field label={t("Описание результата")}>
          <textarea
            required
            minLength={10}
            maxLength={2000}
            rows={5}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </Field>
        <Field
          label={t("Ссылка на результат")}
          hint={t("HTTPS-ссылка на материалы проекта")}
        >
          <input
            required
            type="url"
            pattern="https://.*"
            maxLength={2000}
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://"
          />
        </Field>
        <Button type="submit" disabled={busy}>
          {t("Отправить на приёмку")} <ArrowUpRight size={17} />
        </Button>
      </form>
    </>
  );
}
function CommentEditor({
  kind,
  busy,
  submit,
}: {
  kind: string;
  busy: boolean;
  submit: (text: string) => void;
}) {
  const [text, setText] = useState("");
  return (
    <>
      <h2>
        {kind === "close"
          ? t("Закрыть обращение")
          : kind === "update"
            ? t("Обновление проекта")
            : kind === "request-revision"
              ? t("Что нужно поправить?")
              : t("Что изменить в условиях?")}
      </h2>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          submit(text);
        }}
      >
        <Field
          label={kind === "close" ? t("Причина закрытия") : t("Комментарий")}
        >
          <textarea
            required
            minLength={kind === "close" ? 3 : 2}
            maxLength={kind === "close" ? 1000 : 2000}
            rows={5}
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
        </Field>
        <Button type="submit" danger={kind === "close"} disabled={busy}>
          {kind === "close"
            ? t("Подтвердить закрытие")
            : kind === "update"
              ? t("Опубликовать обновление")
              : t("Отправить комментарий")}
        </Button>
      </form>
    </>
  );
}
function OwnerHome() {
  const resource = useResource<Summary>("/owner/summary");
  return (
    <>
      <Heading title={t("Рабочий обзор")} />
      {resource.loading ? (
        <Loading />
      ) : resource.error ? (
        <Alert message={resource.error} retry={() => void resource.load()} />
      ) : (
        resource.data && (
          <>
            <section
              className="attention-panel"
              aria-labelledby="attention-heading"
            >
              <div className="attention-copy">
                <h2 id="attention-heading">{t("Требуют внимания")}</h2>
                <p>
                  {resource.data.needs_response
                    ? t("Нужно ответить клиенту или начать работу.")
                    : t(
                        "Сейчас нет проектов, ожидающих вашего ответа или старта.",
                      )}
                </p>
              </div>
              <strong className="attention-count">
                {number(resource.data.needs_response)}
              </strong>
              <Link
                className="button"
                to="/owner/projects?attention=true"
                aria-label={t("Показать проекты, требующие внимания")}
              >
                {t("Показать проекты")} <ArrowUpRight size={18} />
              </Link>
            </section>
            <div className="overview-meta">
              <span>
                {t("Всего проектов: {count}", {
                  count: number(resource.data.total),
                })}
              </span>
              <Link className="text-link" to="/owner/projects">
                {t("Все проекты")} <ArrowRight size={16} />
              </Link>
            </div>
            <div className="metrics">
              {[
                [t("Новые обращения"), resource.data.counts.new, "new"],
                [
                  t("Ждём клиента"),
                  resource.data.waiting_client,
                  "proposal_sent",
                ],
                [t("В работе"), resource.data.in_progress, "in_progress"],
                [t("На приёмке"), resource.data.review, "review"],
              ].map(([name, value, status]) => (
                <Link
                  to={`/owner/projects?status=${status}`}
                  key={name}
                  className="metric"
                >
                  <div className="metric-top">
                    <span className={`metric-dot status-${status}`} />
                    <ArrowUpRight size={17} />
                  </div>
                  <strong>
                    {typeof value === "number" ? number(value) : value}
                  </strong>
                  <span>{t(String(name))}</span>
                </Link>
              ))}
            </div>
            <p className="dashboard-hint">
              {t("Выберите этап, чтобы открыть нужные проекты.")}
            </p>
            <Link to="/owner/notifications" className="notification-link">
              <Bell size={22} />
              <div>
                <h3>{t("Доставка уведомлений")}</h3>
                <p>{t("Состояние сообщений и допустимые повторы.")}</p>
              </div>
              <ChevronRight size={21} />
            </Link>
          </>
        )
      )}
    </>
  );
}
function Notifications() {
  const [offset, setOffset] = useState(0),
    [error, setError] = useState(""),
    [busy, setBusy] = useState<number | null>(null);
  const resource = useResource<PageData<Notification>>(
    `/owner/notifications?offset=${offset}`,
  );
  const retry = async (id: number) => {
    setBusy(id);
    setError("");
    try {
      await api(`/owner/notifications/${id}/retry`, json("POST", {}));
      await resource.load();
    } catch (e) {
      setError(errorOf(e));
    } finally {
      setBusy(null);
    }
  };
  return (
    <>
      <Heading
        eyebrow={t("РАБОЧИЙ КАБИНЕТ")}
        title={t("Уведомления")}
        description={t(
          "Бизнес-действия уже сохранены. Здесь — только доставка сообщений.",
        )}
      />
      {error && <Alert message={error} />}{" "}
      {resource.loading ? (
        <Loading />
      ) : resource.error ? (
        <Alert message={resource.error} retry={() => void resource.load()} />
      ) : !resource.data?.items.length ? (
        <Empty title={t("Нет уведомлений, требующих внимания")} icon={<Bell />}>
          <p>{t("Состояние доставки появится здесь.")}</p>
        </Empty>
      ) : (
        <>
          <div className="notification-list">
            {resource.data.items.map((n) => (
              <article className="panel" key={n.id}>
                <div className="section-title">
                  <Link
                    to={`/owner/projects/${n.project_id}`}
                    className="text-link"
                  >
                    {t("Проект #{id}", { id: number(n.project_id) })}{" "}
                    <ArrowUpRight size={15} />
                  </Link>
                  <span className="version">
                    {n.state === "failed"
                      ? t("Ошибка доставки")
                      : n.state === "dead"
                        ? t("Попытки исчерпаны")
                        : n.state === "sent"
                          ? t("Доставлено")
                          : n.state === "cancelled"
                            ? t("Отменено")
                            : t("В очереди")}
                  </span>
                </div>
                <h3>{t(historyNames[n.kind] || "Уведомление проекта")}</h3>
                <p className="muted">
                  {t("Попыток: {count}", { count: number(n.attempts) })}
                </p>
                {n.error_code && (
                  <p className="small">
                    {t(
                      "Не удалось доставить сообщение. Проверьте доступ бота к сообщениям.",
                    )}
                  </p>
                )}
                {n.can_retry && (
                  <Button
                    secondary
                    disabled={busy === n.id}
                    onClick={() => void retry(n.id)}
                  >
                    {t("Повторить доставку")} <RefreshCw size={16} />
                  </Button>
                )}
              </article>
            ))}
          </div>
          <div className="pagination">
            <Button
              secondary
              disabled={offset === 0}
              onClick={() =>
                setOffset(Math.max(0, offset - (resource.data?.limit || 20)))
              }
            >
              {t("Назад")}
            </Button>
            <span>
              {t("{count} уведомлений", { count: number(resource.data.total) })}
            </span>
            <Button
              secondary
              disabled={offset + resource.data.limit >= resource.data.total}
              onClick={() => setOffset(offset + resource.data!.limit)}
            >
              {t("Далее")}
            </Button>
          </div>
        </>
      )}
    </>
  );
}
function Profile({
  user,
  setUser,
  logout,
  ownerUsername,
}: {
  user: User;
  setUser: (user: User | null) => void;
  logout: () => Promise<void>;
  ownerUsername: string;
}) {
  const [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [confirmation, setConfirmation] = useState(""),
    [deleted, setDeleted] = useState(false);
  const preferences = async () => {
    setBusy(true);
    setError("");
    try {
      const enabled = !user.notifications_enabled;
      if (enabled && telegram()?.requestWriteAccess)
        await new Promise<void>((resolve) =>
          telegram()!.requestWriteAccess!(() => resolve()),
        );
      setUser(
        await api<User>(
          "/me/preferences",
          json("PUT", {
            notifications_enabled: enabled,
            expected_version: user.preference_version,
          }),
        ),
      );
    } catch (e) {
      setError(errorOf(e));
      if (e instanceof ApiError && e.status === 409)
        setUser(await api<User>("/me"));
    } finally {
      setBusy(false);
    }
  };
  const askDelete = async () => {
    setBusy(true);
    setError("");
    try {
      setConfirmation(
        (
          await api<{ confirmation_token: string }>(
            "/me/deletion-confirmation",
            json("POST", {}),
          )
        ).confirmation_token,
      );
    } catch (e) {
      setError(errorOf(e));
    } finally {
      setBusy(false);
    }
  };
  const remove = async () => {
    setBusy(true);
    setError("");
    try {
      await api(
        "/me/data",
        json("DELETE", { confirmation_token: confirmation }),
      );
      session.clear();
      setDeleted(true);
    } catch (e) {
      setError(errorOf(e));
      setConfirmation("");
    } finally {
      setBusy(false);
    }
  };
  if (deleted)
    return (
      <Empty title={t("Ваши данные удалены")} icon={<CheckCheck />}>
        <p>
          {t(
            "Рабочие записи и доступ к ним удалены. Физическая очистка файлов выполняется в фоне.",
          )}
        </p>
      </Empty>
    );
  return (
    <>
      <Heading
        eyebrow={t("ЛИЧНЫЙ КАБИНЕТ")}
        title={t("Профиль")}
        description={t("Ваш контакт и настройки приватности.")}
      />
      <div className="profile-grid">
        <section className="panel">
          <div className="profile-person">
            <span className="avatar large">{user.first_name.slice(0, 1)}</span>
            <div>
              <h2>{user.first_name}</h2>
              <p>
                {user.username ? `@${user.username}` : t("Telegram-аккаунт")}
              </p>
            </div>
            <ShieldCheck size={22} />
          </div>
          <hr />
          <div className="preference-row">
            <div>
              <h3>{t("Уведомления в Telegram")}</h3>
              <p>{t("Изменения условий, этапов и приёмка.")}</p>
            </div>
            <button
              role="switch"
              aria-label={t("Уведомления в Telegram")}
              aria-checked={user.notifications_enabled}
              className={`switch ${user.notifications_enabled ? "on" : ""}`}
              disabled={busy}
              onClick={() => void preferences()}
            >
              <span />
            </button>
          </div>
          <p className="small muted">
            {t(
              "Настройка сохраняется здесь. Доставка зависит от доступа бота к сообщениям.",
            )}
          </p>
          {ownerUsername && (
            <button
              className="text-link text-button"
              onClick={() => contactOwner(ownerUsername)}
            >
              {t("Связаться со студией")} <MessageCircle size={16} />
            </button>
          )}
          <button
            className="logout text-button"
            disabled={busy}
            onClick={() => void logout().catch((e) => setError(errorOf(e)))}
          >
            <LogOut size={16} />
            {t("Завершить сессию")}
          </button>
        </section>
        <section className="panel privacy">
          <ShieldCheck size={24} />
          <h2>{t("Ваши данные")}</h2>
          <p>
            {t(
              "Сохраняем Telegram-контакт, черновик, проекты, условия и материалы, чтобы вести работу по вашей задаче.",
            )}
          </p>
          <p>
            {t(
              "Удаление очищает связанные записи в рабочей базе и прекращает доступ к файлам. Ранее отправленные сообщения и резервные копии автоматически не отзываются.",
            )}
          </p>
          {!confirmation ? (
            <button
              className="danger-text text-button"
              disabled={busy}
              onClick={() => void askDelete()}
            >
              {t("Удалить мои данные")} <Trash2 size={15} />
            </button>
          ) : (
            <div className="delete-confirmation">
              <h3>{t("Удалить все ваши данные?")}</h3>
              <p>
                {t(
                  "Будут удалены черновик, проекты, условия, история и настройки. Это действие нельзя отменить.",
                )}
              </p>
              <div className="action-row">
                <Button danger disabled={busy} onClick={() => void remove()}>
                  {t("Подтвердить удаление")}
                </Button>
                <Button
                  secondary
                  disabled={busy}
                  onClick={() => setConfirmation("")}
                >
                  {t("Отмена")}
                </Button>
              </div>
            </div>
          )}
        </section>
      </div>
      {error && <Alert message={error} />}
    </>
  );
}
