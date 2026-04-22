import { useUIStore } from '../stores/uiStore'
import { translations } from '../i18n/translations'

/**
 * Returns a translation function `t(key, vars?)` for the current locale.
 * Supports {varName} interpolation in translation strings.
 * Falls back to Turkish, then to the raw key if a translation is missing.
 */
export function useT(): (key: string, vars?: Record<string, string | number>) => string {
  const locale = useUIStore((s) => s.locale)

  return (key: string, vars?: Record<string, string | number>): string => {
    const str = translations[locale][key] ?? translations.tr[key] ?? key
    if (!vars) return str
    return str.replace(/\{(\w+)\}/g, (_, k) => String(vars[k] ?? `{${k}}`))
  }
}
