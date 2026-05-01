import { useUIStore } from '../stores/uiStore'
import { translations } from '../i18n/translations'

/**
 * Non-hook translation function for use outside React components
 * (services, classes, store callbacks). Reads locale directly from store.
 *
 * Inside React components prefer `useT()` so the component re-renders
 * on locale change.
 */
export function t(key: string, vars?: Record<string, string | number>): string {
  const locale = useUIStore.getState().locale
  const str = translations[locale][key] ?? translations.tr[key] ?? key
  if (!vars) return str
  return str.replace(/\{(\w+)\}/g, (_, k) => String(vars[k] ?? `{${k}}`))
}
