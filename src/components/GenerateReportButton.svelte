<script>
  import { logs, calCursor, showToast, loading, excelColorHomeHours, dayOverrides, fillMissingOfficeHours, requiredHours } from '../stores/appStore.js'
  import { monthLogsAndIntervals } from '../lib/reportIntervals.js'
  import { generateXls, warmUpPyodide, isPyodideReady } from '../lib/pyodideBridge.js'
  import { saveFile } from '../lib/exportUtils.js'

  warmUpPyodide()

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
    return date.toLocaleString('en-US', { month: 'long', year: 'numeric' })
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
    showToast(
      isPyodideReady()
        ? 'Generating hours report...'
        : 'Preparing the processing engine (one-time, may take a few seconds)...',
      'info'
    )

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

      // Generated entirely client-side via Pyodide — no server involved, so
      // this works the same on GitHub Pages as locally.
      const blob = await generateXls(config, allIntervals)

      // On Android this shows a native "Save to…" picker so the user knows
      // exactly where it went; on web it's a normal browser download.
      const filename = `${employeeName || 'report'}_${targetYear}${String(targetMonth).padStart(2, '0')}_generated.xls`
      await saveFile(blob, filename, 'application/vnd.ms-excel')

      showToast('Report generated successfully!', 'success')
    } catch (err) {
      if (err?.message !== 'cancelled') {
        console.error(err)
        showToast('Report generation failed: ' + err.message, 'error')
      }
    } finally {
      loading.set(false)
    }
  }
</script>

<div class="card generate-report-card">
  <div class="header-row">
    <div class="title-group">
      <span class="icon">🆕</span>
      <h3>Generate Hours Report From Scratch</h3>
    </div>
    <span class="pill pill-home tabnum">Selected month: {getMonthName($calCursor)}</span>
  </div>

  <p class="description">
    Generate an hours report in the company's format without uploading the official .xls file — useful if you don't have the file yet, or just want to skip the upload. The report will be built from the data you logged in the app and the details filled in above.
  </p>

  {#if !canGenerate}
    <p class="warning-text">⚠ Fill in company name and employee name above to generate a report.</p>
  {/if}

  <button
    type="button"
    class="btn btn-primary"
    style="width:100%"
    disabled={!canGenerate || $loading}
    on:click={handleGenerate}
  >
    🆕 Generate Hours Report
  </button>
</div>

<style>
  .generate-report-card {
    border-top: 4px solid var(--color-home);
    direction: ltr;
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
