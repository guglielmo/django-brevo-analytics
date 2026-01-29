const { createApp, ref, computed, onMounted } = Vue
const { createRouter, createWebHashHistory } = VueRouter

// ========================================
// I18n Helper - Get translations from Django
// ========================================
const getConfig = () => window.BREVO_ANALYTICS_CONFIG || { translations: {}, languageCode: 'en' }
const t = (key, fallback = key) => getConfig().translations[key] || fallback

const formatDate = (dateValue, options = null) => {
  if (!dateValue) return ''
  const locale = getConfig().languageCode === 'it' ? 'it-IT' : 'en-US'
  return new Date(dateValue).toLocaleDateString(locale, options || {
    day: 'numeric', month: 'long', year: 'numeric'
  })
}

const formatDateTime = (dateValue, options = null) => {
  if (!dateValue) return ''
  const locale = getConfig().languageCode === 'it' ? 'it-IT' : 'en-US'
  return new Date(dateValue).toLocaleString(locale, options || {
    day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', second: '2-digit'
  })
}

const formatShortDate = (dateValue) => {
  if (!dateValue) return ''
  const locale = getConfig().languageCode === 'it' ? 'it-IT' : 'en-US'
  return new Date(dateValue).toLocaleDateString(locale, {
    day: 'numeric', month: 'short'
  })
}

