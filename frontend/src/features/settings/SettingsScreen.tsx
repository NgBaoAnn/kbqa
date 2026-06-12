/**
 * SettingsScreen — user preferences panel (Sprint 1).
 *
 * Allows the authenticated user to configure:
 *  - Language (vi / en)
 *  - Explanation level (general / detailed / expert)
 *  - Answer style (concise / detailed)
 *
 * Loads current preferences on mount; saves via PATCH on form submit.
 */

import { useEffect, useMemo, useState, type FormEvent } from "react";
import {
  Check,
  Languages,
  Loader2,
  RotateCcw,
  Save,
  Settings2,
  SlidersHorizontal,
  Text,
} from "lucide-react";
import { getPreferences, updatePreferences } from "../../services/api";
import type { UserPreferences, UserPreferencesResponse } from "../../types/api";

// ── Option definitions ─────────────────────────────────────────────────────────

const LANGUAGE_OPTIONS: { value: UserPreferences["language"]; label: string }[] = [
  { value: "vi", label: "Tiếng Việt" },
  { value: "en", label: "English" },
];

const EXPLANATION_OPTIONS: {
  value: UserPreferences["explanation_level"];
  label: string;
  description: string;
}[] = [
  { value: "general", label: "Phổ thông", description: "Ngôn ngữ đơn giản, phù hợp cho người dùng thông thường" },
  { value: "detailed", label: "Chi tiết", description: "Giải thích đầy đủ hơn, phù hợp cho học sinh, sinh viên" },
  { value: "expert", label: "Chuyên sâu", description: "Thuật ngữ y khoa chuyên nghiệp, dành cho chuyên gia" },
];

const STYLE_OPTIONS: {
  value: UserPreferences["answer_style"];
  label: string;
  description: string;
}[] = [
  { value: "concise", label: "Ngắn gọn", description: "Câu trả lời trực tiếp, súc tích" },
  { value: "detailed", label: "Đầy đủ", description: "Câu trả lời toàn diện với bối cảnh và ví dụ" },
];

function preferencesEqual(a: UserPreferences, b: UserPreferences): boolean {
  return (
    a.language === b.language &&
    a.explanation_level === b.explanation_level &&
    a.answer_style === b.answer_style
  );
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function LoadingState() {
  return (
    <div className="settings-loading" aria-live="polite">
      <Loader2 size={22} className="spin" />
      <span>Đang tải cài đặt…</span>
    </div>
  );
}

function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="settings-error" role="alert">
      <span>{message}</span>
      <button type="button" className="link-btn" onClick={onRetry}>
        Thử lại
      </button>
    </div>
  );
}

// ── OptionCard ─────────────────────────────────────────────────────────────────

function ChoiceRow<T extends string>({
  value,
  selected,
  label,
  description,
  onSelect,
}: {
  value: T;
  selected: boolean;
  label: string;
  description?: string;
  onSelect: (v: T) => void;
}) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={selected}
      className={`settings-choice-row${selected ? " settings-choice-row--selected" : ""}`}
      onClick={() => onSelect(value)}
    >
      <span className="settings-radio-mark" aria-hidden="true">
        {selected && <Check size={12} />}
      </span>
      <div className="settings-choice-copy">
        <span className="settings-choice-label">{label}</span>
        {description && (
          <span className="settings-choice-desc">{description}</span>
        )}
      </div>
    </button>
  );
}

// ── SaveBanner ────────────────────────────────────────────────────────────────

function SaveBanner({ visible }: { visible: boolean }) {
  return (
    <div
      className={`settings-save-banner${visible ? " settings-save-banner--visible" : ""}`}
      aria-live="polite"
    >
      <Check size={14} aria-hidden="true" /> Đã lưu cài đặt
    </div>
  );
}

// ── Main component ─────────────────────────────────────────────────────────────

