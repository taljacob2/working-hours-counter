<script>
  import { logs, calCursor, showToast, loading, excelColorHomeHours, dayOverrides, fillMissingOfficeHours, requiredHours } from '../stores/appStore.js'
  import { monthLogsAndIntervals } from '../lib/reportIntervals.js'

  // Metadata is passed in from SettingsScreen's own (possibly-unsaved) local
  // fields, so this works immediately without requiring a separate Save step.
  export let companyName = ''
  export let employeeName = ''
  export let employeeCode = ''
  export let cardNumber = ''
  export let payrollNumber = ''
  export let employmentStartDate = '' // 'YYYY-MM-DD'
  export let workAgreementText = ''

  $: canGenerate = companyName.trim() !== '' && employeeName.trim() !== ''

  function getMonthName(date) {
    return date.toLocaleString('he-IL', { month: 'long', year: 'numeric' })
  }

  // 'YYYY-MM-DD' -> 'DD/MM/YY', matching the vendor template's date format
  function toVendorDate(isoDate) {
    if (!isoDate) return ''
    const [y, m, d] = isoDate.split('-')
    if (!y || !m || !d) return ''
    return `${d}/${m}/${y.slice(2)}`
  }

  async function handleGenerate() {
    if (!canGenerate) return
    loading.set(true)
    showToast('יוצר דוח שעות...', 'info')

    try {
      const targetYear = $calCursor.getFullYear()
      const targetMonth = $calCursor.getMonth() + 1
      const allIntervals = monthLogsAndIntervals([...$logs], targetYear, targetMonth)

      const config = {
        year: targetYear,
        month: targetMonth,
        companyName,
        employeeName,
        employeeCode,
        cardNumber,
        payrollNumber,
        startDate: toVendorDate(employmentStartDate),
        agreementText: workAgreementText,
        targetDailyHours: $requiredHours,
        colorHomeHours: $excelColorHomeHours,
        fillMissingOffice: $fillMissingOfficeHours,
        dayOverrides: $dayOverrides,
      }

      const res = await fetch('/api/generate-xls', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ config, logs: allIntervals }),
      })

      if (!res.ok) {
        let errMsg = 'שגיאת שרת לא ידועה'
        try {
          const errJson = await res.json()
          errMsg = errJson.error || errMsg
        } catch {}
        throw new Error(errMsg)
      }

      const blob = await res.blob()
      const downloadUrl = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = downloadUrl
      a.download = `${employeeName || 'דוח'}_${targetYear}${String(targetMonth).padStart(2, '0')}_נוצר.xls`
      a.click()
      URL.revokeObjectURL(downloadUrl)

      showToast('הדוח נוצר בהצלחה!', 'success')
    } catch (err) {
      console.error(err)
      showToast('יצירת הדוח נכשלה: ' + err.message, 'error')
    } finally {
      loading.set(false)
    }
  }
</script>

<div class="card generate-report-card">
  <div class="header-row">
    <div class="title-group">
      <span class="icon">🆕</span>
      <h3>יצירת דוח שעות מאפס</h3>
    </div>
    <span class="pill pill-home tabnum">חודש נבחר: {getMonthName($calCursor)}</span>
  </div>

  <p class="description">
    צור דוח שעות בפורמט החברה בלי להעלות קובץ .xls רשמי — שימושי אם עדיין אין ברשותך את הקובץ, או אם פשוט תרצה לדלג על ההעלאה. הדוח ייבנה מהנתונים שרשמת באפליקציה ומהפרטים שמולאו למעלה.
  </p>

  {#if !canGenerate}
    <p class="warning-text">⚠ יש למלא שם חברה ושם עובד למעלה כדי ליצור דוח.</p>
  {/if}

  <button
    type="button"
    class="btn btn-primary"
    style="width:100%"
    disabled={!canGenerate || $loading}
    on:click={handleGenerate}
  >
    🆕 צור דוח שעות
  </button>
</div>

<style>
  .generate-report-card {
    border-top: 4px solid var(--color-home);
    direction: rtl;
  }

  .header-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: var(--space-3);
  }

  .title-group {
    display: flex;
    align-items: center;
    gap: var(--space-2);
  }

  .title-group h3 {
    font-size: 1.1rem;
    font-weight: 600;
  }

  .icon {
    font-size: 1.3rem;
  }

  .description {
    font-size: 0.875rem;
    color: var(--color-text-muted);
    line-height: 1.5;
    margin-bottom: var(--space-3);
  }

  .warning-text {
    font-size: 0.8125rem;
    color: var(--color-danger);
    margin-bottom: var(--space-3);
  }
</style>
