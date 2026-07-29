<script>
  import { excelColorHomeHours, fillMissingOfficeHours } from '../stores/appStore.js'
  import { getSupabase } from '../lib/supabase.js'

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
</script>

<div class="card excel-report-options">
  <p class="section-title">Excel Report Options</p>
  <p class="info-text">These apply whether you merge an official file or generate a report from scratch below.</p>

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
  .excel-report-options {
    direction: ltr;
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
