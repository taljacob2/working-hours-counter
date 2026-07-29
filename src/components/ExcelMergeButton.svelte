<script>
  import { logs, calCursor, showToast, loading, excelColorHomeHours, dayOverrides, fillMissingOfficeHours } from '../stores/appStore.js'
  import { getSupabase } from '../lib/supabase.js'
  import { monthLogsAndIntervals } from '../lib/reportIntervals.js'
  import { mergeXls, warmUpPyodide, isPyodideReady } from '../lib/pyodideBridge.js'

  warmUpPyodide()

  let fileInput
  let uploadEl
  let isDragging = false

  let colorHomeHoursLocal = false
  excelColorHomeHours.subscribe(v => colorHomeHoursLocal = v)

  async function toggleColorHomeHours(checked) {
    colorHomeHoursLocal = checked
    excelColorHomeHours.set(checked)
    localStorage.setItem('whl_excel_color_home', String(checked))
    const sb = getSupabase()
    await sb.from('work_settings').upsert([{ key: 'excelColorHomeHours', value: String(checked) }])
  }

  let fillMissingOfficeLocal = true
  fillMissingOfficeHours.subscribe(v => fillMissingOfficeLocal = v)

  async function toggleFillMissingOffice(checked) {
    fillMissingOfficeLocal = checked
    fillMissingOfficeHours.set(checked)
    localStorage.setItem('whl_fill_missing_office', String(checked))
    const sb = getSupabase()
    await sb.from('work_settings').upsert([{ key: 'fillMissingOfficeHours', value: String(checked) }])
  }
  
  function getMonthName(date) {
    return date.toLocaleString('en-US', { month: 'long', year: 'numeric' })
  }

  async function handleFileSelect(e) {
    const file = e.target.files?.[0]
    if (!file) return
    await processFile(file)
  }
  
  function handleDragOver(e) {
    e.preventDefault()
    isDragging = true
  }
  
  function handleDragLeave() {
    isDragging = false
  }
  
  async function handleDrop(e) {
    e.preventDefault()
    isDragging = false
    const file = e.dataTransfer?.files?.[0]
    if (file) {
      if (!file.name.toLowerCase().endsWith('.xls')) {
        showToast('Please upload an XLS file only', 'error')
        return
      }
      await processFile(file)
    }
  }
  
  async function processFile(file) {
    loading.set(true)
    showToast(
      isPyodideReady()
        ? 'Reading the Excel file and preparing the data...'
        : 'Preparing the processing engine (one-time, may take a few seconds)...',
      'info'
    )

    try {
      // 1. Get selected month from calendar cursor
      const targetYear = $calCursor.getFullYear()
      const targetMonth = $calCursor.getMonth() + 1

      // 2. Filter this month's logs and pair resume/pause events into intervals,
      // per platform. Office intervals are only used by the backend to backfill a
      // day the company's own sheet never detailed — never to override real data.
      const allIntervals = monthLogsAndIntervals([...$logs], targetYear, targetMonth)

      // 3. Read file bytes and merge entirely client-side via Pyodide — no
      // server involved, so this works the same on GitHub Pages as locally.
      const xlsBytes = new Uint8Array(await file.arrayBuffer())
      const blob = await mergeXls(xlsBytes, allIntervals, colorHomeHoursLocal, $dayOverrides, fillMissingOfficeLocal)

      // 4. Trigger download of the merged file
      const downloadUrl = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = downloadUrl

      const origName = file.name.replace(/\.xls$/i, '')
      a.download = `${origName}_updated.xls`
      a.click()
      URL.revokeObjectURL(downloadUrl)

      showToast('File merged and updated successfully!', 'success')
    } catch (err) {
      console.error(err)
      showToast('Merge failed: ' + err.message, 'error')
    } finally {
      loading.set(false)
      if (fileInput) fileInput.value = ''
    }
  }
</script>