// ========================================
// API Helper
// ========================================
const api = {
  async get(url) {
    const response = await fetch(`/brevo-analytics${url}`)
    if (!response.ok) {
      const error = await response.json().catch(() => ({ error: response.statusText }))
      throw new Error(error.error || response.statusText)
    }
    return response.json()
  },
  async post(url, data) {
    const response = await fetch(`/brevo-analytics${url}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]')?.value || ''
      },
      body: JSON.stringify(data)
    })
    if (!response.ok) {
      const error = await response.json().catch(() => ({ error: response.statusText }))
      throw new Error(error.error || response.statusText)
    }
    return response.json()
  },
  async delete(url) {
    const response = await fetch(`/brevo-analytics${url}`, {
      method: 'DELETE',
      headers: {
        'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]')?.value || ''
      }
    })
    if (!response.ok) {
      const error = await response.json().catch(() => ({ error: response.statusText }))
      throw new Error(error.error || response.statusText)
    }
    return response.json()
  }
}

// ========================================
// Components
// ========================================

// Check Email Tab Component
const CheckEmailTab = {
  template: `
    <div class="blacklist-tab">
      <h2>{{ t('check_email_tab') }}</h2>
      <p style="color: #666; margin-bottom: 20px;">
        {{ t('check_email_description') }}
      </p>

      <div class="search-box" style="max-width: 600px;">
        <div style="display: flex; gap: 10px;">
          <input
            v-model="emailQuery"
            type="email"
            :placeholder="t('enter_email_placeholder')"
            @keyup.enter="checkEmail"
            style="flex: 1;">
          <button
            @click="checkEmail"
            :disabled="loading || !emailQuery"
            style="padding: 10px 24px; background: #417690; color: white; border: none; border-radius: 6px; cursor: pointer; font-weight: 600; white-space: nowrap;"
            :style="{ opacity: (loading || !emailQuery) ? 0.5 : 1 }">
            {{ loading ? t('verifying') : t('verify_button') }}
          </button>
        </div>
      </div>

      <!-- Result Box -->
      <div v-if="result && !error" class="result-box" style="margin-top: 30px; max-width: 600px;">
        <div v-if="result.is_blacklisted" class="alert alert-warning">
          <h3 style="margin: 0 0 15px 0; color: #e65100;">{{ t('email_in_blacklist') }}</h3>
          <div style="line-height: 1.8;">
            <div><strong>{{ t('email') }}:</strong> {{ result.email }}</div>
            <div><strong>{{ t('reason') }}:</strong> {{ formatReason(result.reason) }}</div>
            <div v-if="result.blocked_at">
              <strong>{{ t('blocked_date') }}:</strong> {{ formatDateTime(result.blocked_at) }}
            </div>
            <div v-if="result.senders && result.senders.length > 0">
              <strong>{{ t('blocked_senders') }}:</strong> {{ result.senders.join(', ') }}
            </div>
          </div>
          <button
            @click="removeFromBlacklist"
            :disabled="removing"
            style="margin-top: 15px; padding: 10px 20px; background: #ff9800; color: white; border: none; border-radius: 4px; cursor: pointer; font-weight: 600;">
            {{ removing ? t('unblocking') : t('unblock_button') }}
          </button>
        </div>

        <div v-else class="alert alert-success">
          <h3 style="margin: 0 0 10px 0; color: #2e7d32;">{{ t('email_not_in_blacklist') }}</h3>
          <p style="margin: 0;">
            <strong>{{ result.email }}</strong> - {{ t('email_not_blocked_message') }}
          </p>
        </div>
      </div>

      <!-- Error Box -->
      <div v-if="error" class="alert alert-error" style="margin-top: 30px; max-width: 600px;">
        <h3 style="margin: 0 0 10px 0; color: #c62828;">❌ {{ t('error') }}</h3>
        <p style="margin: 0;">{{ error }}</p>
      </div>
    </div>
  `,

  setup() {
    const emailQuery = ref('')
    const loading = ref(false)
    const result = ref(null)
    const error = ref(null)
    const removing = ref(false)

    const checkEmail = async () => {
      if (!emailQuery.value) return

      loading.value = true
      error.value = null
      result.value = null

      try {
        const encodedEmail = encodeURIComponent(emailQuery.value)
        const data = await api.get(`/api/blacklist/${encodedEmail}/`)
        result.value = data
      } catch (e) {
        error.value = e.message
      } finally {
        loading.value = false
      }
    }

    const removeFromBlacklist = async () => {
      if (!result.value || !result.value.email) return

      const confirmed = confirm(
        `Sbloccare ${result.value.email}?\n\n` +
        'Questa azione rimuoverà l\'indirizzo dalla blacklist Brevo.\n' +
        'Brevo riproverà a inviare email a questo indirizzo.\n\n' +
        'ATTENZIONE: Procedere SOLO se:\n' +
        '✓ Il blocco era erroneo (hard bounce temporaneo segnalato come permanente)\n' +
        '✓ Hai verificato con il destinatario che vuole ricevere le email\n\n' +
        'Se il blocco era VALIDO (spam, disiscrizione, email non più nello staff):\n' +
        '✗ NON sbloccare\n' +
        '✗ Rimuovi invece l\'indirizzo dai destinatari nell\'applicazione\n\n' +
        'Confermi di aver verificato la situazione?'
      )

      if (!confirmed) return

      removing.value = true

      try {
        const encodedEmail = encodeURIComponent(result.value.email)
        await api.delete(`/api/blacklist/${encodedEmail}/remove/`)

        alert('Email sbloccata con successo!')

        // Re-check to show updated status
        await checkEmail()
      } catch (e) {
        alert(`Errore: ${e.message}`)
      } finally {
        removing.value = false
      }
    }

    const formatReason = (reason) => {
      // Handle objects/dicts - extract code first, fallback to message
      if (typeof reason === 'object' && reason !== null) {
        if (reason.code) {
          reason = reason.code
        } else if (reason.message) {
          reason = reason.message
        } else {
          reason = JSON.stringify(reason)
        }
      }

      // Ensure it's a string
      reason = String(reason || 'unknown')

      // Tabella traduzioni code Brevo → Italiano
      const translations = {
        // Hard bounces
        'hard_bounce': 'Hard Bounce',
        'hardBounce': 'Hard Bounce',
        'invalidEmail': 'Email Invalida',
        'blockedDomain': 'Dominio Bloccato',
        'unknown': 'Sconosciuto',

        // Soft bounces
        'soft_bounce': 'Soft Bounce',
        'softBounce': 'Soft Bounce',
        'mailboxFull': 'Casella Piena',
        'greyListed': 'Greylist',
        'temporaryUnavailable': 'Temporaneamente Non Disponibile',

        // Complaints
        'complaint': 'Segnalazione Spam',
        'spam': 'Spam',

        // Unsubscribes
        'unsubscribe': 'Disiscrizione',
        'unsubscribed': 'Disiscritto',
        'unsubscribedViaEmail': 'Disiscritto via Email',
        'unsubscribedViaLink': 'Disiscritto via Link',
        'unsubscribedViaAdmin': 'Disiscritto dall\'Amministratore',

        // Blocks
        'manual_block': 'Blocco Manuale',
        'blocked': 'Bloccato',
        'blockedContact': 'Contatto Bloccato',

        // Invalid
        'invalid_email': 'Email Invalida',
        'invalidDomain': 'Dominio Invalido',
        'invalidSyntax': 'Sintassi Invalida',

        // Deferred
        'deferred': 'Differita',

        // Errors
        'error': 'Errore',
        'errorRelaying': 'Errore di Inoltro'
      }

      return translations[reason] || reason
    }

    return {
      emailQuery,
      loading,
      result,
      error,
      removing,
      t,
      checkEmail,
      removeFromBlacklist,
      formatReason,
      formatDateTime  // Use global helper
    }
  }
}

// List All Tab Component
const ListAllTab = {
  template: `
    <div class="blacklist-tab">
      <h2 style="margin-bottom: 20px;">Lista Completa Blacklist</h2>

      <!-- Istruzioni collapsabili -->
      <div class="alert" style="margin-bottom: 30px; border-radius: 8px; border-left: 4px solid #417690; background: #f0f7fa;">
        <div style="display: flex; justify-content: space-between; align-items: center; cursor: pointer; padding: 15px 20px;" @click="toggleInstructions">
          <h3 style="margin: 0; color: #333;">📋 Gestione Blacklist Brevo</h3>
          <span style="font-size: 24px; color: #417690; user-select: none;">{{ instructionsOpen ? '−' : '+' }}</span>
        </div>

        <div v-show="instructionsOpen" style="padding: 0 20px 20px 20px;">
          <p style="margin: 0 0 15px 0; line-height: 1.6;">
            Questa sezione mostra gli indirizzi email <strong>bloccati dalla piattaforma Brevo</strong> dopo eventi critici (hard bounce, spam complaints, disiscrizioni).
            Quando un indirizzo è in blacklist, Brevo <strong>non invierà più email</strong> a quel destinatario.
          </p>

          <div style="margin-bottom: 15px;">
            <strong style="display: block; margin-bottom: 8px;">🔍 Quando il blocco è VALIDO:</strong>
            <ul style="margin: 0; padding-left: 25px; line-height: 1.8;">
              <li><strong>Disiscritto via Email</strong>: Il destinatario ha chiesto esplicitamente di non ricevere più email</li>
              <li><strong>Segnalazione Spam</strong>: Il destinatario ci ha segnalato come spammers</li>
              <li><strong>Email non più nello staff</strong>: La persona non fa più parte del team/organizzazione</li>
            </ul>
            <p style="margin: 10px 0 0 25px; color: #e65100; font-weight: 600;">
              → In questi casi: <strong>Rimuovere l'indirizzo dai destinatari nell'applicazione</strong> (Newsletter, etc.)
            </p>
          </div>

          <div style="margin-bottom: 15px;">
            <strong style="display: block; margin-bottom: 8px;">✅ Quando il blocco è INVALIDO:</strong>
            <ul style="margin: 0; padding-left: 25px; line-height: 1.8;">
              <li><strong>Hard Bounce erroneo</strong>: Il server email del destinatario ha temporaneamente segnalato l'indirizzo come permanentemente invalido, ma in realtà è ancora valido (raro, ma succede)</li>
              <li><strong>Blocco non più attuale</strong>: Situazione verificata con il destinatario che conferma di voler ricevere le email</li>
            </ul>
            <p style="margin: 10px 0 0 25px; color: #2e7d32; font-weight: 600;">
              → Solo in questi casi: Usare il pulsante <strong>"Sblocca o rimuovi"</strong> per riabilitare l'invio
            </p>
          </div>

          <div style="padding: 15px; background: #fff3e0; border-left: 3px solid #ff9800; border-radius: 4px;">
            <strong style="color: #e65100;">⚠️ ATTENZIONE:</strong>
            <p style="margin: 5px 0 0 0; line-height: 1.6;">
              Il pulsante <strong>"Sblocca o rimuovi"</strong> rimuove l'indirizzo dalla blacklist Brevo: il server <strong>riproverà a inviare email</strong> a quell'indirizzo.
              Se il blocco era valido (spam, disiscrizione), si genererà un <strong>nuovo bounce o protesta</strong>, danneggiando gravemente la reputazione del mittente.
              <strong>Usare solo dopo aver verificato</strong> che il blocco era effettivamente erroneo o che il destinatario è stato rimosso dall'applicazione.
            </p>
          </div>
        </div>
      </div>

      <!-- Filters -->
      <div style="display: flex; gap: 15px; margin-bottom: 20px; flex-wrap: wrap; align-items: center;">
        <div>
          <label style="display: block; font-size: 13px; color: #666; margin-bottom: 5px;">Filtra per motivo:</label>
          <select v-model="reasonFilter" @change="loadContacts" style="padding: 8px 12px; border: 1px solid #ddd; border-radius: 4px;">
            <option value="">Tutti</option>
            <option value="hard_bounce">Hard Bounce</option>
            <option value="soft_bounce">Soft Bounce</option>
            <option value="complaint">Segnalazione Spam</option>
            <option value="unsubscribe">Disiscrizione</option>
            <option value="invalid_email">Email Invalida</option>
          </select>
        </div>

        <div>
          <label style="display: block; font-size: 13px; color: #666; margin-bottom: 5px;">Cerca:</label>
          <input
            v-model="searchQuery"
            type="text"
            placeholder="Filtra per email..."
            style="padding: 8px 12px; border: 1px solid #ddd; border-radius: 4px; width: 250px;">
        </div>

        <div v-if="selectedEmails.length > 0" style="margin-left: auto;">
          <button
            @click="removeSelected"
            :disabled="removingMultiple"
            style="padding: 10px 20px; background: #ff9800; color: white; border: none; border-radius: 6px; cursor: pointer; font-weight: 600;">
            {{ removingMultiple ? 'Sblocco in corso...' : 'Sblocca o rimuovi (' + selectedEmails.length + ')' }}
          </button>
        </div>
      </div>

      <!-- Stats -->
      <div v-if="stats.by_reason" class="kpi-grid" style="margin-bottom: 30px;">
        <div
          v-for="(count, reason) in stats.by_reason"
          :key="reason"
          class="kpi-card clickable"
          :class="{ active: reasonFilter === reason }"
          @click="filterByReason(reason)"
          style="cursor: pointer;">
          <div class="kpi-label">{{ formatReason(reason) }}</div>
          <div class="kpi-value">{{ count }}</div>
        </div>
      </div>

      <!-- Loading -->
      <div v-if="loading" class="loading">Caricamento...</div>

      <!-- Error -->
      <div v-if="error" class="alert alert-error" style="margin-top: 20px;">
        <strong>Errore:</strong> {{ error }}
      </div>

      <!-- Table -->
      <div v-if="!loading && filteredContacts.length > 0">
        <p style="color: #666; margin-bottom: 15px;">
          Mostrando {{ filteredContacts.length }} di {{ stats.total }} contatti
        </p>

        <table class="data-table">
          <thead>
            <tr>
              <th style="width: 40px;">
                <input
                  type="checkbox"
                  @change="toggleAll"
                  :checked="allSelected">
              </th>
              <th>Email</th>
              <th>Motivo</th>
              <th>Data Blocco</th>
              <th style="width: 100px;">Dettagli</th>
              <th>Azioni</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="contact in filteredContacts"
              :key="contact.email"
              @click="toggleRowSelection(contact.email, $event)"
              style="cursor: pointer;">
              <td @click.stop>
                <input
                  type="checkbox"
                  :value="contact.email"
                  v-model="selectedEmails">
              </td>
              <td>{{ contact.email }}</td>
              <td>
                <span class="status-badge" :class="'badge-' + normalizeReasonClass(contact.reason)">
                  {{ formatReason(contact.reason) }}
                </span>
              </td>
              <td>{{ formatDateTime(contact.blockedAt) }}</td>
              <td @click.stop style="text-align: center;">
                <button
                  v-if="isHardBounce(contact.reason)"
                  @click="showBounceDetails(contact)"
                  style="padding: 6px 12px; background: #417690; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 13px;"
                  :title="contact.has_local_data ? 'Dettagli bounce (database locale + Brevo)' : 'Dettagli bounce (da blacklist Brevo)'">
                  ℹ️ Dettagli
                </button>
              </td>
              <td @click.stop>
                <button
                  @click="removeSingle(contact.email)"
                  style="padding: 6px 12px; background: #ff9800; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 13px;">
                  Sblocca o rimuovi
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Empty State -->
      <div v-if="!loading && !error && filteredContacts.length === 0" style="text-align: center; padding: 60px 20px; color: #999;">
        <div style="font-size: 48px; margin-bottom: 15px;">✅</div>
        <h3 style="margin: 0 0 10px 0;">Nessuna email in blacklist</h3>
        <p>{{ searchQuery ? 'Nessun risultato per la ricerca' : 'La blacklist è vuota' }}</p>
      </div>

      <!-- Bounce Details Modal -->
      <div v-if="bounceModal.show" class="modal-overlay" @click.self="closeBounceModal">
        <div class="modal-content" style="max-width: 600px;">
          <div class="modal-header">
            <div>
              <h2>Dettagli Hard Bounce</h2>
              <p style="font-size: 14px; color: #666; margin: 5px 0 0 0;">{{ bounceModal.email }}</p>
            </div>
            <button @click="closeBounceModal" class="modal-close">&times;</button>
          </div>

          <div class="modal-body">
            <div v-if="bounceModal.loading" class="loading">Caricamento dettagli aggiuntivi dal database locale...</div>

            <!-- Dati dalla Blacklist Brevo (sempre disponibili) -->
            <div v-if="bounceModal.blacklistData">
              <div style="margin-bottom: 20px;">
                <strong style="display: block; margin-bottom: 5px; color: #666;">Motivo Blocco (Brevo):</strong>
                <div style="padding: 12px; background: #fff3e0; border-left: 3px solid #ff9800; border-radius: 4px; font-size: 14px; line-height: 1.6;">
                  {{ formatReason(bounceModal.blacklistData.reason) }}
                </div>
              </div>

              <div style="margin-bottom: 20px;">
                <strong style="display: block; margin-bottom: 5px; color: #666;">Data Blocco:</strong>
                <div>{{ formatDateTime(bounceModal.blacklistData.blockedAt) }}</div>
              </div>

              <div v-if="bounceModal.blacklistData.senders && bounceModal.blacklistData.senders.length > 0" style="margin-bottom: 20px;">
                <strong style="display: block; margin-bottom: 5px; color: #666;">Mittenti Bloccati:</strong>
                <div>{{ bounceModal.blacklistData.senders.join(', ') }}</div>
              </div>
            </div>

            <!-- Dati dal Database Locale o API Brevo (se disponibili) -->
            <div v-if="bounceModal.localData && !bounceModal.loading" style="margin-top: 30px; padding-top: 20px; border-top: 2px solid #eee;">
              <h3 style="font-size: 16px; margin-bottom: 15px; color: #417690;">
                <span v-if="bounceModal.localData.source === 'local'">📊 Dettagli Evento (Database Locale)</span>
                <span v-else>🔍 Dettagli Evento (Brevo API)</span>
              </h3>

              <div style="margin-bottom: 20px;">
                <strong style="display: block; margin-bottom: 5px; color: #666;">Tipo Bounce:</strong>
                <span :class="bounceModal.localData.bounce_type === 'hard' ? 'bounce-hard' : 'bounce-soft'" style="font-size: 14px;">
                  {{ bounceModal.localData.bounce_type === 'hard' ? 'Hard Bounce' : 'Soft Bounce' }}
                </span>
              </div>

              <div style="margin-bottom: 20px;">
                <strong style="display: block; margin-bottom: 5px; color: #666;">Messaggio Dettagliato:</strong>
                <div style="padding: 12px; background: #f5f5f5; border-radius: 4px; font-family: monospace; font-size: 12px; line-height: 1.6; white-space: pre-wrap;">{{ bounceModal.localData.bounce_reason }}</div>
              </div>

              <div v-if="bounceModal.localData.subject" style="margin-bottom: 20px;">
                <strong style="display: block; margin-bottom: 5px; color: #666;">Oggetto Email:</strong>
                <div>{{ bounceModal.localData.subject }}</div>
              </div>

              <div style="margin-bottom: 20px;">
                <strong style="display: block; margin-bottom: 5px; color: #666;">Data Evento:</strong>
                <div>{{ formatDateTime(bounceModal.localData.timestamp) }}</div>
              </div>
            </div>

            <!-- Info se non ci sono dati aggiuntivi -->
            <div v-if="!bounceModal.localData && !bounceModal.loading" style="margin-top: 20px; padding: 12px; background: #f0f7fa; border-left: 3px solid #417690; border-radius: 4px; font-size: 13px;">
              ℹ️ Dettagli aggiuntivi non disponibili: nessun bounce trovato (né nel database locale né nelle statistiche Brevo degli ultimi 3 anni).
            </div>
          </div>
        </div>
      </div>
    </div>
  `,

  setup() {
    const loading = ref(false)
    const error = ref(null)
    const contacts = ref([])
    const stats = ref({})
    const reasonFilter = ref('')
    const searchQuery = ref('')
    const selectedEmails = ref([])
    const removingMultiple = ref(false)

    // Stato istruzioni (localStorage)
    const instructionsOpen = ref(
      localStorage.getItem('blacklist-instructions-open') !== 'false'
    )

    const toggleInstructions = () => {
      instructionsOpen.value = !instructionsOpen.value
      localStorage.setItem('blacklist-instructions-open', instructionsOpen.value)
    }

    // Stato modal bounce details
    const bounceModal = ref({
      show: false,
      loading: false,
      error: null,
      email: null,
      blacklistData: null,  // Dati dalla blacklist (sempre disponibili)
      localData: null       // Dati dal DB locale (opzionali)
    })

    const showBounceDetails = async (contact) => {
      bounceModal.value = {
        show: true,
        loading: true,  // Sempre loading perché proviamo a caricare dettagli
        error: null,
        email: contact.email,
        blacklistData: {
          reason: contact.reason,
          blockedAt: contact.blockedAt,
          senders: contact.senderEmail || []
        },
        localData: null
      }

      // Prova a caricare dettagli (da DB locale o API Brevo)
      try {
        const encodedEmail = encodeURIComponent(contact.email)
        const data = await api.get(`/api/bounce-details/${encodedEmail}/`)
        bounceModal.value.localData = data
        bounceModal.value.loading = false
      } catch (e) {
        // Non è un errore fatale - mostriamo comunque i dati dalla blacklist
        console.warn('Could not load bounce details:', e.message)
        bounceModal.value.loading = false
      }
    }

    const closeBounceModal = () => {
      bounceModal.value = {
        show: false,
        loading: false,
        error: null,
        email: null,
        blacklistData: null,
        localData: null
      }
    }

    const isHardBounce = (reason) => {
      if (typeof reason === 'object' && reason !== null) {
        reason = reason.code || reason.message || ''
      }
      reason = String(reason || '').toLowerCase()
      return reason.includes('hard') || reason.includes('hardbounce')
    }

    const filteredContacts = computed(() => {
      let filtered = contacts.value

      if (searchQuery.value) {
        const query = searchQuery.value.toLowerCase()
        filtered = filtered.filter(c =>
          c.email.toLowerCase().includes(query)
        )
      }

      // Sort by blocked date (most recent first)
      filtered = [...filtered].sort((a, b) => {
        const dateA = a.blockedAt || ''
        const dateB = b.blockedAt || ''
        return dateB.localeCompare(dateA)
      })

      return filtered
    })

    const allSelected = computed(() => {
      return filteredContacts.value.length > 0 &&
             selectedEmails.value.length === filteredContacts.value.length
    })

    const loadContacts = async () => {
      loading.value = true
      error.value = null

      try {
        const params = new URLSearchParams()
        if (reasonFilter.value) {
          params.append('reason', reasonFilter.value)
        }
        params.append('limit', '500')

        const data = await api.get(`/api/blacklist/?${params}`)
        contacts.value = data.contacts
        stats.value = data
      } catch (e) {
        error.value = e.message
      } finally {
        loading.value = false
      }
    }

    const filterByReason = async (reason) => {
      // Toggle filter: if already selected, clear filter
      if (reasonFilter.value === reason) {
        reasonFilter.value = ''
      } else {
        reasonFilter.value = reason
      }
      await loadContacts()
    }

    const toggleAll = () => {
      if (allSelected.value) {
        selectedEmails.value = []
      } else {
        selectedEmails.value = filteredContacts.value.map(c => c.email)
      }
    }

    const removeSingle = async (email) => {
      const confirmed = confirm(
        `Sbloccare ${email}?\n\n` +
        'Questa azione rimuoverà l\'indirizzo dalla blacklist Brevo.\n' +
        'Brevo riproverà a inviare email a questo indirizzo.\n\n' +
        'ATTENZIONE: Procedere SOLO se:\n' +
        '✓ Il blocco era erroneo (hard bounce temporaneo segnalato come permanente)\n' +
        '✓ Hai verificato con il destinatario che vuole ricevere le email\n\n' +
        'Se il blocco era VALIDO (spam, disiscrizione, email non più nello staff):\n' +
        '✗ NON sbloccare\n' +
        '✗ Rimuovi invece l\'indirizzo dai destinatari nell\'applicazione\n\n' +
        'Confermi di aver verificato la situazione?'
      )
      if (!confirmed) return

      try {
        const encodedEmail = encodeURIComponent(email)
        await api.delete(`/api/blacklist/${encodedEmail}/remove/`)
        alert('Email sbloccata con successo!')
        await loadContacts()
      } catch (e) {
        alert(`Errore: ${e.message}`)
      }
    }

    const removeSelected = async () => {
      const count = selectedEmails.value.length
      const confirmed = confirm(
        `Sbloccare ${count} email?\n\n` +
        'Questa azione rimuoverà questi indirizzi dalla blacklist Brevo.\n' +
        'Brevo riproverà a inviare email a questi indirizzi.\n\n' +
        'ATTENZIONE: Procedere SOLO se:\n' +
        '✓ I blocchi erano erronei (hard bounce temporanei segnalati come permanenti)\n' +
        '✓ Hai verificato con i destinatari che vogliono ricevere le email\n\n' +
        'Se i blocchi erano VALIDI (spam, disiscrizioni, email non più nello staff):\n' +
        '✗ NON sbloccare\n' +
        '✗ Rimuovi invece gli indirizzi dai destinatari nell\'applicazione\n\n' +
        'Confermi di aver verificato la situazione per OGNI indirizzo?'
      )

      if (!confirmed) return

      removingMultiple.value = true

      let success = 0
      let failed = 0

      for (const email of selectedEmails.value) {
        try {
          const encodedEmail = encodeURIComponent(email)
          await api.delete(`/api/blacklist/${encodedEmail}/remove/`)
          success++
        } catch (e) {
          failed++
        }
      }

      removingMultiple.value = false
      selectedEmails.value = []

      alert(`Operazione completata!\n\nEmail sbloccate: ${success}\nFallite: ${failed}`)

      await loadContacts()
    }

    const toggleRowSelection = (email, event) => {
      // Don't toggle if clicking on checkbox or button (they have @click.stop)
      const index = selectedEmails.value.indexOf(email)
      if (index > -1) {
        selectedEmails.value.splice(index, 1)
      } else {
        selectedEmails.value.push(email)
      }
    }

    const normalizeReasonClass = (reason) => {
      // Ensure reason is string for CSS class
      if (typeof reason === 'object') {
        return 'unknown'
      }
      return reason || 'unknown'
    }

    const formatReason = (reason) => {
      // Handle objects/dicts - extract code first, fallback to message
      if (typeof reason === 'object' && reason !== null) {
        // Priority: code (will be translated), then message, then stringify
        if (reason.code) {
          reason = reason.code
        } else if (reason.message) {
          reason = reason.message
        } else {
          reason = JSON.stringify(reason)
        }
      }

      // Ensure it's a string
      reason = String(reason || 'unknown')

      // Tabella traduzioni code Brevo → Italiano
      const translations = {
        // Hard bounces
        'hard_bounce': 'Hard Bounce',
        'hardBounce': 'Hard Bounce',
        'invalidEmail': 'Email Invalida',
        'blockedDomain': 'Dominio Bloccato',
        'unknown': 'Sconosciuto',

        // Soft bounces
        'soft_bounce': 'Soft Bounce',
        'softBounce': 'Soft Bounce',
        'mailboxFull': 'Casella Piena',
        'greyListed': 'Greylist',
        'temporaryUnavailable': 'Temporaneamente Non Disponibile',

        // Complaints
        'complaint': 'Segnalazione Spam',
        'spam': 'Spam',

        // Unsubscribes
        'unsubscribe': 'Disiscrizione',
        'unsubscribed': 'Disiscritto',
        'unsubscribedViaEmail': 'Disiscritto via Email',
        'unsubscribedViaLink': 'Disiscritto via Link',
        'unsubscribedViaAdmin': 'Disiscritto dall\'Amministratore',

        // Blocks
        'manual_block': 'Blocco Manuale',
        'blocked': 'Bloccato',
        'blockedContact': 'Contatto Bloccato',

        // Invalid
        'invalid_email': 'Email Invalida',
        'invalidDomain': 'Dominio Invalido',
        'invalidSyntax': 'Sintassi Invalida',

        // Deferred
        'deferred': 'Differita',

        // Errors
        'error': 'Errore',
        'errorRelaying': 'Errore di Inoltro'
      }

      // Se c'è traduzione, usala; altrimenti restituisci il valore originale
      return translations[reason] || reason
    }

    onMounted(() => {
      loadContacts()
    })

    return {
      loading,
      error,
      contacts,
      stats,
      reasonFilter,
      searchQuery,
      selectedEmails,
      removingMultiple,
      instructionsOpen,
      t,
      toggleInstructions,
      bounceModal,
      showBounceDetails,
      closeBounceModal,
      isHardBounce,
      filteredContacts,
      allSelected,
      loadContacts,
      filterByReason,
      toggleAll,
      toggleRowSelection,
      removeSingle,
      removeSelected,
      normalizeReasonClass,
      formatReason,
      formatDateTime  // Use global helper
    }
  }
}

// Main Dashboard Component
const Dashboard = {
  template: `
    <div class="blacklist-dashboard">
      <!-- Tabs -->
      <div class="tabs" style="margin-bottom: 30px; border-bottom: 2px solid #eee;">
        <button
          v-for="tab in tabs"
          :key="tab.id"
          @click="activeTab = tab.id"
          :class="{ active: activeTab === tab.id }"
          style="padding: 12px 24px; background: none; border: none; border-bottom: 3px solid transparent; cursor: pointer; font-size: 15px; font-weight: 600; color: #666; margin-right: 10px;"
          :style="{
            color: activeTab === tab.id ? '#417690' : '#666',
            borderBottomColor: activeTab === tab.id ? '#417690' : 'transparent'
          }">
          {{ tab.label }}
        </button>
      </div>

      <!-- Tab Content -->
      <check-email-tab v-if="activeTab === 'check'"></check-email-tab>
      <list-all-tab v-if="activeTab === 'list'"></list-all-tab>
    </div>
  `,

  setup() {
    const activeTab = ref('list')  // Default: mostra lista

    const tabs = [
      { id: 'list', label: t('manage_blacklist_tab') },
      { id: 'check', label: t('check_email_tab') }
    ]

    return {
      activeTab,
      tabs,
      t
    }
  },

  components: {
    CheckEmailTab,
    ListAllTab
  }
}

// ========================================
// Router Setup
// ========================================
const routes = [
  {
    path: '/',
    component: Dashboard
  }
]

const router = createRouter({
  history: createWebHashHistory(),
  routes
})

// ========================================
// App Setup
// ========================================
const app = createApp({})
app.use(router)
app.mount('#blacklist-app')
