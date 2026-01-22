/**
 * I18n Helper for Brevo Analytics SPA
 *
 * Provides translation functions based on Django settings.
 * Translations are passed from Django via window.BREVO_ANALYTICS_CONFIG.
 */

// Get translations from global config
const getConfig = () => {
  if (!window.BREVO_ANALYTICS_CONFIG) {
    console.warn('BREVO_ANALYTICS_CONFIG not found, using default English translations')
    return {
      translations: {},
      languageCode: 'en'
    }
  }
  return window.BREVO_ANALYTICS_CONFIG
}

/**
 * Get translated string by key.
 *
 * @param {string} key - Translation key
 * @param {string} fallback - Fallback text if translation not found
 * @returns {string} Translated text or fallback
 */
export const t = (key, fallback = null) => {
  const config = getConfig()
  const value = config.translations[key]

  if (value !== undefined) {
    return value
  }

  if (fallback !== null) {
    return fallback
  }

  console.warn(`Translation key "${key}" not found`)
  return key
}

/**
 * Get current language code.
 *
 * @returns {string} Language code (e.g., 'it', 'en')
 */
export const getLanguageCode = () => {
  return getConfig().languageCode
}

/**
 * Format date based on current locale.
 *
 * @param {string|Date} dateValue - Date to format
 * @param {object} options - Intl.DateTimeFormat options
 * @returns {string} Formatted date
 */
export const formatDate = (dateValue, options = null) => {
  if (!dateValue) return ''

  const config = getConfig()
  const locale = config.languageCode === 'it' ? 'it-IT' : 'en-US'

  const defaultOptions = {
    day: 'numeric',
    month: 'long',
    year: 'numeric'
  }

  return new Date(dateValue).toLocaleDateString(locale, options || defaultOptions)
}

/**
 * Format date and time based on current locale.
 *
 * @param {string|Date} dateValue - DateTime to format
 * @param {object} options - Intl.DateTimeFormat options
 * @returns {string} Formatted date and time
 */
export const formatDateTime = (dateValue, options = null) => {
  if (!dateValue) return ''

  const config = getConfig()
  const locale = config.languageCode === 'it' ? 'it-IT' : 'en-US'

  const defaultOptions = {
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  }

  return new Date(dateValue).toLocaleString(locale, options || defaultOptions)
}

/**
 * Format short date (day + month) based on current locale.
 *
 * @param {string|Date} dateValue - Date to format
 * @returns {string} Formatted short date
 */
export const formatShortDate = (dateValue) => {
  if (!dateValue) return ''

  const config = getConfig()
  const locale = config.languageCode === 'it' ? 'it-IT' : 'en-US'

  return new Date(dateValue).toLocaleDateString(locale, {
    day: 'numeric',
    month: 'short'
  })
}

// Export all functions as default object
export default {
  t,
  getLanguageCode,
  formatDate,
  formatDateTime,
  formatShortDate
}