<div class="card xls-merge-card">
  <div class="header-row">
    <div class="title-group">
      <span class="icon">📊</span>
      <h3>Update &amp; Merge Official Excel File</h3>
    </div>
    <span class="pill pill-home tabnum">Selected month: {getMonthName($calCursor)}</span>
  </div>

  <p class="description">
    Upload the official hours report you received from the company (in <code>.xls</code> format). The system will automatically merge in the work-from-home hours logged in the app and recalculate all norms and overtime, without affecting the original report's styling or structure.
  </p>
  
  <!-- Drag & Drop Dropzone -->
  <button 
    type="button"
    class="dropzone"
    class:dragging={isDragging}
    on:dragover={handleDragOver}
    on:dragleave={handleDragLeave}
    on:drop={handleDrop}
    on:click={() => fileInput.click()}
  >
    <div class="dropzone-content">
      <span class="upload-icon">📥</span>
      <span class="primary-text">Click to choose a file or drag an Excel file here (.xls)</span>
      <span class="secondary-text">Supports JBClock reports</span>
    </div>
  </button>
  
  <input 
    type="file" 
    accept=".xls" 
    bind:this={fileInput} 
    on:change={handleFileSelect} 
    style="display: none;" 
  />
  
  <div class="info-alert">
    <span class="alert-icon">💡</span>
    <p>Work-from-home hours will be merged into the secondary check-in/check-out columns (check-in 2 and check-out 2) for each work day. In addition, the "vacation" marking will update automatically based on the vacation days you marked manually in the app (adding or removing the marking in the received file).</p>
  </div>

  <label class="color-toggle-row">
    <input
      type="checkbox"
      checked={colorHomeHoursLocal}
      on:change={e => toggleColorHomeHours(e.target.checked)}
    />
    <span>Color the home hours we added in a distinct shade (in addition to the company's colors for exceptions/vacation)</span>
  </label>

  <label class="color-toggle-row">
    <input
      type="checkbox"
      checked={fillMissingOfficeLocal}
      on:change={e => toggleFillMissingOffice(e.target.checked)}
    />
    <span>Backfill office hours the app tracked but the company file hasn't detailed yet (highlighted in purple for HR)</span>
  </label>
</div>

<style>
  .xls-merge-card {
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
    margin-bottom: var(--space-4);
  }
  
  .dropzone {
    width: 100%;
    border: 2px dashed var(--color-border);
    border-radius: var(--radius-md);
    padding: var(--space-6) var(--space-4);
    background: var(--color-surface-2);
    transition: border-color var(--transition), background var(--transition), transform var(--transition);
    outline: none;
    text-align: center;
    margin-bottom: var(--space-4);
  }
  
  .dropzone:hover, .dropzone.dragging {
    border-color: var(--color-home);
    background: var(--color-home-subtle);
  }
  
  .dropzone:active {
    transform: scale(0.995);
  }
  
  .dropzone-content {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: var(--space-2);
  }
  
  .upload-icon {
    font-size: 2.2rem;
    filter: grayscale(0.2);
  }
  
  .primary-text {
    font-size: 0.9375rem;
    font-weight: 500;
    color: var(--color-text);
  }
  
  .secondary-text {
    font-size: 0.8125rem;
    color: var(--color-text-muted);
  }
  
  .info-alert {
    display: flex;
    gap: var(--space-2);
    padding: var(--space-3);
    background: var(--color-surface-2);
    border-radius: var(--radius-sm);
    border-right: 3px solid var(--color-text-muted);
  }
  
  .alert-icon {
    font-size: 1rem;
  }
  
  .info-alert p {
    font-size: 0.8125rem;
    color: var(--color-text-muted);
    line-height: 1.4;
  }

  .color-toggle-row {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    margin-top: var(--space-3);
    font-size: 0.8125rem;
    color: var(--color-text);
    font-weight: normal;
    cursor: pointer;
  }

  .color-toggle-row input {
    cursor: pointer;
    flex-shrink: 0;
  }
</style>