export function SettingsScreen() {
  const [loadState, setLoadState] = useState<"loading" | "ready" | "error">("loading");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [prefs, setPrefs] = useState<UserPreferences>({
    language: "vi",
    explanation_level: "general",
    answer_style: "concise",
  });
  const [savedPrefs, setSavedPrefs] = useState<UserPreferences>({
    language: "vi",
    explanation_level: "general",
    answer_style: "concise",
  });
  const [saving, setSaving] = useState(false);
  const [savedVisible, setSavedVisible] = useState(false);

  const isDirty = useMemo(() => !preferencesEqual(prefs, savedPrefs), [prefs, savedPrefs]);

  const selectedLabels = useMemo(() => ({
    language: LANGUAGE_OPTIONS.find((o) => o.value === prefs.language)?.label ?? prefs.language,
    explanation: EXPLANATION_OPTIONS.find((o) => o.value === prefs.explanation_level)?.label ?? prefs.explanation_level,
    style: STYLE_OPTIONS.find((o) => o.value === prefs.answer_style)?.label ?? prefs.answer_style,
  }), [prefs]);

  // ── Load preferences on mount ──────────────────────────────────────────

  async function loadPreferences() {
    setLoadState("loading");
    setErrorMsg(null);
    try {
      const data: UserPreferencesResponse = await getPreferences();
      const nextPrefs = {
        language: data.language,
        explanation_level: data.explanation_level,
        answer_style: data.answer_style,
      };
      setPrefs(nextPrefs);
      setSavedPrefs(nextPrefs);
      setLoadState("ready");
    } catch {
      setErrorMsg("Không thể tải cài đặt. Vui lòng thử lại.");
      setLoadState("error");
    }
  }

  useEffect(() => { void loadPreferences(); }, []);

  // ── Save preferences ──────────────────────────────────────────────────

  async function handleSave(e: FormEvent) {
    e.preventDefault();
    if (saving) return;
    setSaving(true);
    try {
      const data = await updatePreferences(prefs);
      const nextPrefs = {
        language: data.language,
        explanation_level: data.explanation_level,
        answer_style: data.answer_style,
      };
      setPrefs(nextPrefs);
      setSavedPrefs(nextPrefs);
      setSavedVisible(true);
      setTimeout(() => setSavedVisible(false), 2500);
    } catch {
      setErrorMsg("Không thể lưu cài đặt. Vui lòng thử lại.");
    } finally {
      setSaving(false);
    }
  }

  function handleReset() {
    setPrefs(savedPrefs);
  }

  // ── Render ────────────────────────────────────────────────────────────

  return (
    <div className="settings-screen" aria-label="Cài đặt cá nhân">
      <header className="settings-header">
        <div className="settings-title-block">
          <span className="settings-header-icon" aria-hidden="true">
            <Settings2 size={19} />
          </span>
          <div>
            <h1 className="settings-title">Cài đặt cá nhân</h1>
            <p className="settings-subtitle">Ngôn ngữ, độ chi tiết và phong cách trả lời.</p>
          </div>
        </div>
        <SaveBanner visible={savedVisible} />
      </header>

      {loadState === "loading" && <LoadingState />}
      {loadState === "error" && (
        <ErrorState message={errorMsg ?? ""} onRetry={loadPreferences} />
      )}

      {loadState === "ready" && (
        <form
          id="settings-form"
          className="settings-form"
          onSubmit={handleSave}
          aria-label="Biểu mẫu cài đặt"
        >
          <aside className="settings-summary-panel" aria-label="Tóm tắt cài đặt">
            <div className="settings-summary-row">
              <span>Ngôn ngữ</span>
              <strong>{selectedLabels.language}</strong>
            </div>
            <div className="settings-summary-row">
              <span>Mức giải thích</span>
              <strong>{selectedLabels.explanation}</strong>
            </div>
            <div className="settings-summary-row">
              <span>Phong cách</span>
              <strong>{selectedLabels.style}</strong>
            </div>
          </aside>

          <div className="settings-panel-stack">
            <section className="settings-panel" aria-labelledby="lang-label">
              <div className="settings-section-heading">
                <Languages size={16} aria-hidden="true" />
                <div>
                  <h2 id="lang-label" className="settings-section-title">Ngôn ngữ</h2>
                  <p className="settings-section-desc">Mặc định cho hội thoại và câu trả lời mới.</p>
                </div>
              </div>
              <div
                className="settings-segmented"
                role="radiogroup"
                aria-labelledby="lang-label"
              >
                {LANGUAGE_OPTIONS.map((opt) => (
                  <button
                    key={opt.value}
                    type="button"
                    role="radio"
                    aria-checked={prefs.language === opt.value}
                    className={`settings-segment${prefs.language === opt.value ? " settings-segment--active" : ""}`}
                    onClick={() => setPrefs((p) => ({ ...p, language: opt.value }))}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
            </section>

            <section className="settings-panel" aria-labelledby="level-label">
              <div className="settings-section-heading">
                <SlidersHorizontal size={16} aria-hidden="true" />
                <div>
                  <h2 id="level-label" className="settings-section-title">Mức độ giải thích</h2>
                  <p className="settings-section-desc">Điều chỉnh độ sâu và thuật ngữ y khoa.</p>
                </div>
              </div>
              <div className="settings-choice-list" role="radiogroup" aria-labelledby="level-label">
                {EXPLANATION_OPTIONS.map((opt) => (
                  <ChoiceRow
                    key={opt.value}
                    value={opt.value}
                    selected={prefs.explanation_level === opt.value}
                    label={opt.label}
                    description={opt.description}
                    onSelect={(v) => setPrefs((p) => ({ ...p, explanation_level: v }))}
                  />
                ))}
              </div>
            </section>

            <section className="settings-panel" aria-labelledby="style-label">
              <div className="settings-section-heading">
                <Text size={16} aria-hidden="true" />
                <div>
                  <h2 id="style-label" className="settings-section-title">Phong cách trả lời</h2>
                  <p className="settings-section-desc">Cân bằng giữa tốc độ đọc và mức đầy đủ.</p>
                </div>
              </div>
              <div className="settings-choice-list" role="radiogroup" aria-labelledby="style-label">
                {STYLE_OPTIONS.map((opt) => (
                  <ChoiceRow
                    key={opt.value}
                    value={opt.value}
                    selected={prefs.answer_style === opt.value}
                    label={opt.label}
                    description={opt.description}
                    onSelect={(v) => setPrefs((p) => ({ ...p, answer_style: v }))}
                  />
                ))}
              </div>
            </section>
          </div>

          <div className="settings-actions">
            <button
              type="button"
              className="settings-secondary-btn"
              disabled={!isDirty || saving}
              onClick={handleReset}
            >
              <RotateCcw size={14} aria-hidden="true" />
              Hoàn tác
            </button>
            <button
              id="settings-save-btn"
              type="submit"
              className="settings-save-btn"
              disabled={saving || !isDirty}
              aria-busy={saving}
            >
              {saving ? (
                <>
                  <Loader2 size={15} className="spin" aria-hidden="true" />
                  Đang lưu…
                </>
              ) : (
                <>
                  <Save size={14} aria-hidden="true" />
                  Lưu cài đặt
                </>
              )}
            </button>
          </div>
        </form>
      )}
    </div>
  );
}
